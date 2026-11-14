"""STEP 3c: 5-ASPECT MULTI-LABEL CLASSIFIERS + ERROR ANALYSIS

Models (all scored on the same held-out TEST split, tuned ONLY on VAL). Everything is scikit-learn
logistic regression, so it runs on a laptop CPU in under a minute and is easy to explain:
  1. keyword      baseline (aspects.KEYWORDS), no training
  2. tfidf_lr     TF-IDF (word 1-2 grams + char 2-5 grams) + one logistic regression per aspect
  3. emb_lr       MiniLM sentence embeddings (already computed in Step 3a) + one logistic regression per aspect
(DistilBERT fine-tuning was dropped on 2026-11-14 to keep the project beginner-track friendly.)
Tuning on VAL: regularization C, TF-IDF feature set, and one decision threshold per aspect.
TEST is touched once, at the end.

Run from repo root (after Riley has filled `checked` in labels/label_template.csv):
    .venv/bin/python close_not_accessible/src/step3c_train.py
Use the LLM pre-labels as gold without a hand check (flagged in every output):
    .venv/bin/python close_not_accessible/src/step3c_train.py --accept-llm-labels
Code check on the UNVERIFIED LLM pre-labels (writes only to outputs/cache/smoke/, never real results):
    .venv/bin/python close_not_accessible/src/step3c_train.py --smoke

Writes (real run):
  outputs/step3c_metrics.csv            per model x eval set x aspect: precision, recall, F1, support (+ macro rows)
  outputs/step3c_model_selection.csv    VAL scores for every config tried
  outputs/step3c_error_analysis.csv     best model's TEST errors by service type, county, short, non-English
  outputs/step3c_best_model.json        chosen model, thresholds, split sizes
  outputs/step3c_top_words.csv          words that push each aspect up or down in tfidf_lr (explainability)
  labels/step3c_failures.csv            10 example failures with text (row-level -> gitignored)
  outputs/cache/review_aspects.parquet  aspects for ALL 1-2 star reviews (input to Step 4)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_recall_fscore_support

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
from aspects import ASPECTS, keyword_matrix  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--smoke", action="store_true", help="code check on unverified pre-labels; outputs go to cache/smoke")
ap.add_argument("--accept-llm-labels", action="store_true",
                help="use the LLM pre-labels as gold without a hand check (Riley's call); flagged in every output")
args = ap.parse_args()

C.set_seeds()
LABEL_DIR = C.IDEA_DIR / "labels"
OUT = C.CACHE_DIR / "smoke" if args.smoke else C.OUT_DIR
FAIL_PATH = (OUT if args.smoke else LABEL_DIR) / "step3c_failures.csv"
OUT.mkdir(parents=True, exist_ok=True)
SPLIT_RATIOS = (0.6, 0.2, 0.2)          # train / val / test
THRESH_GRID = np.round(np.arange(0.05, 0.951, 0.05), 2)
MIN_CHECKED = 300

if args.smoke:
    print("#" * 78 + "\n# SMOKE TEST on UNVERIFIED LLM pre-labels: numbers below are NOT results.\n" + "#" * 78)

# =============================================================== 1. labeled data
lab = pd.read_csv(LABEL_DIR / "label_template.csv", dtype={"rid": str, "checked": str})
for a in ASPECTS:
    lab[a] = pd.to_numeric(lab[a], errors="coerce")
if args.smoke:
    lab = lab.dropna(subset=ASPECTS)
    LABEL_STATUS = "smoke_unverified"
elif args.accept_llm_labels:
    # DATA DECISION (Riley, 2026-11-14): accept the 500 LLM pre-labels as gold without a hand check.
    # Test scores therefore measure agreement with the LLM labeler, not human-verified truth.
    lab = lab.dropna(subset=ASPECTS)
    LABEL_STATUS = "llm_labels_accepted_not_hand_checked"
    print("NOTE: gold = LLM pre-labels accepted by Riley without hand check.")
else:
    LABEL_STATUS = "human_checked"
    # DATA DECISION: only rows Riley marked checked=1 count as gold labels.
    lab = lab[lab["checked"].fillna("").str.strip().isin(["1", "1.0", "yes", "y", "x"])].dropna(subset=ASPECTS)
    if len(lab) < MIN_CHECKED:
        sys.exit(f"Only {len(lab)} rows have checked=1 (need >= {MIN_CHECKED}). Finish the hand check first, "
                 f"or run with --smoke to test the code.")
lab[ASPECTS] = lab[ASPECTS].astype(int)
lab = lab.reset_index(drop=True)
Y = lab[ASPECTS].to_numpy()
print(f"gold rows: {len(lab)} | positives per aspect: " + ", ".join(f"{a}={int(Y[:, i].sum())}"
                                                              for i, a in enumerate(ASPECTS)))

# context columns for error analysis (zip -> county via Step 2 table)
rev = pd.read_parquet(C.CACHE_DIR / "reviews_all.parquet", columns=["rid", "place_id"])
places = pd.read_parquet(C.CACHE_DIR / "places_target.parquet", columns=["place_id", "zip"])
zcounty = pd.read_csv(C.OUT_DIR / "step2_zip_physical_access.csv", dtype={"zip": str})[["zip", "county"]]
ctx = rev.merge(places, on="place_id", how="left").merge(zcounty, on="zip", how="left")
lab = lab.merge(ctx[["rid", "county"]], on="rid", how="left")
lab["county"] = lab["county"].fillna("outside 9 counties / unknown")
lab["n_words"] = lab["text"].str.split().str.len()
non_ascii = lab["text"].map(lambda t: sum(ord(ch) > 127 for ch in t) / max(len(t), 1))
spanish = lab["text"].str.contains(r"\b(?:que|muy|pero|para|servicio|atenci[oó]n|cita|no me)\b", case=False)
lab["non_english"] = (non_ascii > 0.3) | spanish
# DATA DECISION: "short" = bottom quartile of word count in the labeled set (< 10 words gave only ~2 test rows).
SHORT_WORDS = int(lab["n_words"].quantile(0.25))
lab["short"] = lab["n_words"] <= SHORT_WORDS
print(f"short review = <= {SHORT_WORDS} words ({lab['short'].mean():.0%} of labeled rows)")


# =============================================================== 2. stratified split
def iterative_stratified_split(M: np.ndarray, ratios, seed: int) -> np.ndarray:
    """Iterative stratification for multi-label data (Sechidis et al. 2011).
    Assigns each row to a fold so every label's positives are spread in proportion to `ratios`."""
    rng = np.random.RandomState(seed)
    n = len(M)
    ratios = np.asarray(ratios, float)
    want_rows = ratios * n
    want_lab = np.outer(ratios, M.sum(0)).astype(float)
    fold = -np.ones(n, int)
    left = np.ones(n, bool)
    while left.any():
        counts = M[left].sum(0)
        if counts.sum() == 0:  # rows with no labels: fill folds by remaining room
            for i in rng.permutation(np.flatnonzero(left)):
                f = int(np.argmax(want_rows)); fold[i] = f; want_rows[f] -= 1
            break
        lbl = int(np.argmin(np.where(counts > 0, counts, np.inf)))  # rarest remaining label first
        for i in rng.permutation(np.flatnonzero(left & (M[:, lbl] == 1))):
            cand = np.flatnonzero(want_lab[:, lbl] == want_lab[:, lbl].max())
            cand = cand[want_rows[cand] == want_rows[cand].max()]
            f = int(rng.choice(cand))
            fold[i] = f; left[i] = False
            want_rows[f] -= 1; want_lab[f] -= M[i]
    return fold


# DATA DECISION: stratify jointly on the 5 aspects AND service type so each split has every
# category and as many rare-aspect positives as possible. Split is fixed by SEED.
strat = np.hstack([Y, pd.get_dummies(lab["service_type"]).to_numpy().astype(int)])
lab["split"] = np.array(["train", "val", "test"])[iterative_stratified_split(strat, SPLIT_RATIOS, C.SEED)]
tr, va, te = (lab["split"].eq(s).to_numpy() for s in ("train", "val", "test"))
print("split sizes:", lab["split"].value_counts().to_dict())
print(pd.DataFrame({s: lab.loc[lab.split == s, ASPECTS].sum() for s in ("train", "val", "test")}).T.to_string())


# =============================================================== 3. helpers
def tune_thresholds(P: np.ndarray, Yv: np.ndarray) -> np.ndarray:
    """Per-aspect threshold that maximizes VAL F1 (0.5 if the aspect has no VAL positives)."""
    th = np.full(P.shape[1], 0.5)
    for j in range(P.shape[1]):
        if Yv[:, j].sum() == 0:
            continue
        scores = [f1_score(Yv[:, j], P[:, j] >= t, zero_division=0) for t in THRESH_GRID]
        th[j] = THRESH_GRID[int(np.argmax(scores))]
    return th


def macro_f1(Yt, Yp) -> float:
    return float(f1_score(Yt, Yp, average="macro", zero_division=0))


def fit_ovr_lr(Xtr, Ytr, Cval):
    """One logistic regression per aspect. class_weight='balanced' handles rare aspects."""
    ms = []
    for j in range(Ytr.shape[1]):
        m = LogisticRegression(C=Cval, class_weight="balanced", max_iter=2000, random_state=C.SEED)
        m.fit(Xtr, Ytr[:, j]) if Ytr[:, j].any() else None
        ms.append(m if Ytr[:, j].any() else None)
    return ms


def predict_ovr(ms, X):
    return np.column_stack([m.predict_proba(X)[:, 1] if m is not None else np.zeros(X.shape[0]) for m in ms])


selection = []          # every VAL config tried
final = {}              # model -> dict(test probs/preds, thresholds, predictor for full set)
texts = lab["text"].tolist()

# =============================================================== 4a. keyword baseline
K = keyword_matrix(texts)
final["keyword"] = {"pred_test": K[te], "pred_val": K[va], "thresholds": None}
selection.append({"model": "keyword", "config": "fixed regexes", "val_macro_f1": macro_f1(Y[va], K[va])})

# =============================================================== 4b. TF-IDF + LR
best = None
for feats in ("word", "word+char"):
    wv = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, strip_accents="unicode")
    cv = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)
    Xw = wv.fit(np.array(texts)[tr]).transform(texts)
    X = hstack([Xw, cv.fit(np.array(texts)[tr]).transform(texts)]).tocsr() if feats == "word+char" else Xw
    for Cval in (0.3, 1, 3, 10, 30):
        ms = fit_ovr_lr(X[tr], Y[tr], Cval)
        Pv = predict_ovr(ms, X[va])
        th = tune_thresholds(Pv, Y[va])
        s = macro_f1(Y[va], Pv >= th)
        selection.append({"model": "tfidf_lr", "config": f"{feats}, C={Cval}", "val_macro_f1": s})
        if best is None or s > best[0]:
            best = (s, feats, Cval, ms, th, X, wv, cv)
s, feats, Cval, ms, th, X, wv, cv = best
final["tfidf_lr"] = {"pred_test": predict_ovr(ms, X[te]) >= th, "pred_val": predict_ovr(ms, X[va]) >= th,
                     "thresholds": th, "config": f"{feats}, C={Cval}",
                     "predict_texts": (lambda T, ms=ms, th=th, feats=feats, wv=wv, cv=cv: predict_ovr(
                         ms, hstack([wv.transform(T), cv.transform(T)]).tocsr() if feats == "word+char"
                         else wv.transform(T)) >= th)}
print(f"tfidf_lr best on VAL: {feats}, C={Cval}, macro-F1 {s:.3f}")

# Explainability (beginner-friendly): the word features with the largest positive / negative weight per aspect.
vocab = np.array(wv.get_feature_names_out())
tw = []
for j, a in enumerate(ASPECTS):
    if ms[j] is None:
        continue
    coef = ms[j].coef_[0][:len(vocab)]                    # first block = word features
    for sign, order in (("+", np.argsort(-coef)[:15]), ("-", np.argsort(coef)[:10])):
        tw += [{"aspect": a, "direction": sign, "rank": k + 1, "term": vocab[i], "weight": round(float(coef[i]), 3)}
               for k, i in enumerate(order)]
top_words = pd.DataFrame(tw)
top_words.to_csv(OUT / "step3c_top_words.csv", index=False)
print("top words per aspect:")
for a in ASPECTS:
    print(f"  {a:18s} " + ", ".join(top_words[(top_words.aspect == a) & (top_words.direction == "+")].term.head(8)))

# =============================================================== 4c. sentence embeddings + LR
emb_all = np.load(C.CACHE_DIR / "emb_minilm.npy")
rid_idx = pd.Series(np.arange(len(rev)), index=rev["rid"])
E = emb_all[rid_idx.loc[lab["rid"]].to_numpy()]
best = None
for Cval in (0.1, 0.3, 1, 3, 10):
    ms = fit_ovr_lr(E[tr], Y[tr], Cval)
    Pv = predict_ovr(ms, E[va])
    th = tune_thresholds(Pv, Y[va])
    s = macro_f1(Y[va], Pv >= th)
    selection.append({"model": "emb_lr", "config": f"MiniLM, C={Cval}", "val_macro_f1": s})
    if best is None or s > best[0]:
        best = (s, Cval, ms, th)
s, Cval, ms, th = best
final["emb_lr"] = {"pred_test": predict_ovr(ms, E[te]) >= th, "pred_val": predict_ovr(ms, E[va]) >= th,
                   "thresholds": th, "config": f"MiniLM, C={Cval}",
                   "predict_rids": (lambda R, ms=ms, th=th: predict_ovr(ms, emb_all[rid_idx.loc[R].to_numpy()]) >= th)}
print(f"emb_lr best on VAL: C={Cval}, macro-F1 {s:.3f}")

# =============================================================== 5. TEST evaluation (once)
rand_te = lab.loc[te, "stratum"].eq("random").to_numpy()
rows = []
for name, d in final.items():
    for eval_set, mask in (("test", np.ones(te.sum(), bool)), ("test_random_only", rand_te)):
        yt, yp = Y[te][mask], np.asarray(d["pred_test"], int)[mask]
        p, r, f, sup = precision_recall_fscore_support(yt, yp, zero_division=0)
        for j, a in enumerate(ASPECTS):
            rows.append({"model": name, "eval_set": eval_set, "aspect": a, "precision": p[j], "recall": r[j],
                         "f1": f[j], "support": int(sup[j])})
        # bootstrap 95% CI for macro-F1 (rows resampled with replacement)
        rng = np.random.RandomState(C.SEED)
        boots = [macro_f1(yt[ix], yp[ix]) for ix in (rng.randint(0, len(yt), len(yt)) for _ in range(1000))]
        rows.append({"model": name, "eval_set": eval_set, "aspect": "MACRO", "precision": p.mean(),
                     "recall": r.mean(), "f1": macro_f1(yt, yp), "support": int(len(yt)),
                     "f1_ci_low": np.percentile(boots, 2.5), "f1_ci_high": np.percentile(boots, 97.5)})
metrics = pd.DataFrame(rows).round(3)
metrics["label_status"] = LABEL_STATUS
metrics.to_csv(OUT / "step3c_metrics.csv", index=False)
pd.DataFrame(selection).round(3).to_csv(OUT / "step3c_model_selection.csv", index=False)

print("\nTEST macro-F1 (95% bootstrap CI):")
print(metrics[metrics.aspect == "MACRO"][["model", "eval_set", "f1", "f1_ci_low", "f1_ci_high", "support"]]
      .to_string(index=False))
print("\nTEST per-aspect precision / recall / F1:")
print(metrics[(metrics.eval_set == "test") & (metrics.aspect != "MACRO")]
      .pivot(index="aspect", columns="model", values=["precision", "recall", "f1"]).round(2).to_string())

# DATA DECISION: the model used downstream is the best by VAL macro-F1 (not test).
val_best = {m: macro_f1(Y[va], np.asarray(d["pred_val"], int)) for m, d in final.items()}
best_name = max(val_best, key=val_best.get)
print(f"\nchosen model (best VAL macro-F1): {best_name} ({val_best[best_name]:.3f})")

# =============================================================== 6. error analysis (best model, TEST)
T = lab[te].copy()
P = np.asarray(final[best_name]["pred_test"], int)
T["n_wrong_aspects"] = (P != Y[te]).sum(1)
groups = []
for col in ("service_type", "county", "short", "non_english", "stratum"):
    for val, g in T.groupby(col):
        ix = T.index.get_indexer(g.index)
        groups.append({"group": col, "value": str(val), "n": len(g),
                       "macro_f1": macro_f1(Y[te][ix], P[ix]) if len(g) >= 5 else np.nan,
                       "exact_match": float((T.loc[g.index, "n_wrong_aspects"] == 0).mean()),
                       "mean_wrong_aspects": float(g["n_wrong_aspects"].mean())})
err = pd.DataFrame(groups).round(3)
err.to_csv(OUT / "step3c_error_analysis.csv", index=False)
print(f"\nerror analysis ({best_name}, TEST; macro_f1 blank when n < 5):")
print(err.to_string(index=False))

# 10 example failures: most aspects wrong first, spread across service types.
fail = T[T.n_wrong_aspects > 0].copy()
fail["true"] = [",".join(a for a, v in zip(ASPECTS, y) if v) or "none" for y in Y[te][T.n_wrong_aspects.to_numpy() > 0]]
fail["pred"] = [",".join(a for a, v in zip(ASPECTS, y) if v) or "none" for y in P[T.n_wrong_aspects.to_numpy() > 0]]
fail = (fail.sort_values(["n_wrong_aspects", "rid"], ascending=[False, True])
        .groupby("service_type", group_keys=False).head(4).head(10))
fail["snippet"] = fail["text"].str.replace(r"\s+", " ", regex=True).str[:160]
fail[["rid", "service_type", "county", "n_words", "non_english", "true", "pred", "snippet"]].to_csv(FAIL_PATH, index=False)
print(f"\n{len(fail)} example failures -> {FAIL_PATH} (row-level text, gitignored)")

# =============================================================== 7. score ALL 1-2 star reviews for Step 4
full = pd.read_parquet(C.CACHE_DIR / "reviews_all.parquet")
low = full[full["low_star"]][["rid", "place_id", "service_type", "review"]].reset_index(drop=True)
d = final[best_name]
if best_name == "keyword":
    pred = keyword_matrix(low["review"])
elif "predict_rids" in d:
    pred = d["predict_rids"](low["rid"])
else:
    pred = d["predict_texts"](low["review"].tolist())
asp = pd.DataFrame(np.asarray(pred, int), columns=ASPECTS)
out_asp = pd.concat([low[["rid", "place_id", "service_type"]], asp], axis=1)
# DATA DECISION: for the 500 hand-checked rows, use the gold label instead of the model prediction.
gold = lab.set_index("rid")[ASPECTS]
hit = out_asp["rid"].isin(gold.index)
out_asp.loc[hit, ASPECTS] = gold.loc[out_asp.loc[hit, "rid"], ASPECTS].to_numpy()
out_asp["label_source"] = np.where(hit, "gold" if LABEL_STATUS == "human_checked" else "llm_label", best_name)
out_asp.to_parquet((C.CACHE_DIR / "smoke" if args.smoke else C.CACHE_DIR) / "review_aspects.parquet", index=False)
print(f"scored {len(out_asp):,} low-star reviews; aspect rates: " +
      ", ".join(f"{a}={out_asp[a].mean():.2f}" for a in ASPECTS))

json.dump({"chosen_model": best_name, "chosen_by": "VAL macro-F1", "val_macro_f1": val_best,
           "configs": {m: d.get("config") for m, d in final.items()},
           "thresholds": {m: (list(map(float, d["thresholds"])) if d["thresholds"] is not None else None)
                          for m, d in final.items()},
           "split_sizes": lab["split"].value_counts().to_dict(), "seed": C.SEED, "smoke": args.smoke,
           "label_status": LABEL_STATUS},
          open(OUT / "step3c_best_model.json", "w"), indent=2)
print(f"wrote metrics/selection/error analysis/best_model to {OUT}")
