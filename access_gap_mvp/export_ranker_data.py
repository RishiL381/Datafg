"""Export the small dataset the side-by-side ranker page (ranker.html) loads.

Light script: reads google_maps.csv once (~500 MB), no Zillow, no model. Needs Riley's Step 1 cache
(close_not_accessible/outputs/cache/places_target.parquet) for the vetted clinic / grocery / pharmacy lists.

Per place it keeps only what the ranker needs: name, category, coordinates, the latest time it is open on
>= 3 of 5 weekdays, weekend flag, rating, distance to the nearest bus stop. Business names are public
listings; no reviewer or resident data is exported.

Run from repo root:
    python access_gap_mvp/export_ranker_data.py
Writes access_gap_mvp/outputs/ranker_data.js  (window.RANKER = {...}, loaded by ranker.html)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from hours import day_closes, weekday_close_3of5  # noqa: E402

OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)
R_MI = 3958.8
CATS = ["grocery", "pharmacy", "clinic", "bank", "food_bank"]
# Budget mode heuristic (hand-picked, documented on the limitations slide): lower-price grocery chains.
DISCOUNT = (r"grocery outlet|foodmaxx|food 4 less|food4less|winco|smart & final|smart and final|walmart|"
            r"costco|aldi|foods co|99 cents|dollar tree|family dollar|cardenas|mi pueblo|la superior|target")

g = pd.read_csv(REPO / "data" / "google_maps" / "google_maps.csv", low_memory=False,
                usecols=["place_id", "name", "category", "lat", "lon", "rating", "reviews_count",
                         "open_hours", "permanently_closed"])
g = g[g["permanently_closed"].astype(str).str.lower() != "true"].dropna(subset=["lat", "lon"])
cat = g["category"].fillna("")
bus = g[cat.str.contains(r"bus stop|transit stop|transit station|light rail|train station", case=False)]
bank = g[cat.str.contains(r"^bank$|credit union", case=False)].assign(cat="bank")
food = g[cat.str.contains(r"food bank|food pantry|soup kitchen", case=False)].assign(cat="food_bank")
tgt = pd.read_parquet(REPO / "close_not_accessible/outputs/cache/places_target.parquet",
                      columns=["place_id", "service_type"]).rename(columns={"service_type": "cat"})
tgt = tgt.merge(g.drop(columns=["category", "permanently_closed"]), on="place_id")
cols = ["place_id", "cat", "name", "lat", "lon", "rating", "reviews_count", "open_hours"]
p = pd.concat([tgt[cols], bank[cols], food[cols]], ignore_index=True).drop_duplicates(["place_id", "cat"])

p["wc"] = p["open_hours"].map(weekday_close_3of5)                      # None = hours unknown


def weekend_open(h):
    d = day_closes(h)
    return None if d is None else int(any((d.get(k) or -1) > 0 for k in ("Saturday", "Sunday")))


p["we"] = p["open_hours"].map(weekend_open)
tree = BallTree(np.radians(bus[["lat", "lon"]].to_numpy(float)), metric="haversine")
p["b"] = tree.query(np.radians(p[["lat", "lon"]].to_numpy(float)), k=1)[0].ravel() * R_MI
p["disc"] = p["name"].fillna("").str.contains(DISCOUNT, case=False) & p["cat"].eq("grocery")


def num(v, nd=None):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return round(float(v), nd) if nd is not None else int(v)


places = [{"n": str(r.name_), "c": CATS.index(r.cat), "la": round(r.lat, 5), "lo": round(r.lon, 5),
           "wc": num(r.wc), "we": num(r.we), "r": num(r.rating, 1), "rc": num(r.reviews_count),
           "b": round(float(r.b), 2), "d": int(r.disc)}
          for r in p.rename(columns={"name": "name_"}).itertuples()]

# ZIP lookup for the "What's your ZIP?" box: only if the ZIP table from build_access_gap.py exists.
zips = []
zp = OUT / "bay_area_access_gap.csv"
if zp.exists():
    z = pd.read_csv(zp, dtype={"zip": str})
    z = z[~z["low_n"]]
    zips = [{"z": r.zip, "city": r.city, "la": r.lat, "lo": r.lon, "rent": num(r.median_rent),
             "raw": r.raw_proximity_score, "use": r.usable_access_score} for r in z.itertuples()]

data = {"cats": CATS, "places": places, "zips": zips,
        "bus": np.round(bus[["lat", "lon"]].to_numpy(float), 5).tolist()}
(OUT / "ranker_data.js").write_text("window.RANKER = " + json.dumps(data, separators=(",", ":")) + ";\n")

print(f"places {len(places):,} | bus stops {len(bus):,} | zips {len(zips)}")
print(p.assign(known=p["wc"].notna(), open_7pm=p["wc"].fillna(-1) >= 19 * 60, near_bus=p["b"] <= 0.25)
      .groupby("cat")[["known", "open_7pm", "near_bus", "disc"]].mean().round(2)
      .assign(n=p.groupby("cat").size()).to_string())
print(f"wrote {OUT / 'ranker_data.js'} ({(OUT / 'ranker_data.js').stat().st_size / 1e6:.1f} MB)")
