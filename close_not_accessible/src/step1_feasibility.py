"""STEP 1: FEASIBILITY

Can we study "felt access" with this data? We need enough 1-2 star reviews of clinics,
pharmacies, and grocery stores that join back to the Places table.

Run from repo root:  .venv/bin/python close_not_accessible/src/step1_feasibility.py

Writes:
  outputs/step1_feasibility_summary.json   aggregate counts only (safe to share)
  outputs/cache/places_target.parquet      row-level, gitignored, input to Steps 2-4
  outputs/cache/reviews_all.parquet        row-level, gitignored, both review sources (input to Step 3)
"""
from __future__ import annotations

import json
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import config as C  # noqa: E402

C.set_seeds()
pd.set_option("display.width", 160, "display.max_colwidth", 60, "display.max_rows", 100)


def hr(title: str) -> None:
    print(f"\n{'=' * 8} {title} {'=' * (70 - len(title))}")


# =============================================================== 1. Places
hr("PLACES")
places = pd.read_csv(C.PLACES_CSV, usecols=C.PLACES_COLS, dtype={"place_id": str})
print(f"raw rows: {len(places):,}")

# DATA DECISION: drop exact duplicate place_ids (keep first) so every place counts once.
n0 = len(places)
places = places.drop_duplicates("place_id")
print(f"duplicate place_id dropped: {n0 - len(places):,}")

# DATA DECISION: drop permanently closed places (they provide no current access).
# Temporarily closed places are KEPT (they still exist) but counted so we can revisit.
to_bool = lambda s: s.astype(str).str.strip().str.lower().eq("true")  # noqa: E731
places["permanently_closed"] = to_bool(places["permanently_closed"])
places["temporarily_closed"] = to_bool(places["temporarily_closed"])
n_closed = int(places["permanently_closed"].sum())
places = places[~places["permanently_closed"]].copy()
print(f"permanently closed dropped: {n_closed:,}  -> open places: {len(places):,}")

# DATA DECISION: service type from main `category` (rules + reasons in config.SERVICE_RULES).
places["service_type"] = places["category"].map(C.match_service)

# DATA DECISION (Riley, 2026-11-14): "clinic" = general / primary / urgent care. Google files many
# specialty programs under "Medical clinic" (imaging, dermatology, spine, blood-draw labs), so drop
# clinics whose NAME looks specialty unless it also looks general (rules in config.py).
spec_mask = places["service_type"].eq("clinic") & places["name"].map(C.is_specialty_clinic_name)
print(f"specialty-named clinics excluded: {int(spec_mask.sum()):,}")
print("  e.g. " + "; ".join(places.loc[spec_mask, "name"].sample(6, random_state=C.SEED)))
places.loc[spec_mask, "service_type"] = None


def has_pharmacy_tag(s: str) -> bool:
    try:
        return "Pharmacy" in json.loads(s)
    except (TypeError, ValueError):
        return False


# Flags (a place can be more than one, e.g. a clinic with an in-house pharmacy). Flags drive
# Step 2 distances; `service_type` (one per place) drives reporting and stratification.
places["is_clinic"] = places["service_type"].eq("clinic")
places["is_grocery"] = places["service_type"].eq("grocery")
places["is_pharmacy"] = places["service_type"].eq("pharmacy") | places["all_categories"].map(has_pharmacy_tag)

target = places[places[["is_clinic", "is_pharmacy", "is_grocery"]].any(axis=1)].copy()
# Places that only carry the Pharmacy tag (main category = e.g. Hospital) get service_type pharmacy for reporting.
target["service_type"] = target["service_type"].fillna("pharmacy")

print("\nTarget places by service_type:")
print(target["service_type"].value_counts().to_string())
print(f"\nflags -> clinic {target.is_clinic.sum():,} | pharmacy {target.is_pharmacy.sum():,} "
      f"| grocery {target.is_grocery.sum():,}")
print(f"temporarily closed among target (kept): {int(target.temporarily_closed.sum()):,}")

print("\nMain categories kept, per service type:")
for st, g in target.groupby("service_type"):
    print(f"  [{st}] " + ", ".join(f"{c} ({n})" for c, n in g["category"].value_counts().items()))

# ---- spot-check 20 rows (stratified so each type shows up). Names are business listings, printed only.
hr("SPOT-CHECK: 20 random kept places")
spot = (target.groupby("service_type").sample(n=7, random_state=C.SEED)
        .head(20)[["service_type", "category", "name", "rating", "reviews_count"]])
print(spot.to_string(index=False))

hr("SPOT-CHECK: 10 random EXCLUDED places whose category mentions clinic/pharm/grocery/market")
near = places[places["service_type"].isna()
              & places["category"].str.contains("clinic|pharm|grocer|market|drug|urgent",
                                                case=False, na=False)]
print(near.sample(min(10, len(near)), random_state=C.SEED)[["category", "name"]].to_string(index=False))

# =============================================================== 2. Reviews
hr("REVIEWS")
rev = pd.read_csv(C.REVIEWS_CSV, usecols=C.REVIEWS_COLS, dtype={"place_id": str, "review_id": str})
print(f"raw rows: {len(rev):,}")

# DATA DECISION: de-duplicate on review_id (same review scraped twice).
n0 = len(rev)
rev = rev.drop_duplicates("review_id")
print(f"duplicate review_id dropped: {n0 - len(rev):,}")

# DATA DECISION: a review needs real text and a 1-5 star rating.
#   Some rows are hotel-style templates like 'Positive: "" Negative: ""' with no words -> treat as empty.
rev["review"] = rev["review"].fillna("").astype(str)
template_empty = rev["review"].str.fullmatch(r'\s*Positive:\s*""\s*Negative:\s*""\s*')
rev.loc[template_empty, "review"] = ""
rev["review_rating"] = pd.to_numeric(rev["review_rating"], errors="coerce")
bad_rating = ~rev["review_rating"].between(1, 5)
no_text = rev["review"].str.strip().eq("")
print(f"empty / template-only text: {int(no_text.sum()):,} | rating not in 1-5: {int(bad_rating.sum()):,}")
rev = rev[~no_text & ~bad_rating].copy()
rev["review_rating"] = rev["review_rating"].astype(int)
print(f"usable reviews: {len(rev):,} across {rev.place_id.nunique():,} places")
print("star distribution (all usable reviews):")
print(rev["review_rating"].value_counts(normalize=True).sort_index().round(3).to_string())

# =============================================================== 3. Join
hr("JOIN reviews -> places on place_id")
all_ids = set(pd.read_csv(C.PLACES_CSV, usecols=["place_id"], dtype=str)["place_id"])
open_ids = set(places["place_id"])
target_ids = set(target["place_id"])
m_any = rev["place_id"].isin(all_ids)
m_open = rev["place_id"].isin(open_ids)
m_tgt = rev["place_id"].isin(target_ids)
print(f"reviews matching ANY place in Places file : {m_any.sum():>7,}  ({m_any.mean():.2%})")
print(f"reviews matching an OPEN place            : {m_open.sum():>7,}  ({m_open.mean():.2%})")
print(f"reviews matching a TARGET place (c/p/g)   : {m_tgt.sum():>7,}  ({m_tgt.mean():.2%})")

# DATA DECISION: inner join -> only reviews of open clinics/pharmacies/grocery stores are kept.
matched = rev[m_tgt].merge(
    target[["place_id", "service_type", "category", "lat", "lon"]], on="place_id", how="inner"
)
cov = target.assign(has_rev=target.place_id.isin(matched.place_id)).groupby("service_type")["has_rev"].agg(["sum", "mean"])
cov.columns = ["places_with_>=1_review", "share_of_places"]
print("\nPlace coverage (how many target places have at least one matched review):")
print(cov.round(3).to_string())

hr("1-2 STAR REVIEWS BY CATEGORY")
matched["low_star"] = matched["review_rating"] <= C.LOW_STAR_MAX
tab = matched.groupby("service_type").agg(
    matched_reviews=("review_rating", "size"),
    low_star_reviews=("low_star", "sum"),
    low_star_share=("low_star", "mean"),
    places_with_low_star=("place_id", lambda s: s[matched.loc[s.index, "low_star"]].nunique()),
)
tab.loc["TOTAL"] = [len(matched), matched.low_star.sum(), matched.low_star.mean(),
                    matched.loc[matched.low_star, "place_id"].nunique()]
tab["low_star_share"] = tab["low_star_share"].astype(float).round(3)
print(tab.to_string())

print("\nStar distribution of matched reviews, by service type (row %):")
print(pd.crosstab(matched.service_type, matched.review_rating, normalize="index").round(3).to_string())

# ---- concentration: does one place / chain dominate the complaints?
low = matched[matched.low_star].copy()
top_place_share = low["place_id"].value_counts(normalize=True).head(10).sum() if len(low) else np.nan
chain = (low["place_name"].str.lower()
         .str.extract(r"(cvs|walgreens|rite aid|safeway|kaiser|sutter|stanford|ucsf|costco|"
                      r"walmart|target|trader joe|whole foods|lucky|99 ranch|foodmaxx|grocery outlet|"
                      r"carbon health|one medical)")[0].fillna("other / independent").rename("chain"))
print(f"\nShare of 1-2 star reviews from the top 10 places: {top_place_share:.1%}")
print("1-2 star reviews by chain (top 12):")
print(chain.value_counts().head(12).to_string())

# ---- text properties that matter for Step 3
words = low["review"].str.split().str.len()
non_ascii = low["review"].map(lambda t: sum(ord(ch) > 127 for ch in t) / max(len(t), 1))
spanish = low["review"].str.contains(r"\b(?:el|la|los|las|muy|pero|para|servicio|atenci[oó]n)\b", case=False)
print(f"\n1-2 star text: median {words.median():.0f} words | <10 words: {(words < 10).mean():.1%} "
      f"| >30% non-ASCII (likely CJK etc.): {(non_ascii > 0.3).mean():.1%} | Spanish-looking: {spanish.mean():.1%}")
print(f"owner responded to 1-2 star: {low['response_of_owner'].notna().mean():.1%}")
dates = pd.to_datetime(low["review_date"], errors="coerce", utc=True)
print(f"review dates: {dates.min():%Y-%m} to {dates.max():%Y-%m} (median {dates.median():%Y-%m})")

# ---- why is the match rate so low? The reviews file is NOT Bay-Area essential services.
print("\nWhy so few matches: most-reviewed places in the reviews file (all businesses):")
print(rev["place_name"].value_counts().head(8).to_string())

# =============================================================== 3b. Second review source
# The Places file has its own `top_reviews` column: a JSON list of up to ~8 reviews per place
# (Google's "most relevant" sort, so NOT a random sample). Each item also carries reviewer_name
# and reviewer_image_url -> PRIVACY: we keep ONLY content, rating, review_date and drop the rest
# while parsing, so those fields never enter a DataFrame.
hr("SECOND SOURCE: top_reviews embedded in the Places file")
emb_raw = pd.read_csv(C.PLACES_CSV, usecols=["place_id", "top_reviews"], dtype=str)
emb_raw = emb_raw[emb_raw["place_id"].isin(target_ids) & emb_raw["top_reviews"].notna()]
emb_rows = []
for pid, js in emb_raw.itertuples(index=False):
    try:
        items = json.loads(js)
    except ValueError:
        continue
    for it in items:
        emb_rows.append((pid, it.get("content"), it.get("rating"), it.get("review_date")))
emb = pd.DataFrame(emb_rows, columns=["place_id", "review", "review_rating", "review_date"])
emb["review"] = emb["review"].fillna("").astype(str)
emb["review_rating"] = pd.to_numeric(emb["review_rating"], errors="coerce")
emb = emb[emb["review"].str.strip().ne("") & emb["review_rating"].between(1, 5)].copy()
emb["review_rating"] = emb["review_rating"].astype(int)
emb = emb.merge(target[["place_id", "service_type", "category", "lat", "lon"]], on="place_id")
emb["source"] = "places_top_reviews"
emb["low_star"] = emb["review_rating"] <= C.LOW_STAR_MAX
# overlap with the reviews file (same place + same text) -> would be dropped as duplicates if we union.
dup = emb.set_index(["place_id", "review"]).index.isin(matched.set_index(["place_id", "review"]).index)
print(f"embedded reviews with text: {len(emb):,} from {emb.place_id.nunique():,} places "
      f"({emb.place_id.nunique() / len(target):.0%} of target places); overlap with reviews file: {int(dup.sum())}")
etab = emb.groupby("service_type").agg(reviews=("low_star", "size"), low_star_reviews=("low_star", "sum"),
                                       low_star_share=("low_star", "mean"),
                                       places_with_low_star=("place_id", lambda s: s[emb.loc[s.index, "low_star"]].nunique()))
etab.loc["TOTAL"] = [len(emb), emb.low_star.sum(), emb.low_star.mean(), emb.loc[emb.low_star, "place_id"].nunique()]
etab["low_star_share"] = etab["low_star_share"].astype(float).round(3)
print(etab.to_string())
elow = emb[emb.low_star]
print(f"embedded 1-2 star: median {elow.review.str.split().str.len().median():.0f} words | "
      f"top-10 places share {elow.place_id.value_counts(normalize=True).head(10).sum():.1%}")
union_low = int(matched.low_star.sum() + (emb.low_star.values & ~dup).sum())
print(f"UNION (reviews file + embedded, deduped) 1-2 star: {union_low:,}")

# =============================================================== 3c. Combined review table (decision: both sources)
# DATA DECISION (Riley, 2026-11-14): use both sources (config.REVIEW_SOURCES). Dedupe on
# (place_id, normalized text) keeping the reviews-file copy (it has response_of_owner).
hr("COMBINED REVIEWS (both sources, deduped)")
matched["source"] = "reviews_file"
keep_cols = ["place_id", "service_type", "category", "lat", "lon", "review", "review_rating",
             "review_date", "response_of_owner", "source", "low_star"]
reviews_all = pd.concat([matched.reindex(columns=keep_cols), emb.reindex(columns=keep_cols)], ignore_index=True)
reviews_all["_key"] = reviews_all["review"].str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
reviews_all = reviews_all.drop_duplicates(["place_id", "_key"]).drop(columns="_key").reset_index(drop=True)
# Stable id for labeling / train-test splits (row order is deterministic given the raw files).
reviews_all.insert(0, "rid", [f"r{i:06d}" for i in range(len(reviews_all))])
atab = pd.crosstab(reviews_all.service_type, reviews_all.source, values=reviews_all.low_star,
                   aggfunc="sum", margins=True).fillna(0).astype(int)
print("1-2 star reviews by service type x source:")
print(atab.to_string())
print(f"all-star reviews: {len(reviews_all):,} | 1-2 star: {int(reviews_all.low_star.sum()):,} "
      f"| places with any review: {reviews_all.place_id.nunique():,}")

# =============================================================== 4. Gate
hr("FEASIBILITY VERDICT")
n_low_file = int(matched["low_star"].sum())
n_low = int(reviews_all["low_star"].sum())
ok = n_low >= C.MIN_LOW_STAR_REVIEWS
print(f"reviews file alone: {n_low_file:,} 1-2 star (below {C.MIN_LOW_STAR_REVIEWS:,}; clinics only).")
print(f"{'PASS' if ok else 'FAIL'}: both sources combined -> {n_low:,} 1-2 star reviews "
      f"(threshold {C.MIN_LOW_STAR_REVIEWS:,}).")
print("Caveat for write-up: places_top_reviews are Google's 'most relevant' reviews (<=8/place), not random.")

# =============================================================== 5. Place zip (for Step 4)
# DATA DECISION: Places has no zip column. Parse the 5-digit CA zip from `address` and keep ONLY
# the zip; the address string itself is never stored.
addr = pd.read_csv(C.PLACES_CSV, usecols=["place_id", "address"], dtype=str)
addr = addr[addr.place_id.isin(target_ids)]
addr["zip"] = addr["address"].str.extract(r"\bCA\s+(9\d{4})\b")[0]
target = target.merge(addr[["place_id", "zip"]], on="place_id", how="left")
print(f"\nplace zip parsed for {target.zip.notna().mean():.1%} of target places")

summary = {
    "places_open": int(len(places)),
    "permanently_closed_dropped": n_closed,
    "specialty_clinics_excluded": int(spec_mask.sum()),
    "target_places": target["service_type"].value_counts().to_dict(),
    "reviews_file_usable": int(len(rev)),
    "reviews_file_match_rate_any_place": round(float(m_any.mean()), 4),
    "reviews_file_match_rate_target_place": round(float(m_tgt.mean()), 4),
    "reviews_file_matched": int(len(matched)),
    "reviews_file_low_star": n_low_file,
    "embedded_top_reviews_with_text": int(len(emb)),
    "embedded_low_star": int(emb.low_star.sum()),
    "combined_reviews": int(len(reviews_all)),
    "combined_low_star": n_low,
    "combined_low_star_by_type": {k: int(v) for k, v in atab["All"].drop("All").items()},
    "review_sources": C.REVIEW_SOURCES,
    "passes_threshold": bool(ok),
    "threshold": C.MIN_LOW_STAR_REVIEWS,
}
(C.OUT_DIR / "step1_feasibility_summary.json").write_text(json.dumps(summary, indent=2))
target.drop(columns=["all_categories"]).to_parquet(C.CACHE_DIR / "places_target.parquet", index=False)
reviews_all.to_parquet(C.CACHE_DIR / "reviews_all.parquet", index=False)  # PII-free, row-level, gitignored
print(f"\nwrote {C.OUT_DIR / 'step1_feasibility_summary.json'}")
print(f"wrote cache: places_target.parquet ({len(target):,}), reviews_all.parquet ({len(reviews_all):,})")
