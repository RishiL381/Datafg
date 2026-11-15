"""SUPERVISION CLIFF: data builder for the school -> youth-space ranker.

Thesis: school ends ~3 PM, but staffed youth spaces (libraries, community / rec centers, after-school programs)
close long before many working parents clock out. Standard maps rank them by distance; we re-rank by whether a kid
can actually be there from 3 PM until the parent is off work.

Light script (pandas + scikit-learn only, ~1 min). Reads data/google_maps/google_maps.csv and, for rent context,
close_not_accessible/outputs/step2_zip_physical_access.csv (Riley's Step 2, committed).

DATA DECISIONS
  - Origins = K-12 schools by main category (elementary / middle / high / charter / catholic / private / montessori /
    special education). Preschools, driving, trade, dance, martial arts etc. are excluded.
  - Destinations = STAFFED youth spaces: public libraries, community centers, recreation centers, after-school
    programs, youth organizations. Playgrounds and parks are excluded: they are unsupervised (and the dataset has
    almost no parks / rec centers / museums: it was filtered to essential services).
  - Hours: per weekday, open time = start of the first range, close = end of the last range. A place "covers" a
    window if it is open by 3:30 PM and still open at clock-out on >= 3 of 5 weekdays. Unknown hours stay unknown.
  - Public / free flag: libraries, community and rec centers, youth orgs = public; after-school programs = may charge,
    unless the name says city / parks / YMCA / Boys & Girls / library.
  - School ZIP is parsed from the address only to join ZIP rent; no address is written out.

Run from repo root:  python supervision_cliff/build_school_data.py
Writes supervision_cliff/outputs/: school_data.js (for index.html), schools_lookup.csv, summary.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)
R_MI = 3958.8
RADIUS_MI, WALK_MI, BUS_MI = 1.5, 0.5, 0.25
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
CLOCK_OUTS = {"5pm": 17 * 60, "6:30pm": 18 * 60 + 30, "8pm": 20 * 60, "10pm": 22 * 60}
DEST_TYPES = ["library", "community_center", "rec_center", "after_school", "youth_org"]


# ------------------------------------------------------------------ hours
def _t(s: str, default_ap: str | None) -> tuple[int | None, str | None]:
    m = re.match(r"\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?", s, re.I)
    if not m:
        return None, None
    h, mm, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or default_ap or "").upper()
    if ap not in ("AM", "PM"):
        return None, None
    return (h % 12 + (12 if ap == "PM" else 0)) * 60 + mm, ap


def span(v) -> tuple[int, int] | None:
    """(open, close) minutes for one day's string; (0, 0) = closed; None = missing/unparseable."""
    if not v:
        return None
    s = str(v)
    if "closed" in s.lower():
        return (0, 0)
    if "24" in s:
        return (0, 1440)
    ranges = [r for r in s.split(",") if r.strip()]
    first, last = re.split(r"[–\-]", ranges[0]), re.split(r"[–\-]", ranges[-1])
    if len(first) < 2 or len(last) < 2:
        return None
    close, ap_c = _t(last[-1], None)
    if close is None:
        return None
    open_, _ = _t(first[0], re.search(r"(AM|PM)", first[1], re.I).group(1) if re.search(r"(AM|PM)", first[1], re.I) else ap_c)
    if open_ is None:
        return None
    if ap_c == "AM" and close <= 5 * 60:      # closes after midnight
        close += 1440
    return (open_, min(close, 1440))


def weekday_window(h) -> tuple[int | None, int | None, int | None]:
    """-> (open by, open until) that hold on >= 3 of 5 weekdays, weekend flag; all None if hours unknown."""
    try:
        d = json.loads(h)
    except (TypeError, ValueError):
        return (None, None, None)
    sp = {k: span(v) for k, v in d.items()}
    if all(v is None for v in sp.values()):
        return (None, None, None)
    days = [sp.get(k) or (0, 0) for k in WEEKDAYS]
    opens = sorted(o if c > o else 9999 for o, c in days)        # 3rd earliest opening
    closes = sorted((c if c > o else -1 for o, c in days), reverse=True)  # 3rd latest closing
    wk = int(any((sp.get(k) or (0, 0))[1] > (sp.get(k) or (0, 0))[0] for k in ("Saturday", "Sunday")))
    return (opens[2] if opens[2] < 9999 else -1, closes[2], wk)


# ------------------------------------------------------------------ places
g = pd.read_csv(REPO / "data" / "google_maps" / "google_maps.csv", low_memory=False,
                usecols=["place_id", "name", "category", "all_categories", "address", "lat", "lon",
                         "rating", "open_hours", "permanently_closed"])
g = g[g["permanently_closed"].astype(str).str.lower() != "true"].dropna(subset=["lat", "lon"])
cat, allc, name = g["category"].fillna(""), g["all_categories"].fillna(""), g["name"].fillna("")

school_rx = r"^(?:elementary|middle|high|charter|catholic|private|public|montessori|special education|boys' high|girls' high) school$|^school$"
schools = g[cat.str.contains(school_rx, case=False)].copy()
schools["level"] = np.select(
    [schools["category"].str.contains("elementary|montessori", case=False),
     schools["category"].str.contains("middle", case=False),
     schools["category"].str.contains("high", case=False)], ["elementary", "middle", "high"], "k12_other")

dtype = np.select(
    [cat.str.contains(r"^(?:public )?library$", case=False),
     cat.str.contains("community center", case=False),
     cat.str.contains("recreation center", case=False) | allc.str.contains("recreation center", case=False),
     cat.str.contains("after school", case=False),
     cat.str.contains("youth", case=False) & ~cat.str.contains("sport|clinic|counsel", case=False)],
    DEST_TYPES, "")
dest = g[dtype != ""].assign(dtype=dtype[dtype != ""]).drop_duplicates("place_id").copy()
public_name = name.loc[dest.index].str.contains(r"city of|parks|recreation|ymca|boys (?:&|and) girls|library|public|county", case=False)
dest["public"] = (dest["dtype"].ne("after_school") | public_name).astype(int)
win = pd.DataFrame(dest["open_hours"].map(weekday_window).tolist(), index=dest.index, columns=["ob", "ou", "we"])
dest = dest.join(win)

bus = g[cat.str.contains(r"bus stop|transit stop|transit station|light rail|train station", case=False)]
btree = BallTree(np.radians(bus[["lat", "lon"]].to_numpy(float)), metric="haversine")
for df in (schools, dest):
    df["bus_mi"] = btree.query(np.radians(df[["lat", "lon"]].to_numpy(float)), k=1)[0].ravel() * R_MI
for df in (schools, dest):
    df["zip"] = df["address"].astype(str).str.extract(r"CA (9[45]\d{3})")[0]

print(f"schools {len(schools):,} | youth spaces {len(dest):,} | bus stops {len(bus):,}")
print(dest.groupby("dtype").agg(n=("dtype", "size"), hours_known=("ou", lambda s: s.notna().mean()),
                                public=("public", "mean")).round(2).to_string())

# ------------------------------------------------------------------ per-school "supervision cliff" stats
dtree = BallTree(np.radians(dest[["lat", "lon"]].to_numpy(float)), metric="haversine")
ind, dist = dtree.query_radius(np.radians(schools[["lat", "lon"]].to_numpy(float)), r=RADIUS_MI / R_MI,
                               return_distance=True)
ob, ou, dbus = dest["ob"].to_numpy(float), dest["ou"].to_numpy(float), dest["bus_mi"].to_numpy()
rows = []
for k, (ix, dd) in enumerate(zip(ind, dist)):
    dd = dd * R_MI
    reach = (dd <= WALK_MI) | ((schools["bus_mi"].iat[k] <= BUS_MI) & (dbus[ix] <= BUS_MI))
    known = ~np.isnan(ou[ix])
    r = {"n_spaces": len(ix), "n_reachable": int(reach.sum()), "n_hours_known": int(known.sum())}
    for lab, t in CLOCK_OUTS.items():
        covers = known & (ob[ix] <= 15 * 60 + 30) & (ob[ix] >= 0) & (ou[ix] >= t)
        r[f"usable_{lab}"] = int((covers & reach).sum())
    rows.append(r)
lk = pd.concat([schools[["name", "level", "zip", "lat", "lon", "bus_mi"]].reset_index(drop=True),
                pd.DataFrame(rows)], axis=1)
zrent = pd.read_csv(REPO / "close_not_accessible/outputs/step2_zip_physical_access.csv", dtype={"zip": str})
zrent = zrent[~zrent["low_n"]][["zip", "median_rent_zestimate"]]
q1, q2 = zrent["median_rent_zestimate"].quantile([1 / 3, 2 / 3])
lk = lk.merge(zrent, on="zip", how="left")
lk["rent_tier"] = pd.cut(lk["median_rent_zestimate"], [0, q1, q2, 1e9], labels=["affordable", "middle", "expensive"])
lk.round({"lat": 5, "lon": 5, "bus_mi": 2}).to_csv(OUT / "schools_lookup.csv", index=False)


def share(df, col):
    return round(float((df[col] > 0).mean() * 100), 1)


summary = {
    "n_schools": len(lk), "n_youth_spaces": len(dest), "radius_mi": RADIUS_MI,
    "spaces_by_type": dest["dtype"].value_counts().to_dict(),
    "pct_hours_known_by_type": (dest.groupby("dtype")["ou"].apply(lambda s: s.notna().mean() * 100)).round(1).to_dict(),
    "pct_open_until_by_type_known_hours": {lab: (dest[dest.ou.notna()].groupby("dtype")["ou"]
                                                 .apply(lambda s, t=t: (s >= t).mean() * 100)).round(1).to_dict()
                                           for lab, t in CLOCK_OUTS.items()},
    "pct_schools_with_any_space_within_radius": share(lk, "n_spaces"),
    "pct_schools_with_usable_space_by_clockout": {lab: share(lk, f"usable_{lab}") for lab in CLOCK_OUTS},
    "by_rent_tier_pct_schools_with_usable_space": {
        t: {"n": int(len(s)), "any_within_radius": share(s, "n_spaces"),
            **{lab: share(s, f"usable_{lab}") for lab in CLOCK_OUTS}}
        for t, s in lk.groupby("rent_tier", observed=True)},
    "rent_tier_cutoffs": {"affordable_max": float(q1), "middle_max": float(q2)},
}
json.dump(summary, open(OUT / "summary.json", "w"), indent=2)
print(json.dumps(summary, indent=2))

# ------------------------------------------------------------------ page data
def n(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else int(v)


data = {
    "types": DEST_TYPES,
    "schools": [{"n": r.name, "lv": r.level, "la": round(r.lat, 5), "lo": round(r.lon, 5), "b": round(r.bus_mi, 2), "z": r.zip if isinstance(r.zip, str) else None}
                for r in schools.itertuples()],
    "spaces": [{"n": r.name, "t": DEST_TYPES.index(r.dtype), "la": round(r.lat, 5), "lo": round(r.lon, 5),
                "ob": n(r.ob), "ou": n(r.ou), "we": n(r.we), "p": int(r.public), "b": round(r.bus_mi, 2),
                "r": None if pd.isna(r.rating) else round(float(r.rating), 1),
                "z": r.zip if isinstance(r.zip, str) else None} for r in dest.itertuples()],
}
(OUT / "school_data.js").write_text("window.SCHOOLS = " + json.dumps(data, separators=(",", ":")) + ";\n")
print(f"wrote {OUT}/school_data.js, schools_lookup.csv, summary.json")
