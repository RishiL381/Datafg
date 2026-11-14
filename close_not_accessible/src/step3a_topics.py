"""STEP 3a: COMPLAINT THEMES (BERTopic) on 1-2 star reviews

Purpose: discover what people actually complain about, and check that the 5 fixed aspects
(wait_time, cost, staff, language_access, hours_availability) cover the main themes.

Run from repo root:  .venv/bin/python close_not_accessible/src/step3a_topics.py

Writes:
  outputs/step3a_topics.csv           one row per topic: size, top words, share by service type,
                                      mapped aspect (aggregate only, no review text)
  outputs/cache/emb_minilm.npy        sentence embeddings for ALL reviews in reviews_all (reused in 3c)
  outputs/cache/topic_assignments.parquet   rid -> topic (row-level, gitignored)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

C.set_seeds()
EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMB_PATH = C.CACHE_DIR / "emb_minilm.npy"

rev = pd.read_parquet(C.CACHE_DIR / "reviews_all.parquet")

# ------------------------------------------------------------------ embeddings (all reviews, cached)
if EMB_PATH.exists() and len(np.load(EMB_PATH, mmap_mode="r")) == len(rev):
    emb = np.load(EMB_PATH)
else:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMB_MODEL, device="cpu")
    emb = model.encode(rev["review"].tolist(), batch_size=64, show_progress_bar=True, normalize_embeddings=True)
    np.save(EMB_PATH, emb)
print(f"embeddings: {emb.shape}")

# ------------------------------------------------------------------ topic model on 1-2 star
# DATA DECISION: topic model only 1-2 star reviews with >= 5 words (very short reviews like
# "Terrible!" carry no theme and become noise for clustering).
low_mask = rev["low_star"] & (rev["review"].str.split().str.len() >= 5)
docs = rev.loc[low_mask, "review"].tolist()
E = emb[low_mask.to_numpy()]
print(f"1-2 star docs for topic modeling: {len(docs):,}")

from bertopic import BERTopic  # noqa: E402
from hdbscan import HDBSCAN  # noqa: E402
from sklearn.feature_extraction.text import CountVectorizer  # noqa: E402
from umap import UMAP  # noqa: E402

# DATA DECISION: fit BERTopic SEPARATELY per service type. A single model on all 1-2 star reviews
# just splits by domain (clinic vs grocery vs pharmacy vocabulary), which hides the complaint themes.
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS  # noqa: E402

# Domain stop words: chain and service names would otherwise dominate topic labels.
extra_stop = ["cvs", "walgreens", "safeway", "kaiser", "store", "pharmacy", "clinic", "place", "location",
              "just", "like", "don", "dont", "didn", "said", "told", "got", "get", "go", "went", "come", "came",
              "know", "time", "people", "one", "would", "even", "back", "trader", "joe", "joes", "whole", "foods"]
stop = list(ENGLISH_STOP_WORDS.union(extra_stop))

low_df = rev.loc[low_mask, ["rid", "service_type"]].reset_index(drop=True)
low_df["topic"] = -1
rows, reps_out = [], []
for st in C.SERVICE_TYPES:
    m = (low_df.service_type == st).to_numpy()
    d_st = [docs[i] for i in np.flatnonzero(m)]
    umap_model = UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=C.SEED)
    hdb = HDBSCAN(min_cluster_size=20, min_samples=5, metric="euclidean", cluster_selection_method="leaf",
                  prediction_data=True)
    vec = CountVectorizer(stop_words=stop, ngram_range=(1, 2), min_df=4)
    tm = BERTopic(umap_model=umap_model, hdbscan_model=hdb, vectorizer_model=vec, verbose=False)
    t_st, _ = tm.fit_transform(d_st, embeddings=E[m])
    low_df.loc[m, "topic_local"] = t_st
    for t in sorted(set(t_st)):
        words = [w for w, _ in tm.get_topic(t)][:8]
        rows.append({"service_type": st, "topic": t, "size": int((np.array(t_st) == t).sum()),
                     "top_words": ", ".join(words)})
        if t >= 0:
            reps_out.append(f"[{st} {t}] " + " || ".join(r[:120].replace("\n", " ")
                                                         for r in tm.get_representative_docs(t)[:2]))
    print(f"{st}: {len(d_st):,} docs -> {len(set(t_st)) - (-1 in t_st)} topics, "
          f"outliers {np.mean(np.array(t_st) == -1):.0%}")

low_df["topic"] = low_df["service_type"] + "_" + low_df["topic_local"].astype(int).astype(str)
tt = pd.DataFrame(rows)
with pd.option_context("display.max_colwidth", 100, "display.width", 200, "display.max_rows", 200):
    print(tt.to_string(index=False))

tt.to_csv(C.OUT_DIR / "step3a_topics.csv", index=False)
low_df.to_parquet(C.CACHE_DIR / "topic_assignments.parquet", index=False)

# Representative docs printed to console only (short snippets) so a human can name the topics.
print("\n--- 2 representative snippets per topic (console only) ---")
print("\n".join(reps_out))
