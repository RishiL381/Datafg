"""MVP: "Close Doesn't Count" access-gap engine (Track 1).

For every Bay Area ZIP, score access to 4 pillars (grocery, pharmacy, clinic, bank) two ways:
  RAW    (the Illusion): % of homes with >= 1 place within 1 mile.
  USABLE (the Reality) : % of homes with >= 1 place within 1 mile that
                          - is open until at least 7 PM on >= 3 weekdays (known hours only), AND
                          - is reachable without a car: within a 0.5 mi walk, OR a bus stop within
                            0.25 mi of BOTH the home and the place.
Scores are the mean over pillars, 0-100. gap = raw - usable.

DATA DECISIONS
  - Clinic / grocery / pharmacy lists come from Riley's Step 1 cache (places_target.parquet), so his
    closed-place and specialty-clinic filters apply. Banks and bus stops are read from google_maps.csv.
  - Hours have 3 states: late / not late / UNKNOWN. Unknown-hours places never count as usable in the
    main score. `usable_optimistic` treats unknown as open late, so [usable, usable_optimistic] brackets the truth.
  - Homes = Zillow listings (all statuses) with valid coords and a 94xxx/95xxx zip. ZIPs with < 30 homes get low_n.
  - Output is ZIP-level only (no addresses, no place names).

Run from repo root (after Riley's step1_feasibility.py):
    .venv/bin/python access_gap_mvp/build_access_gap.py
Writes access_gap_mvp/outputs/bay_area_access_gap.csv, summary.json and access_gap_mvp/map.html
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

REPO = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
OUT, CACHE = HERE / "outputs", HERE / "cache"
OUT.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
DATA = REPO / "data"
R_MI = 3958.8
NEAR_MI, WALK_MI, BUS_MI = 1.0, 0.5, 0.25
LATE_MIN = 19 * 60          # open until at least 7 PM
PILLARS = ["grocery", "pharmacy", "clinic", "bank"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


# ------------------------------------------------------------------ hours parsing
def close_minutes(v) -> int | None:
    """Closing time in minutes after midnight for one day's string; 24h/after-midnight -> 1440; closed -> -1."""
    if not v:
        return None
    s = str(v)
    if "closed" in s.lower():
        return -1
    if "24" in s:
        return 1440
    end = re.split(r"[–\-]", s.split(",")[-1])[-1].strip()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)", end, re.I)
    if not m:
        return None
    h, mm, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).upper()
    if ap == "AM":
        return 1440 if (h == 12 or h <= 5) else h * 60 + mm   # closes after midnight
    return (12 if h == 12 else h + 12) * 60 + mm


def parse_hours(h) -> tuple[bool, bool, bool]:
    """-> (known, late_weekdays, open_weekend)"""
    try:
        d = json.loads(h)
    except (TypeError, ValueError):
        return (False, False, False)
    mins = {k: close_minutes(v) for k, v in d.items()}
    if all(v is None for v in mins.values()):
        return (False, False, False)
    late = sum((mins.get(k) or -1) >= LATE_MIN for k in WEEKDAYS) >= 3
    wkend = any((mins.get(k) or -1) > 0 for k in ("Saturday", "Sunday"))
    return (True, late, wkend)


# ------------------------------------------------------------------ places
g = pd.read_csv(DATA / "google_maps" / "google_maps.csv", low_memory=False,
                usecols=["place_id", "category", "lat", "lon", "open_hours", "permanently_closed"])
g = g[g["permanently_closed"].astype(str).str.lower() != "true"].dropna(subset=["lat", "lon"])
cat = g["category"].fillna("")
bus = g[cat.str.contains(r"bus stop|transit stop|transit station|light rail|train station", case=False)]
bank = g[cat.str.contains(r"^bank$|credit union", case=False)].assign(pillar="bank")
tgt = pd.read_parquet(REPO / "close_not_accessible/outputs/cache/places_target.parquet",
                      columns=["place_id", "service_type"]).rename(columns={"service_type": "pillar"})
tgt = tgt.merge(g[["place_id", "lat", "lon", "open_hours"]], on="place_id")
places = pd.concat([tgt, bank[["place_id", "pillar", "lat", "lon", "open_hours"]]], ignore_index=True)
places = places.drop_duplicates(["place_id", "pillar"])
places[["known", "late", "weekend"]] = pd.DataFrame(places["open_hours"].map(parse_hours).tolist(), index=places.index)


def rad(df, la="lat", lo="lon"):
    return np.radians(df[[la, lo]].to_numpy(float))


bus_tree = BallTree(rad(bus), metric="haversine")
places["near_bus"] = bus_tree.query(rad(places), k=1)[0].ravel() * R_MI <= BUS_MI
print(f"bus stops {len(bus):,}")
print(places.groupby("pillar")[["known", "late", "weekend", "near_bus"]].mean().round(2).assign(
    n=places.groupby("pillar").size()).to_string())

# ------------------------------------------------------------------ homes (cached after first read)
hp = CACHE / "homes.parquet"
if hp.exists():
    homes = pd.read_parquet(hp)
else:
    cols = ["zipcode", "city", "county", "latitude", "longitude", "rentZestimate"]
    parts = [ch for f in sorted((DATA / "zillow").glob("zillow_part*.csv"))
             for ch in pd.read_csv(f, usecols=cols, chunksize=20000, low_memory=False)]
    homes = pd.concat(parts, ignore_index=True)
    homes["zip"] = homes["zipcode"].astype(str).str.extract(r"(\d{5})")[0]
    homes = homes[homes["zip"].str.match(r"9[45]\d{3}", na=False)].dropna(subset=["latitude", "longitude"])
    homes = homes[homes["latitude"].between(36.8, 39) & homes["longitude"].between(-123.7, -121.2)]
    homes = homes.drop(columns="zipcode").reset_index(drop=True)
    homes.to_parquet(hp, index=False)
print(f"homes {len(homes):,} in {homes['zip'].nunique()} zips")
H = rad(homes, "latitude", "longitude")
homes["home_bus"] = bus_tree.query(H, k=1)[0].ravel() * R_MI <= BUS_MI


# ------------------------------------------------------------------ per-home access flags
def nearest(mask) -> np.ndarray:
    sub = places[mask]
    if len(sub) == 0:
        return np.full(len(homes), np.inf)
    return BallTree(rad(sub), metric="haversine").query(H, k=1)[0].ravel() * R_MI


def reachable(mask) -> np.ndarray:
    """No-car reach: a matching place within WALK_MI, or within NEAR_MI with a bus stop at both ends."""
    return (nearest(mask) <= WALK_MI) | (homes["home_bus"].to_numpy() & (nearest(mask & places["near_bus"]) <= NEAR_MI))


VIEWS = ["raw", "night", "transit", "weekend", "usable", "usable_optimistic"]
for p in PILLARS:
    m = places["pillar"].eq(p)
    late_opt = places["late"] | ~places["known"]
    homes[f"{p}_raw"] = nearest(m) <= NEAR_MI
    homes[f"{p}_night"] = nearest(m & places["late"]) <= NEAR_MI          # hours filter only
    homes[f"{p}_transit"] = reachable(m)                                  # no-car filter only
    homes[f"{p}_weekend"] = nearest(m & places["weekend"]) <= NEAR_MI
    homes[f"{p}_usable"] = reachable(m & places["late"])                  # both filters
    homes[f"{p}_usable_optimistic"] = reachable(m & late_opt)
homes["chain_ready"] = homes["grocery_usable"] & homes["pharmacy_usable"]

# ------------------------------------------------------------------ ZIP table
flag_cols = [f"{p}_{v}" for p in PILLARS for v in VIEWS] + ["chain_ready", "home_bus"]
z = homes.groupby("zip").agg(
    n_homes=("zip", "size"), city=("city", lambda s: s.mode().iat[0] if s.notna().any() else ""),
    county=("county", lambda s: s.mode().iat[0] if s.notna().any() else ""),
    lat=("latitude", "median"), lon=("longitude", "median"), median_rent=("rentZestimate", "median"),
    **{c: (c, "mean") for c in flag_cols})
for v in VIEWS:
    z[f"{v}_score"] = z[[f"{p}_{v}" for p in PILLARS]].mean(axis=1) * 100
z = z.rename(columns={"raw_score": "raw_proximity_score", "usable_score": "usable_access_score"})
z["access_gap"] = z["raw_proximity_score"] - z["usable_access_score"]
hours_loss = z["raw_proximity_score"] - z["night_score"]
transit_loss = z["raw_proximity_score"] - z["transit_score"]
z["primary_barrier"] = np.where(z["access_gap"] < 5, "none (gap < 5)", np.where(hours_loss >= transit_loss, "hours", "transit"))
z["weakest_pillar"] = pd.DataFrame({p: z[f"{p}_raw"] - z[f"{p}_usable"] for p in PILLARS}).idxmax(axis=1)
z["pct_chain_ready"] = z.pop("chain_ready") * 100
z["pct_homes_near_bus"] = z.pop("home_bus") * 100
z["low_n"] = z["n_homes"] < 30
for p in PILLARS:
    for v in VIEWS:
        z[f"{p}_{v}"] *= 100
z = z.round(1).round({"lat": 4, "lon": 4}).reset_index().sort_values("access_gap", ascending=False)
z.to_csv(OUT / "bay_area_access_gap.csv", index=False)

ok = z[~z["low_n"]]
w = ok["n_homes"] / ok["n_homes"].sum()
summary = {
    "n_zips": int(len(z)), "n_zips_reported": int(len(ok)), "n_homes": int(len(homes)), "n_bus_stops": int(len(bus)),
    "home_weighted": {c: round(float((ok[c] * w).sum()), 1) for c in
                      ["raw_proximity_score", "night_score", "transit_score", "weekend_score",
                       "usable_access_score", "usable_optimistic_score", "access_gap", "pct_chain_ready"]},
    "per_pillar_home_weighted": {p: {v: round(float((ok[f"{p}_{v}"] * w).sum()), 1) for v in VIEWS} for p in PILLARS},
    "places": {p: {"n": int(m.sum()), "pct_hours_known": round(float(places.loc[m, "known"].mean() * 100), 1),
                   "pct_late_of_known": round(float(places.loc[m & places.known, "late"].mean() * 100), 1),
                   "pct_weekend_of_known": round(float(places.loc[m & places.known, "weekend"].mean() * 100), 1),
                   "pct_near_bus": round(float(places.loc[m, "near_bus"].mean() * 100), 1)}
               for p in PILLARS for m in [places["pillar"].eq(p)]},
    "primary_barrier_counts": ok["primary_barrier"].value_counts().to_dict(),
    "rent_vs_gap_spearman": round(float(ok[["median_rent", "access_gap"]].corr(method="spearman").iat[0, 1]), 3),
}
json.dump(summary, open(OUT / "summary.json", "w"), indent=2)
print(json.dumps(summary, indent=2))
print("\nTop 12 gaps (>= 30 homes):")
print(ok[["zip", "city", "n_homes", "median_rent", "raw_proximity_score", "usable_access_score", "access_gap",
          "primary_barrier", "weakest_pillar"]].head(12).to_string(index=False))

# ------------------------------------------------------------------ map
keep = ["zip", "city", "county", "n_homes", "lat", "lon", "median_rent", "raw_proximity_score", "night_score",
        "transit_score", "weekend_score", "usable_access_score", "access_gap", "primary_barrier", "weakest_pillar",
        "pct_chain_ready"]
html = (HERE / "map_template.html").read_text().replace("/*DATA*/[]", ok[keep].to_json(orient="records"))
(HERE / "map.html").write_text(html)
print(f"\nwrote {OUT / 'bay_area_access_gap.csv'}, summary.json, {HERE / 'map.html'}")
