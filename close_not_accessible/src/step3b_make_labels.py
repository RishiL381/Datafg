"""STEP 3b: LABELING FILE (~500 reviews) for the 5-aspect multi-label classifier

Run from repo root:  .venv/bin/python close_not_accessible/src/step3b_make_labels.py

Sampling (DATA DECISION):
  - population = 1-2 star reviews of target places (both sources), any length
  - 400 "random"   : stratified by service type (150 clinic / 125 grocery / 125 pharmacy)
  - 100 "enriched" : language_access and hours_availability are rare, so a random sample would
                     give too few positives to train or evaluate. We add
                       40 language-keyword hits, 30 from hours/phone BERTopic topics,
                       30 likely non-English reviews (for the error analysis).
    `sample_stratum` records this. Headline test metrics are ALSO reported on the random-only
    subset, because enriched rows were picked partly by keyword and would flatter the keyword baseline.

Pre-labels: if labels/prelabels_llm.csv exists (rid + 5 aspects, written by an LLM reading each
review), they pre-fill the label columns. Riley hand-checks and sets checked=1.

Writes:
  labels/label_template.csv   rid, service_type, stars, stratum, text, 5 aspect columns, checked, notes
  (row-level review text, NO place names / coords / reviewer info; gitignored by default)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
from aspects import ASPECTS, keyword_labels  # noqa: E402

C.set_seeds()
LABEL_DIR = C.IDEA_DIR / "labels"
LABEL_DIR.mkdir(exist_ok=True)
TEMPLATE = LABEL_DIR / "label_template.csv"
PRELABELS = LABEL_DIR / "prelabels_llm.csv"

rev = pd.read_parquet(C.CACHE_DIR / "reviews_all.parquet")
low = rev[rev["low_star"]].copy()
topics = pd.read_parquet(C.CACHE_DIR / "topic_assignments.parquet")[["rid", "topic"]]
low = low.merge(topics, on="rid", how="left")
amap = pd.read_csv(C.OUT_DIR / "step3a_topic_aspect_map.csv")
amap["topic"] = amap["service_type"] + "_" + amap["topic"].astype(str)
low = low.merge(amap[["topic", "aspect"]].rename(columns={"aspect": "topic_aspect"}), on="topic", how="left")

kw = keyword_labels(low["review"])
low["kw_language"] = kw["language_access"].to_numpy()
non_ascii = low["review"].map(lambda t: sum(ord(ch) > 127 for ch in t) / max(len(t), 1))
spanish = low["review"].str.contains(r"\b(?:que|muy|pero|para|servicio|atenci[oó]n|cita|no me)\b", case=False)
low["likely_non_english"] = (non_ascii > 0.3) | spanish

rng = np.random.RandomState(C.SEED)
picked = []
for st, n in {"clinic": 150, "grocery": 125, "pharmacy": 125}.items():
    pool = low[low.service_type == st]
    picked.append(pool.sample(n=n, random_state=rng).assign(sample_stratum="random"))
taken = set(pd.concat(picked)["rid"])


def take(mask: pd.Series, n: int, name: str) -> None:
    pool = low[mask & ~low["rid"].isin(taken)]
    s = pool.sample(n=min(n, len(pool)), random_state=rng).assign(sample_stratum=name)
    taken.update(s["rid"])
    picked.append(s)
    print(f"{name}: {len(s)} (pool {len(pool)})")


take(low["kw_language"].eq(1), 40, "enriched_language_kw")
take(low["topic_aspect"].eq("hours_availability"), 30, "enriched_hours_topic")
take(low["likely_non_english"], 30, "enriched_non_english")

lab = pd.concat(picked, ignore_index=True)
lab = lab.sample(frac=1, random_state=rng).reset_index(drop=True)  # shuffle so strata are mixed for the labeler
out = lab[["rid", "service_type", "review_rating", "sample_stratum", "review"]].rename(
    columns={"review_rating": "stars", "sample_stratum": "stratum", "review": "text"})
for a in ASPECTS:
    out[a] = ""
out["checked"] = ""
out["notes"] = ""

if PRELABELS.exists():
    pre = pd.read_csv(PRELABELS, dtype={"rid": str})
    out = out.drop(columns=ASPECTS).merge(pre[["rid"] + ASPECTS], on="rid", how="left")
    out = out[["rid", "service_type", "stars", "stratum", "text"] + ASPECTS + ["checked", "notes"]]
    print(f"pre-filled from {PRELABELS.name}: {out[ASPECTS[0]].notna().sum()} / {len(out)} rows")

# Never overwrite a template Riley has started checking.
if TEMPLATE.exists():
    old = pd.read_csv(TEMPLATE, dtype=str)
    if old.get("checked", pd.Series(dtype=str)).fillna("").str.strip().ne("").any():
        sys.exit(f"{TEMPLATE} already has checked rows; not overwriting. Move it aside to regenerate.")
out.to_csv(TEMPLATE, index=False)
print(f"\nwrote {TEMPLATE} ({len(out)} rows)")
print(out.groupby(["service_type", "stratum"]).size().unstack(fill_value=0).to_string())
