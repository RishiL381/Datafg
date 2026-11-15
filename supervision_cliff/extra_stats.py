"""SUPERVISION CLIFF: extra evidence for the slides. Prints and saves 3 results.

1. Indeed: share of Bay Area hourly, non-degree postings that list evening / night / weekend shifts.
2. Zillow 2+ bedroom check: does the affordable-vs-expensive school gap hold when rent tiers are built from
   2+ bedroom (family-size) homes only?
3. "Extend hours" policy pick: the 5 libraries / community centers in affordable ZIPs that, if they stayed open
   2 more hours (to at least 8 PM), would give the most schools their first reachable youth space open until 8 PM.
   Picked greedily, so the 5 together are counted without double-counting schools.

Run from repo root AFTER build_school_data.py:  python supervision_cliff/extra_stats.py
Reads the 2.1 GB Indeed file and 7.4 GB of Zillow once (a few minutes); both are cached in supervision_cliff/cache/.
Writes supervision_cliff/outputs/extra_stats.json and extend_hours_top5.csv
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT, CACHE = HERE / "outputs", HERE / "cache"
CACHE.mkdir(exist_ok=True)
R_MI, WALK_MI, BUS_MI, RADIUS_MI = 3958.8, 0.5, 0.25, 1.5
T8, OPEN_BY = 20 * 60, 15 * 60 + 30
res = {}

# ================================================================== 1. Indeed shift schedules
ip = CACHE / "indeed_small.parquet"
if not ip.exists():
    cols = ["job_title", "company_name", "location", "salary_formatted", "shift_schedule", "description_text"]
    parts = []
    for ch in pd.read_csv(REPO / "data/indeed/indeed_job_listings.csv", usecols=cols, chunksize=20000, low_memory=False):
        d = ch["description_text"].fillna("")
        ch["degree_req"] = d.str.contains(r"bachelor'?s|\bB\.?[AS]\.? (?:degree|in)\b|college degree|degree required|master'?s degree",
                                          case=False, regex=True)
        parts.append(ch.drop(columns="description_text"))
    pd.concat(parts, ignore_index=True).to_parquet(ip, index=False)
jobs = pd.read_parquet(ip).drop_duplicates(["job_title", "company_name", "location"])
# DATA DECISION: hourly = posted pay is per hour; non-degree = description never asks for a bachelor's/college degree.
hourly = jobs["salary_formatted"].fillna("").str.contains(r"hour", case=False)
target = jobs[hourly & ~jobs["degree_req"]]
sched = target["shift_schedule"].fillna("[]").astype(str)
listed = sched.str.strip().ne("[]")
evw = sched.str.contains(r"evening|night|overnight|weekend", case=False)
res["indeed"] = {
    "postings_deduped": int(len(jobs)), "hourly_non_degree": int(len(target)),
    "hourly_non_degree_listing_a_schedule": int(listed.sum()),
    "pct_evening_night_weekend_of_those_listing_a_schedule": round(float(evw[listed].mean() * 100), 1),
    "pct_evening_night_or_overnight_of_listed": round(float(sched[listed].str.contains(r"evening|night|overnight", case=False).mean() * 100), 1),
    "pct_weekend_of_listed": round(float(sched[listed].str.contains("weekend", case=False).mean() * 100), 1),
    "pct_evening_night_weekend_of_all_hourly_non_degree": round(float(evw.mean() * 100), 1),
}

# ================================================================== 2. Zillow 2+ bedroom rent tiers
zp = CACHE / "zillow_2br.parquet"
if not zp.exists():
    cols = ["zipcode", "bedrooms", "homeStatus", "price", "rentZestimate"]
    parts = [ch for f in sorted((REPO / "data/zillow").glob("zillow_part*.csv"))
             for ch in pd.read_csv(f, usecols=cols, chunksize=20000, low_memory=False)]
    z = pd.concat(parts, ignore_index=True)
    z["zip"] = z["zipcode"].astype(str).str.extract(r"(9[45]\d{3})")[0]
    z[["zip", "bedrooms", "homeStatus", "price", "rentZestimate"]].to_parquet(zp, index=False)
z = pd.read_parquet(zp)
z = z[pd.to_numeric(z["bedrooms"], errors="coerce") >= 2].dropna(subset=["zip"])
# DATA DECISION: family rent per ZIP = median rentZestimate of 2+ BR homes (all statuses: more coverage than
# FOR_RENT listings alone); ZIPs with < 30 such homes are dropped.
zr = z.groupby("zip")["rentZestimate"].agg(["median", "size"])
zr = zr[zr["size"] >= 30]["median"].rename("rent_2br")
q1, q2 = zr.quantile([1 / 3, 2 / 3])
tier2 = pd.cut(zr, [0, q1, q2, 1e9], labels=["affordable", "middle", "expensive"]).rename("tier_2br")
lk = pd.read_csv(OUT / "schools_lookup.csv", dtype={"zip": str}).merge(tier2, left_on="zip", right_index=True, how="left")
res["zillow_2br"] = {
    "cutoffs": {"affordable_max": round(float(q1)), "middle_max": round(float(q2))},
    "pct_schools_with_usable_space": {
        t: {"n": int(len(s)), **{lab: round(float((s[f"usable_{lab}"] > 0).mean() * 100), 1)
                                 for lab in ("5pm", "6:30pm", "8pm", "10pm")}}
        for t, s in lk.groupby("tier_2br", observed=True)},
}

# ================================================================== 3. extend-hours policy pick
D = json.loads((OUT / "school_data.js").read_text().split("=", 1)[1].rstrip().rstrip(";"))
S, P = pd.DataFrame(D["schools"]), pd.DataFrame(D["spaces"])
P["type"] = [D["types"][t] for t in P["t"]]
step2 = pd.read_csv(REPO / "close_not_accessible/outputs/step2_zip_physical_access.csv", dtype={"zip": str})
step2 = step2[~step2["low_n"]]
a1, a2 = step2["median_rent_zestimate"].quantile([1 / 3, 2 / 3])
tier = dict(zip(step2["zip"], pd.cut(step2["median_rent_zestimate"], [0, a1, a2, 1e9],
                                     labels=["affordable", "middle", "expensive"]).astype(str)))
S["tier"], P["tier"] = S["z"].map(tier), P["z"].map(tier)


def reachable(si: np.ndarray, pi: np.ndarray, d_mi: np.ndarray) -> np.ndarray:
    """Same rule as the summary: walk <= 0.5 mi, or a bus stop <= 0.25 mi at both ends."""
    return (d_mi <= WALK_MI) | ((S["b"].to_numpy()[si] <= BUS_MI) & (P["b"].to_numpy()[pi] <= BUS_MI))


ob, ou = P["ob"].astype(float).to_numpy(), P["ou"].astype(float).to_numpy()
covers8 = (ob >= 0) & (ob <= OPEN_BY) & (ou >= T8)
# candidates: library / community center in an affordable ZIP, open by 3:30, closes before 8 PM but at or after
# 6 PM (so +2 hours reaches 8 PM)
# DATA DECISION: policy picks must be public buildings a city could fund, so the name must say library /
# community center / rec center (drops private orgs that Google tags "community center").
public_name = P["n"].str.contains(r"library|community cent|recreation|rec cent", case=False)
cand = P.index[P["type"].isin(["library", "community_center"]) & P["tier"].eq("affordable") & public_name
               & (ob >= 0) & (ob <= OPEN_BY) & (ou < T8) & (ou >= T8 - 120)].to_numpy()

tree = BallTree(np.radians(S[["la", "lo"]].to_numpy(float)), metric="haversine")
ptree = BallTree(np.radians(P[["la", "lo"]].to_numpy(float)), metric="haversine")
# schools that today have NO reachable space open until 8 PM
idx, dist = ptree.query_radius(np.radians(S[["la", "lo"]].to_numpy(float)), r=RADIUS_MI / R_MI, return_distance=True)
has8 = np.array([bool((covers8[ix] & reachable(np.full(len(ix), k), ix, dd * R_MI)).any())
                 for k, (ix, dd) in enumerate(zip(idx, dist))])
# for each candidate, which no-coverage schools would it unlock
unlock = {}
for c in cand:
    six, sd = tree.query_radius(np.radians([[P.at[c, "la"], P.at[c, "lo"]]]), r=RADIUS_MI / R_MI, return_distance=True)
    six, sd = six[0], sd[0] * R_MI
    ok = reachable(six, np.full(len(six), c), sd) & ~has8[six]
    unlock[c] = set(six[ok].tolist())
picked, covered, rows = [], set(), []
for rank in range(1, 6):
    best = max(unlock, key=lambda c: (len(unlock[c] - covered), -P.at[c, "ou"]), default=None)
    if best is None or not (unlock[best] - covered):
        break
    new = unlock[best] - covered
    covered |= new
    r = P.loc[best]
    rows.append({"rank": rank, "name": r["n"], "type": r["type"], "zip": r["z"],
                 "closes_now": f"{int(r['ou']) // 60 - 12}:{int(r['ou']) % 60:02d} PM",
                 "new_schools_unlocked": len(new),
                 "of_which_in_affordable_zips": int(S.loc[list(new), "tier"].eq("affordable").sum()),
                 "cumulative_schools": len(covered),
                 "example_schools": "; ".join(S.loc[list(new), "n"].head(3))})
top = pd.DataFrame(rows)
top.to_csv(OUT / "extend_hours_top5.csv", index=False)
res["extend_hours"] = {
    "schools_without_8pm_coverage": int((~has8).sum()), "candidates_considered": int(len(cand)),
    "top5_total_schools_unlocked": int(len(covered)),
    "top5_affordable_zip_schools_unlocked": int(S.loc[list(covered), "tier"].eq("affordable").sum()),
}
json.dump(res, open(OUT / "extra_stats.json", "w"), indent=2)
print(json.dumps(res, indent=2))
print("\nTop 5 'extend hours to 8 PM' picks:")
print(top.to_string(index=False))
