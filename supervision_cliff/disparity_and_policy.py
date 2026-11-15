"""SUPERVISION CLIFF: is the gap real, and which 5 libraries should stay open 2 hours later?

Part A (disparity tests), unit = school, outcome = "has >= 1 reachable youth space open from 3:30 PM until clock-out":
  A1  affordable vs expensive ZIP tiers: shares, difference, risk ratio, two-proportion z-test, and a 95% CI from a
      bootstrap that resamples whole ZIP codes (schools in one ZIP share the same nearby places, so they are not
      independent).
  A2  density control: expensive ZIPs have more places nearby. Stratify schools by number of youth spaces within
      1.5 mi and compute the Mantel-Haenszel common odds ratio + Cochran-Mantel-Haenszel test (is the gap still
      there among schools with the same number of nearby places?).
  A3  mechanism: among reachable spaces with listed hours, what share stay open until 6:30 / 8 PM, by tier?
      (Do places in affordable areas close earlier, or are there just fewer of them?)
Part B (policy): extend each library's weekday closing time by 2 hours. Greedily pick the 5 libraries that give the
  most affordable-ZIP schools their first covering space (counting 6:30 PM and 8 PM), and report coverage + gap after.

Same rules as summary.json: 1.5 mi radius; reach = walk <= 0.5 mi or bus stop <= 0.25 mi at both ends; covers =
open by 3:30 PM and open until clock-out on >= 3 of 5 weekdays; unknown hours never count.
Light: reads only outputs/school_data.js and Riley's committed Step 2 ZIP table. Runs in a few seconds.
    python supervision_cliff/disparity_and_policy.py
Writes outputs/disparity_tests.json, outputs/library_extend_top5.csv
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = HERE / "outputs"
R_MI, RADIUS, WALK, BUS, OPEN_BY = 3958.8, 1.5, 0.5, 0.25, 15 * 60 + 30
TIMES = {"5pm": 17 * 60, "6:30pm": 18 * 60 + 30, "8pm": 20 * 60, "10pm": 22 * 60}
rng = np.random.default_rng(42)

D = json.loads((OUT / "school_data.js").read_text().split("=", 1)[1].rstrip().rstrip(";"))
S, P = pd.DataFrame(D["schools"]), pd.DataFrame(D["spaces"])
P["type"] = [D["types"][t] for t in P["t"]]
z = pd.read_csv(REPO / "close_not_accessible/outputs/step2_zip_physical_access.csv", dtype={"zip": str})
z = z[~z["low_n"]]
q1, q2 = z["median_rent_zestimate"].quantile([1 / 3, 2 / 3])
tier_of = dict(zip(z["zip"], pd.cut(z["median_rent_zestimate"], [0, q1, q2, 1e9],
                                    labels=["affordable", "middle", "expensive"]).astype(str)))
S["tier"] = S["z"].map(tier_of)

# ---------------------------------------------------------------- school x space reach pairs (computed once)
st = BallTree(np.radians(S[["la", "lo"]].to_numpy(float)), metric="haversine")
idx, dist = st.query_radius(np.radians(P[["la", "lo"]].to_numpy(float)), r=RADIUS / R_MI, return_distance=True)
pairs = pd.DataFrame({"p": np.repeat(np.arange(len(P)), [len(i) for i in idx]),
                      "s": np.concatenate(idx), "d": np.concatenate(dist) * R_MI})
pairs["reach"] = (pairs["d"] <= WALK) | ((S["b"].to_numpy()[pairs["s"]] <= BUS) & (P["b"].to_numpy()[pairs["p"]] <= BUS))
ob = P["ob"].astype(float).to_numpy()
base_ou = P["ou"].astype(float).to_numpy()


def coverage(ou: np.ndarray) -> pd.DataFrame:
    """Per school: covered at each clock-out (bool), given closing times `ou`."""
    r = pairs[pairs["reach"]]
    pob, pou = ob[r["p"]], ou[r["p"]]
    out = pd.DataFrame(index=S.index)
    for lab, t in TIMES.items():
        ok = (pob >= 0) & (pob <= OPEN_BY) & (pou >= t)
        out[lab] = False
        out.loc[np.unique(r["s"].to_numpy()[ok]), lab] = True
    return out


cov = coverage(base_ou)
S["n_spaces"] = pairs.groupby("s").size().reindex(S.index, fill_value=0)
A, E = S["tier"].eq("affordable"), S["tier"].eq("expensive")


def norm_sf(x: float) -> float:
    return 0.5 * math.erfc(x / math.sqrt(2))


# ================================================================ A1: affordable vs expensive
res = {"tier_cutoffs_rent_per_month": {"affordable_max": round(float(q1)), "middle_max": round(float(q2))},
       "n_schools": {"affordable": int(A.sum()), "expensive": int(E.sum())}, "A1_gap": {}}
zips_a, zips_e = S.loc[A, "z"].unique(), S.loc[E, "z"].unique()
by_zip = {k: g.index.to_numpy() for k, g in S.groupby("z")}
for lab in TIMES:
    y = cov[lab]
    na, ne, xa, xe = int(A.sum()), int(E.sum()), int(y[A].sum()), int(y[E].sum())
    pa, pe = xa / na, xe / ne
    pp = (xa + xe) / (na + ne)
    zstat = (pe - pa) / math.sqrt(pp * (1 - pp) * (1 / na + 1 / ne))
    # cluster bootstrap: resample ZIPs within each tier
    boots = []
    for _ in range(2000):
        ia = np.concatenate([by_zip[k] for k in rng.choice(zips_a, len(zips_a))])
        ie = np.concatenate([by_zip[k] for k in rng.choice(zips_e, len(zips_e))])
        boots.append(y.to_numpy()[ie].mean() - y.to_numpy()[ia].mean())
    res["A1_gap"][lab] = {
        "affordable_pct": round(pa * 100, 1), "expensive_pct": round(pe * 100, 1),
        "gap_pct_points": round((pe - pa) * 100, 1),
        "gap_95ci_cluster_bootstrap": [round(float(np.percentile(boots, 2.5)) * 100, 1), round(float(np.percentile(boots, 97.5)) * 100, 1)],
        "risk_ratio_expensive_vs_affordable": round(pe / pa, 2) if pa else None,
        "z": round(zstat, 2), "p_value_two_sided": float(f"{2 * norm_sf(abs(zstat)):.2e}"),
    }

# ================================================================ A2: same number of nearby places?
bins = [-1, 4, 8, 14, 1e9]
labels = ["0-4", "5-8", "9-14", "15+"]
S["dens"] = pd.cut(S["n_spaces"], bins, labels=labels)
res["A2_density_control"] = {}
for lab in ("6:30pm", "8pm"):
    num = den = 0.0
    cmh_num, cmh_var = 0.0, 0.0
    strata = {}
    for b in labels:
        m = S["dens"].eq(b)
        a_ = int((cov[lab] & E & m).sum()); b_ = int((~cov[lab] & E & m).sum())   # expensive: covered / not
        c_ = int((cov[lab] & A & m).sum()); d_ = int((~cov[lab] & A & m).sum())   # affordable: covered / not
        n = a_ + b_ + c_ + d_
        strata[b] = {"affordable_pct": round(c_ / (c_ + d_) * 100, 1) if c_ + d_ else None,
                     "expensive_pct": round(a_ / (a_ + b_) * 100, 1) if a_ + b_ else None,
                     "n_affordable": c_ + d_, "n_expensive": a_ + b_}
        if n < 2 or (a_ + b_) == 0 or (c_ + d_) == 0:
            continue
        num += a_ * d_ / n; den += b_ * c_ / n
        r1, c1 = a_ + b_, a_ + c_
        cmh_num += a_ - r1 * c1 / n
        cmh_var += r1 * (n - r1) * c1 * (n - c1) / (n * n * (n - 1))
    chi = cmh_num ** 2 / cmh_var
    res["A2_density_control"][lab] = {
        "by_nearby_places": strata,
        "mantel_haenszel_odds_ratio_expensive_vs_affordable": round(num / den, 2),
        "cmh_chi2": round(chi, 1), "p_value": float(f"{2 * norm_sf(math.sqrt(chi)):.2e}"),
    }

# ================================================================ A3: do nearby places close earlier?
rk = pairs[pairs["reach"]].copy()
rk["tier"] = S["tier"].to_numpy()[rk["s"]]
rk = rk[rk["tier"].isin(["affordable", "expensive"]) & ~np.isnan(base_ou[rk["p"]])]
rk = rk.drop_duplicates(["p", "tier"])            # each place counted once per tier
res["A3_share_of_reachable_places_open_until"] = {
    lab: {t: round(float((base_ou[g["p"]] >= tt).mean() * 100), 1) for t, g in rk.groupby("tier")}
    for lab, tt in TIMES.items()}
res["A3_reachable_places_with_hours"] = rk["tier"].value_counts().to_dict()

# ================================================================ B: 5 libraries, +2 hours
# DATA DECISION: branches only (drop library-run programs such as "Project Second Chance" literacy services)
is_branch = ~P["n"].str.contains(r"second chance|literacy|program|bookmobile|friends of", case=False)
libs = P.index[P["type"].eq("library") & is_branch & (ob >= 0) & (ob <= OPEN_BY) & ~np.isnan(base_ou) & (base_ou < 22 * 60)].to_numpy()
cur = base_ou.copy()
cur_cov = cov.copy()
picked = []
for rank in range(1, 6):
    best, best_score, best_cov = None, (-1, -1), None
    for L in libs:
        if L in [p["_i"] for p in picked]:
            continue
        trial = cur.copy(); trial[L] = min(trial[L] + 120, 1440)
        # only schools near this library can change
        near = pairs.loc[(pairs["p"] == L) & pairs["reach"], "s"].to_numpy()
        if not len(near):
            continue
        r = pairs[pairs["s"].isin(near) & pairs["reach"]]
        gain = {}
        for lab in ("6:30pm", "8pm"):
            t = TIMES[lab]
            ok = (ob[r["p"]] >= 0) & (ob[r["p"]] <= OPEN_BY) & (trial[r["p"]] >= t)
            now = set(np.unique(r["s"].to_numpy()[ok]))
            gain[lab] = [s for s in now if not cur_cov.at[s, lab]]
        aff = sum(S.loc[g, "tier"].eq("affordable").sum() for g in gain.values())
        tot = sum(len(g) for g in gain.values())
        if (aff, tot) > best_score:
            best, best_score, best_gain = L, (aff, tot), gain
    if best is None or best_score[1] == 0:
        break
    cur[best] = min(cur[best] + 120, 1440)
    for lab, g in best_gain.items():
        cur_cov.loc[g, lab] = True
    r = P.loc[best]
    fmt = lambda m: f"{int(m) // 60 - 12}:{int(m) % 60:02d} PM" if m < 1440 else "midnight"
    picked.append({"_i": best, "rank": rank, "library": r["n"], "zip": r["z"], "zip_tier": tier_of.get(r["z"], "unknown"),
                   "closes_now": fmt(base_ou[best]), "closes_after": fmt(cur[best]),
                   "new_schools_6:30pm": len(best_gain["6:30pm"]), "new_schools_8pm": len(best_gain["8pm"]),
                   "of_which_affordable_6:30pm": int(S.loc[best_gain["6:30pm"], "tier"].eq("affordable").sum()),
                   "of_which_affordable_8pm": int(S.loc[best_gain["8pm"], "tier"].eq("affordable").sum()),
                   "example_schools": "; ".join(S.loc[best_gain["8pm"] or best_gain["6:30pm"], "n"].head(3))})
top = pd.DataFrame(picked).drop(columns="_i")
top.to_csv(OUT / "library_extend_top5.csv", index=False)
after = {}
for lab in ("6:30pm", "8pm"):
    pa0, pe0 = cov.loc[A, lab].mean(), cov.loc[E, lab].mean()
    pa1, pe1 = cur_cov.loc[A, lab].mean(), cur_cov.loc[E, lab].mean()
    after[lab] = {"affordable_before_pct": round(pa0 * 100, 1), "affordable_after_pct": round(pa1 * 100, 1),
                  "expensive_before_pct": round(pe0 * 100, 1), "expensive_after_pct": round(pe1 * 100, 1),
                  "gap_before_pts": round((pe0 - pa0) * 100, 1), "gap_after_pts": round((pe1 - pa1) * 100, 1),
                  "schools_newly_covered_all_tiers": int((cur_cov[lab] & ~cov[lab]).sum()),
                  "affordable_schools_newly_covered": int((cur_cov[lab] & ~cov[lab] & A).sum())}
res["B_library_plus_2h"] = {"candidate_libraries": int(len(libs)), "effect": after}
json.dump(res, open(OUT / "disparity_tests.json", "w"), indent=2)
print(json.dumps(res, indent=2))
print("\nTop 5 libraries to keep open 2 hours later:")
print(top.to_string(index=False))
