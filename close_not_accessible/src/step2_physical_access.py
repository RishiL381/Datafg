"""STEP 2: PHYSICAL ACCESS

Homes (Zillow) are the proxy for where people live. For every home: distance to the nearest
clinic, pharmacy, and grocery store, plus how many of each are within 1 mile. Then roll up to
zip code (medians). No addresses or home-level rows leave the cache.

Run from repo root:  .venv/bin/python close_not_accessible/src/step2_physical_access.py

Reads:   data/zillow/zillow_part*.csv (streamed, usecols only), outputs/cache/places_target.parquet
Writes:  outputs/step2_zip_physical_access.csv   zip-level table (shareable)
         outputs/cache/homes.parquet             home-level coords + distances (gitignored, never shared)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

C.set_seeds()
EARTH_RADIUS_MI = 3958.8
RADIUS_MI = 1.0
MIN_HOMES_PER_ZIP = 30   # zips with fewer homes are kept but flagged `low_n` (unstable medians)

# DATA DECISION: keep the 9 Bay Area counties (standard ABAG definition). The full parts are already
# Bay Area only (148,005 rows, all kept), but zillow_sample.csv is statewide, so the filter is a guard.
# Caveat: homes = Zillow LISTINGS (50% FOR_RENT, 42% RECENTLY_SOLD, 8% FOR_SALE), not every housing
# unit, so the "where people live" proxy leans toward rentals and recently traded homes.
BAY_COUNTIES = ["Alameda", "Contra Costa", "Marin", "Napa", "San Francisco",
                "San Mateo", "Santa Clara", "Solano", "Sonoma"]
# `county` is added to the requested usecols so we can apply that filter (and use it as "region" later).
USECOLS = C.ZILLOW_COLS + ["county"]
HOMES_CACHE = C.CACHE_DIR / "homes.parquet"


def load_homes() -> pd.DataFrame:
    """Stream the 3 big Zillow parts with usecols only; keep Bay Area rows."""
    if HOMES_CACHE.exists():
        print(f"using cached homes: {HOMES_CACHE.name}")
        return pd.read_parquet(HOMES_CACHE)
    parts, t0, n_raw = [], time.time(), 0
    for f in C.ZILLOW_CSVS:
        for chunk in pd.read_csv(f, usecols=USECOLS, chunksize=50_000, dtype={"zpid": str, "zipcode": str},
                                 on_bad_lines="skip", low_memory=True):
            n_raw += len(chunk)
            county = chunk["county"].astype(str).str.replace(r"\s+County$", "", regex=True).str.strip()
            keep = county.isin(BAY_COUNTIES)
            parts.append(chunk.loc[keep].assign(county=county[keep]))
        print(f"  read {f.name}: cumulative raw rows {n_raw:,} ({time.time() - t0:.0f}s)")
    homes = pd.concat(parts, ignore_index=True)
    print(f"raw rows (all CA): {n_raw:,} -> Bay Area rows: {len(homes):,}")
    homes.attrs["n_raw"] = n_raw
    return homes


def clean_homes(h: pd.DataFrame) -> pd.DataFrame:
    n0 = len(h)
    # DATA DECISION: one row per zpid (the same home can appear in more than one part); keep the first.
    h = h.drop_duplicates("zpid")
    n_dup = n0 - len(h)
    h["latitude"] = pd.to_numeric(h["latitude"], errors="coerce")
    h["longitude"] = pd.to_numeric(h["longitude"], errors="coerce")
    h["price"] = pd.to_numeric(h["price"], errors="coerce")
    h["rentZestimate"] = pd.to_numeric(h["rentZestimate"], errors="coerce")
    h["zipcode"] = h["zipcode"].astype(str).str.extract(r"^(\d{5})")[0]
    # DATA DECISION: drop homes with missing/implausible coords (outside a padded Bay Area box), no zip,
    # or a zip outside the Bay Area ranges 94xxx/95xxx (e.g. one listing tagged 93463 Solvang in San Mateo).
    ok = (h.latitude.between(36.8, 39.0) & h.longitude.between(-123.8, -121.2)
          & h.zipcode.fillna("").str.match(r"^9[45]\d{3}$"))
    h = h[ok].copy()
    print(f"dedup zpid dropped {n_dup:,}; bad coords / no zip dropped {int((~ok).sum()):,}; homes kept {len(h):,}")
    return h


homes = load_homes()
homes = clean_homes(homes)
print("homeStatus mix (all statuses are used as 'where people live'):")
print(homes["homeStatus"].fillna("NA").value_counts().to_string())

# ------------------------------------------------------------------ distances
places = pd.read_parquet(C.CACHE_DIR / "places_target.parquet")
home_rad = np.radians(homes[["latitude", "longitude"]].to_numpy())
for st in C.SERVICE_TYPES:
    svc = places[places[f"is_{st}"]]
    tree = BallTree(np.radians(svc[["lat", "lon"]].to_numpy()), metric="haversine")
    d, _ = tree.query(home_rad, k=1)
    homes[f"dist_{st}_mi"] = d[:, 0] * EARTH_RADIUS_MI
    homes[f"n_{st}_1mi"] = tree.query_radius(home_rad, r=RADIUS_MI / EARTH_RADIUS_MI, count_only=True)
    print(f"{st:9s}: {len(svc):,} places | home median dist {homes[f'dist_{st}_mi'].median():.2f} mi "
          f"| homes >1 mi away {(homes[f'dist_{st}_mi'] > RADIUS_MI).mean():.1%}")

homes.to_parquet(HOMES_CACHE, index=False)  # home-level -> cache only (gitignored)

# ------------------------------------------------------------------ zip roll-up
# DATA DECISION (prices): split by homeStatus before averaging, as the README warns.
#   rent_listing   = FOR_RENT `price` (monthly), kept if $300-$30k/mo
#   sale_price     = FOR_SALE / RECENTLY_SOLD / SOLD `price`, kept if > $10k
#   rent_zestimate = Zillow modeled monthly rent; available for ~90% of ALL homes, so it is the main
#                    rent measure for the equity check (less biased toward what happens to be listed).
homes["rent_listing"] = homes["price"].where(homes.homeStatus.eq("FOR_RENT") & homes.price.between(300, 30_000))
homes["sale_price"] = homes["price"].where(homes.homeStatus.isin(["FOR_SALE", "RECENTLY_SOLD", "SOLD"])
                                           & homes.price.gt(10_000))
homes["rent_zestimate"] = homes["rentZestimate"].where(homes.rentZestimate.between(300, 30_000))

mode = lambda s: s.mode().iat[0] if s.notna().any() else None  # noqa: E731
agg = {"n_homes": ("zpid", "size"), "city": ("city", mode), "county": ("county", mode)}
for st in C.SERVICE_TYPES:
    agg[f"med_dist_{st}_mi"] = (f"dist_{st}_mi", "median")
    agg[f"med_n_{st}_1mi"] = (f"n_{st}_1mi", "median")
agg.update({
    "median_rent_zestimate": ("rent_zestimate", "median"),
    "median_rent_listing": ("rent_listing", "median"),
    "n_rent_listings": ("rent_listing", "count"),
    "median_sale_price": ("sale_price", "median"),
    "n_sales": ("sale_price", "count"),
})
z = homes.groupby("zipcode").agg(**agg)
for st in C.SERVICE_TYPES:
    z[f"share_homes_over_1mi_{st}"] = homes.assign(f=homes[f"dist_{st}_mi"] > RADIUS_MI).groupby("zipcode")["f"].mean()
z["low_n"] = z["n_homes"] < MIN_HOMES_PER_ZIP
z = z.reset_index().rename(columns={"zipcode": "zip"}).round(3)

out = C.OUT_DIR / "step2_zip_physical_access.csv"
z.to_csv(out, index=False)
print(f"\nzips: {len(z):,} ({int(z.low_n.sum())} flagged low_n < {MIN_HOMES_PER_ZIP} homes)")
print(z[~z.low_n][[c for c in z.columns if c.startswith("med_dist")]].describe().round(2).to_string())
print("\nFarthest 8 zips from a clinic (median home distance):")
print(z[~z.low_n].nlargest(8, "med_dist_clinic_mi")[["zip", "city", "county", "n_homes", "med_dist_clinic_mi",
                                                      "med_dist_pharmacy_mi", "med_dist_grocery_mi"]].to_string(index=False))
print(f"\nwrote {out}")
