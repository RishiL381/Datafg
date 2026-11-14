"""TRACK 1: TF-IDF "distinctive complaint words" (no labels, no training).

Question: which words show up unusually often in 1-2 star reviews from one group compared with everyone else?
Groups compared:
  1. service_type  clinic / grocery / pharmacy (each vs the other two)
  2. rent_tier     affordable vs expensive ZIPs (ZIP terciles of median Zillow rent estimate, Step 2 table)
  3. county        each county with >= MIN_GROUP_REVIEWS low-star reviews vs the rest
Also: share of complaints hitting each of the 5 keyword aspects (aspects.py) by rent tier, with 95% CIs.

Method (easy to explain on a slide):
  - TF-IDF (word 1-2 grams, English stop words) fit on all 1-2 star reviews.
  - distinctiveness = mean TF-IDF in the group minus mean TF-IDF in the rest.
  - For each term we also report the plain-English version: "% of complaints in the group that use the word"
    vs "% in the rest", and a chi-square p-value on word presence.
  - NOISE / PRIVACY GUARD: a term must appear in >= MIN_DOCS reviews AND at >= MIN_PLACES different places
    inside the group. This drops doctor/staff names and one-business quirks.

Inputs: close_not_accessible/outputs/cache/{reviews_all,places_target}.parquet (run Riley's Step 1 first)
        close_not_accessible/outputs/step2_zip_physical_access.csv (committed)
Outputs (aggregate only, no review text): analysis/outputs/
  tfidf_distinctive_terms.csv, aspect_share_by_rent_tier.csv, rent_tiers.json

Run from repo root:  .venv/bin/python analysis/tfidf_distinctive_words.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_selection import chi2

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "close_not_accessible" / "src"))
import config as C  # noqa: E402  (Riley's paths + seed)
from aspects import ASPECTS, keyword_labels  # noqa: E402

OUT = REPO / "analysis" / "outputs"
OUT.mkdir(parents=True, exist_ok=True)
TOP_N = 25               # terms kept per group
MIN_DOCS = 15            # term must be in >= 15 reviews in the group
MIN_PLACES = 8           # ... at >= 8 different places in the group
MIN_GROUP_REVIEWS = 200  # smallest county group we report
P_MAX = 0.001            # chi-square cutoff (many terms tested, so strict)

C.set_seeds()

# ------------------------------------------------------------------ data
rev = pd.read_parquet(C.CACHE_DIR / "reviews_all.parquet")
low = rev[rev["low_star"]].copy()
places = pd.read_parquet(C.CACHE_DIR / "places_target.parquet", columns=["place_id", "zip"])
zips = pd.read_csv(C.OUT_DIR / "step2_zip_physical_access.csv", dtype={"zip": str})
low = low.merge(places, on="place_id", how="left")

# DATA DECISION: rent tiers = terciles of ZIP median rent estimate, using only ZIPs with >= 30 homes (low_n False).
zt = zips[~zips["low_n"] & zips["median_rent_zestimate"].notna()].copy()
q1, q2 = zt["median_rent_zestimate"].quantile([1 / 3, 2 / 3])
zt["rent_tier"] = np.where(zt["median_rent_zestimate"] <= q1, "affordable",
                           np.where(zt["median_rent_zestimate"] <= q2, "middle", "expensive"))
low = low.merge(zt[["zip", "county", "rent_tier"]], on="zip", how="left")
print(f"low-star reviews: {len(low):,} | with a rent tier: {low['rent_tier'].notna().sum():,} | "
      f"tier cutoffs: affordable <= ${q1:,.0f}/mo < middle <= ${q2:,.0f}/mo < expensive")
json.dump({"affordable_max_rent": float(q1), "middle_max_rent": float(q2), "n_zips": int(len(zt)),
           "zips_per_tier": zt["rent_tier"].value_counts().to_dict(),
           "reviews_per_tier": low["rent_tier"].value_counts().to_dict()},
          open(OUT / "rent_tiers.json", "w"), indent=2)

# ------------------------------------------------------------------ TF-IDF on all low-star reviews
texts = low["review"].fillna("").tolist()
# DATA DECISION: drop place names (city / county words, "sf", big hospital-system names) so the county lists show
# what people complain about, not where they are. Chain names (cvs, walgreens, safeway) are kept: they are informative.
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS  # noqa: E402
geo = {w.lower() for name in pd.concat([zips["city"], zips["county"]]).dropna().unique()
       for w in str(name).replace("-", " ").split() if len(w) > 2}
geo |= {"sf", "ucsf", "muir", "john", "bay", "area", "valley"}
STOP = sorted(set(ENGLISH_STOP_WORDS) | geo)
vec = TfidfVectorizer(ngram_range=(1, 2), stop_words=STOP, min_df=10, max_df=0.4,
                      sublinear_tf=True, strip_accents="unicode", token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z']+\b")
X = vec.fit_transform(texts).tocsc()
terms = np.array(vec.get_feature_names_out())
present = (X > 0).astype(np.int8).tocsc()
place_codes = pd.factorize(low["place_id"])[0]
print(f"vocabulary: {len(terms):,} terms")


def distinctive(mask: np.ndarray, comparison: str, group: str, rest_mask: np.ndarray | None = None) -> pd.DataFrame:
    """Top terms for rows in `mask` vs rows in `rest_mask` (default: everything else)."""
    rest = ~mask if rest_mask is None else rest_mask
    g_idx, r_idx = np.flatnonzero(mask), np.flatnonzero(rest)
    score = np.asarray(X[g_idx].mean(0)).ravel() - np.asarray(X[r_idx].mean(0)).ravel()
    n_g = np.asarray(present[g_idx].sum(0)).ravel()
    n_r = np.asarray(present[r_idx].sum(0)).ravel()
    both = np.concatenate([g_idx, r_idx])
    y = np.r_[np.ones(len(g_idx)), np.zeros(len(r_idx))]
    _, p = chi2(present[both], y)
    # number of distinct places using each term inside the group
    sub = present[g_idx].tocoo()
    n_places = pd.DataFrame({"t": sub.col, "pl": place_codes[g_idx][sub.row]}).drop_duplicates() \
        .groupby("t").size().reindex(range(len(terms)), fill_value=0).to_numpy()
    df = pd.DataFrame({
        "comparison": comparison, "group": group, "term": terms, "distinctiveness": score,
        "pct_of_group_reviews": n_g / len(g_idx), "pct_of_rest_reviews": n_r / len(r_idx),
        "n_reviews_group": n_g, "n_places_group": n_places, "chi2_p": p,
        "group_size": len(g_idx), "rest_size": len(r_idx),
    })
    df["times_more_common"] = df["pct_of_group_reviews"] / df["pct_of_rest_reviews"].clip(lower=1 / len(r_idx))
    keep = (df.distinctiveness > 0) & (df.n_reviews_group >= MIN_DOCS) & (df.n_places_group >= MIN_PLACES) \
        & (df.chi2_p < P_MAX)
    return df[keep].sort_values("distinctiveness", ascending=False).head(TOP_N)


results = []
for st in sorted(low["service_type"].unique()):
    results.append(distinctive(low["service_type"].eq(st).to_numpy(), "service_type", st))

# rent tier: affordable vs expensive only (middle left out so the contrast is clear)
tier = low["rent_tier"]
for g, other in (("affordable", "expensive"), ("expensive", "affordable")):
    results.append(distinctive(tier.eq(g).to_numpy(), "rent_tier", f"{g} (vs {other})", tier.eq(other).to_numpy()))
# same contrast within each service type, so a different clinic/grocery mix can't drive the result
for st in sorted(low["service_type"].unique()):
    s = low["service_type"].eq(st)
    results.append(distinctive((tier.eq("affordable") & s).to_numpy(), "rent_tier_within_service",
                               f"{st}: affordable (vs expensive)", (tier.eq("expensive") & s).to_numpy()))

for county, n in low["county"].value_counts().items():
    if n >= MIN_GROUP_REVIEWS:
        results.append(distinctive(low["county"].eq(county).to_numpy(), "county", county,
                                   low["county"].notna().to_numpy() & low["county"].ne(county).to_numpy()))

res = pd.concat(results, ignore_index=True)
for c in ("distinctiveness", "pct_of_group_reviews", "pct_of_rest_reviews", "times_more_common"):
    res[c] = res[c].round(4)
res["chi2_p"] = res["chi2_p"].map(lambda v: float(f"{v:.2e}"))
res.to_csv(OUT / "tfidf_distinctive_terms.csv", index=False)

# ------------------------------------------------------------------ keyword aspects by rent tier (with CIs)
kw = keyword_labels(low["review"])
kw.index = low.index


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


rows = []
for st in ["all"] + sorted(low["service_type"].unique()):
    for t in ("affordable", "middle", "expensive"):
        m = tier.eq(t) & (low["service_type"].eq(st) if st != "all" else True)
        n = int(m.sum())
        for a in ASPECTS:
            k = int(kw.loc[m, a].sum())
            lo, hi = wilson(k, n)
            rows.append({"service_type": st, "rent_tier": t, "aspect": a, "n_reviews": n, "n_hits": k,
                         "share": round(k / n, 4) if n else np.nan, "ci_low": round(lo, 4), "ci_high": round(hi, 4)})
asp = pd.DataFrame(rows)
asp.to_csv(OUT / "aspect_share_by_rent_tier.csv", index=False)

# ------------------------------------------------------------------ console summary
pd.set_option("display.width", 200)
show = ["term", "pct_of_group_reviews", "pct_of_rest_reviews", "times_more_common", "n_places_group"]
for (comp, grp), g in res.groupby(["comparison", "group"], sort=False):
    print(f"\n== {comp}: {grp}  (group {g.group_size.iloc[0]:,} reviews vs {g.rest_size.iloc[0]:,})")
    print(g[show].head(12).to_string(index=False))
print("\n== keyword aspect share by rent tier (all services)")
print(asp[asp.service_type == "all"].pivot(index="aspect", columns="rent_tier", values="share")
      [["affordable", "middle", "expensive"]].round(3).to_string())
print(f"\nwrote {OUT / 'tfidf_distinctive_terms.csv'}, aspect_share_by_rent_tier.csv, rent_tiers.json")
