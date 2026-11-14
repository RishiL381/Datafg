"""STEP 4: COMBINE physical access (distance) with felt access (what reviews say), per zip code.

Run from repo root:  .venv/bin/python close_not_accessible/src/step4_combine.py

Felt access, built two ways:
  A. STAR RATINGS (does not depend on the aspect labels). Each place's full Google 1-5 star counts
     (`review_distribution`, 100% filled for places with reviews, matches reviews_count) ->
     empirical-Bayes shrunken mean rating and shrunken low-star (1-2 star) share per place.
  B. COMPLAINT ASPECTS (depends on Step 3c). P(aspect | low-star review) pooled per zip and shrunk across
     zips, times the zip's low-star share = estimated share of ALL reviews that complain about that aspect.
     This corrects for the review sample over-representing 1-star reviews (Google "most relevant").
     If Step 3c has not been run on checked labels, the smoke-run predictions are used and every
     aspect column is flagged PRELIMINARY.

Which services count for a zip (DATA DECISION): for each home, the 3 nearest places of each type
(the realistic choice set), averaged over the zip's homes. Unrated places fall back to the type prior.

Writes:
  outputs/zip_summary.csv              one row per zip (Tableau). No addresses, no home or review rows.
  outputs/step4_correlations.csv       Spearman correlations with bootstrap 95% CIs
  outputs/step4_quadrant_equity.csv    quadrant sizes and median rent
  outputs/zip_map.html                 folium backup map (zip centroids colored by quadrant)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.neighbors import BallTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
from aspects import ASPECTS  # noqa: E402

C.set_seeds()
K_NEAREST = 3
STAR_COLS = [f"{i}_star_reviews" for i in range(1, 6)]
QUAD_NAMES = {(True, True): "close+good", (True, False): "close+bad (access mirage)",
              (False, True): "far+good", (False, False): "far+bad"}

# =============================================================== 1. place-level star data
places = pd.read_parquet(C.CACHE_DIR / "places_target.parquet")
raw = pd.read_csv(C.PLACES_CSV, usecols=["place_id", "review_distribution"], dtype=str)
raw = raw[raw.place_id.isin(set(places.place_id))]
dist = pd.DataFrame([json.loads(s) if isinstance(s, str) else {} for s in raw["review_distribution"]],
                    index=raw["place_id"]).reindex(columns=STAR_COLS).fillna(0)
places = places.merge(dist, left_on="place_id", right_index=True, how="left")
places[STAR_COLS] = places[STAR_COLS].fillna(0)
places["n_star"] = places[STAR_COLS].sum(axis=1)
places["sum_star"] = (places[STAR_COLS] * np.arange(1, 6)).sum(axis=1)
places["n_low"] = places["1_star_reviews"] + places["2_star_reviews"]
print(f"places with >= 1 star review: {(places.n_star > 0).mean():.1%}")


# =============================================================== 2. empirical Bayes at place level
def eb_mean_rating(g: pd.DataFrame) -> pd.Series:
    """Normal-normal EB: shrunk = (n*mean + m*mu) / (n + m), m = sigma^2 / tau^2 (method of moments)."""
    r = g[g.n_star > 0]
    means = r.sum_star / r.n_star
    mu = r.sum_star.sum() / r.n_star.sum()
    # within-place per-review variance sigma^2 (pooled), and between-place variance tau^2
    sumsq = (r[STAR_COLS] * np.arange(1, 6) ** 2).sum(axis=1)
    sq = float((sumsq - r.n_star * means ** 2).sum() / r.n_star.sum())
    tau2 = max(float(np.mean((means - mu) ** 2 - sq / r.n_star)), 1e-3)
    m = sq / tau2
    return (g.sum_star + m * mu) / (g.n_star + m)


def eb_beta_binomial(k: pd.Series, n: pd.Series) -> tuple[pd.Series, float, float]:
    """Beta-binomial EB: shrunk = (k + a) / (n + a + b), a,b by method of moments on rows with n > 0."""
    ok = n > 0
    p = (k[ok] / n[ok])
    mu = k[ok].sum() / n[ok].sum()
    var = np.average((p - mu) ** 2, weights=n[ok])
    nbar = n[ok].mean()
    # var(p_hat) ~ mu(1-mu)[1/n + rho(1 - 1/n)]  ->  solve for rho, then a+b = (1-rho)/rho
    rho = np.clip((var / (mu * (1 - mu)) - 1 / nbar) / (1 - 1 / nbar), 1e-4, 0.999)
    ab = (1 - rho) / rho
    a, b = mu * ab, (1 - mu) * ab
    return (k + a) / (n + a + b), a, b


places["eb_rating"] = np.nan
places["eb_low_share"] = np.nan
for st, g in places.groupby("service_type"):
    places.loc[g.index, "eb_rating"] = eb_mean_rating(g)
    shr, a, b = eb_beta_binomial(g.n_low, g.n_star)
    places.loc[g.index, "eb_low_share"] = shr
    print(f"{st:9s}: prior low-star share {a / (a + b):.3f} (strength a+b = {a + b:.1f} reviews)")

# =============================================================== 3. homes -> K nearest places
homes = pd.read_parquet(C.CACHE_DIR / "homes.parquet", columns=["zpid", "zipcode", "latitude", "longitude"])
H = np.radians(homes[["latitude", "longitude"]].to_numpy())
nearest_sets = {}   # service type -> (n_homes x K) array of place row positions
for st in C.SERVICE_TYPES:
    svc = places[places[f"is_{st}"]].reset_index()
    _, idx = BallTree(np.radians(svc[["lat", "lon"]].to_numpy()), metric="haversine").query(H, k=K_NEAREST)
    pos = svc["index"].to_numpy()[idx]                                  # positions in `places`
    nearest_sets[st] = pos
    homes[f"felt_rating_{st}"] = places["eb_rating"].to_numpy()[pos].mean(1)
    homes[f"felt_low_share_{st}"] = places["eb_low_share"].to_numpy()[pos].mean(1)
    homes[f"felt_rating_{st}_k1"] = places["eb_rating"].to_numpy()[pos[:, 0]]
homes["felt_rating"] = homes[[f"felt_rating_{s}" for s in C.SERVICE_TYPES]].mean(1)
homes["felt_low_share"] = homes[[f"felt_low_share_{s}" for s in C.SERVICE_TYPES]].mean(1)
homes["felt_rating_k1"] = homes[[f"felt_rating_{s}_k1" for s in C.SERVICE_TYPES]].mean(1)  # robustness: nearest only

# =============================================================== 4. zip table
z = pd.read_csv(C.OUT_DIR / "step2_zip_physical_access.csv", dtype={"zip": str})
hz = homes.groupby("zipcode").agg(
    lat=("latitude", "mean"), lon=("longitude", "mean"),   # zip centroid of homes (aggregate only)
    **{c: (c, "mean") for c in homes.columns if c.startswith("felt_")})
z = z.merge(hz, left_on="zip", right_index=True, how="left")

# Distance score (DATA DECISION): mean percentile rank of the 3 median distances (0 = closest, 1 = farthest),
# ranked among zips with enough homes so tiny zips don't distort the scale.
main = ~z["low_n"]
for st in C.SERVICE_TYPES:
    z[f"pct_dist_{st}"] = z.loc[main, f"med_dist_{st}_mi"].rank(pct=True)
z["distance_score"] = z[[f"pct_dist_{s}" for s in C.SERVICE_TYPES]].mean(1)

# ---- complaint aspects (B)
asp_path = C.CACHE_DIR / "review_aspects.parquet"
best_json = C.OUT_DIR / "step3c_best_model.json"
if asp_path.exists() and best_json.exists():
    LABEL_STATUS = json.load(open(best_json)).get("label_status", "human_checked")
else:
    asp_path, LABEL_STATUS = C.CACHE_DIR / "smoke" / "review_aspects.parquet", "PRELIMINARY_smoke_unverified"
verified = LABEL_STATUS == "human_checked"
print(f"\naspect labels: {LABEL_STATUS}")
asp = pd.read_parquet(asp_path)
asp_place = asp.groupby("place_id")[ASPECTS].sum()
asp_place["n_low_sampled"] = asp.groupby("place_id").size()
pos_all = np.hstack([nearest_sets[s] for s in C.SERVICE_TYPES])        # homes x (3*K)
pid = places["place_id"].to_numpy()
zip_places = (pd.DataFrame({"zip": np.repeat(homes["zipcode"].to_numpy(), pos_all.shape[1]),
                            "place_id": pid[pos_all.ravel()]}).drop_duplicates())
zp = zip_places.merge(asp_place, left_on="place_id", right_index=True, how="left").fillna(0)
zagg = zp.groupby("zip")[ASPECTS + ["n_low_sampled"]].sum()
for a in ASPECTS:
    shr, _, _ = eb_beta_binomial(zagg[a], zagg["n_low_sampled"])
    zagg[f"p_{a}_given_low"] = shr
z = z.merge(zagg[[f"p_{a}_given_low" for a in ASPECTS] + ["n_low_sampled"]], left_on="zip", right_index=True,
            how="left")
for a in ASPECTS:
    # share of ALL reviews that complain about aspect a = P(low star) x P(a | low star)
    z[f"complaint_rate_{a}"] = z["felt_low_share"] * z[f"p_{a}_given_low"]
z["aspect_labels"] = LABEL_STATUS

# ---- quadrants (non-low_n zips only)
med_d, med_r = z.loc[main, "distance_score"].median(), z.loc[main, "felt_rating"].median()
is_close = z["distance_score"] <= med_d
is_good = z["felt_rating"] >= med_r
z["quadrant"] = [QUAD_NAMES[(c, g)] for c, g in zip(is_close, is_good)]
z.loc[~main, "quadrant"] = "insufficient homes (low_n)"
z["is_close"] = is_close.astype(object).where(main)
z["is_good"] = is_good.astype(object).where(main)

# =============================================================== 5. correlations
rng = np.random.RandomState(C.SEED)


def spearman_ci(x, y, n_boot=2000):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    rho, p = stats.spearmanr(x, y)
    bs = []
    for _ in range(n_boot):
        ix = rng.randint(0, len(x), len(x))
        bs.append(stats.spearmanr(x[ix], y[ix])[0])
    return rho, np.percentile(bs, 2.5), np.percentile(bs, 97.5), p, len(x)


M = z[main]
pairs = [("distance_score", "felt_rating", "zip", "farther vs. avg rating of nearby services"),
         ("distance_score", "felt_low_share", "zip", "farther vs. share of 1-2 star reviews")]
pairs += [("distance_score", "felt_rating_k1", "zip", "robustness: nearest 1 place instead of 3")]
pairs += [(f"med_dist_{s}_mi", f"felt_rating_{s}", "zip", f"{s}: distance vs. rating") for s in C.SERVICE_TYPES]
pairs += [("distance_score", f"complaint_rate_{a}", "zip", f"farther vs. {a} complaints") for a in ASPECTS]
pairs += [("median_rent_zestimate", "felt_rating", "zip", "rent vs. rating (equity)"),
          ("median_rent_zestimate", "distance_score", "zip", "rent vs. distance (equity)"),
          ("median_rent_zestimate", "felt_low_share", "zip", "rent vs. 1-2 star share (equity)")]
pairs += [("median_rent_zestimate", f"complaint_rate_{a}", "zip", f"rent vs. {a} complaints (equity)")
          for a in ASPECTS]
rows = []
for x, y, level, desc in pairs:
    rho, lo, hi, p, n = spearman_ci(M[x], M[y])
    rows.append({"x": x, "y": y, "level": level, "meaning": desc, "spearman_rho": rho, "ci_low": lo,
                 "ci_high": hi, "p_value": p, "n": n,
                 "uses_aspect_labels": "complaint_rate" in y,
                 "aspect_labels": LABEL_STATUS if "complaint_rate" in y else ""})
# robustness: within-county (rank both variables inside each county, so county-wide differences drop out)
wc = M.assign(d=M.groupby("county")["distance_score"].rank(pct=True), r=M.groupby("county")["felt_rating"].rank(pct=True))
rho, lo, hi, p, n = spearman_ci(wc["d"], wc["r"])
rows.append({"x": "distance_score (within-county rank)", "y": "felt_rating (within-county rank)", "level": "zip",
             "meaning": "robustness: within-county", "spearman_rho": rho, "ci_low": lo, "ci_high": hi,
             "p_value": p, "n": n, "uses_aspect_labels": False, "aspect_labels": ""})
for cty, g in M.groupby("county"):
    if len(g) >= 10:
        rho, lo, hi, p, n = spearman_ci(g["distance_score"], g["felt_rating"], n_boot=500)
        rows.append({"x": "distance_score", "y": "felt_rating", "level": f"zip, {cty} only",
                     "meaning": f"by county: {cty}", "spearman_rho": rho, "ci_low": lo, "ci_high": hi,
                     "p_value": p, "n": n, "uses_aspect_labels": False, "aspect_labels": ""})
# home level (n = homes; clustered, so CI is optimistic): distance to nearest vs. rating of nearest
hd = pd.read_parquet(C.CACHE_DIR / "homes.parquet", columns=[f"dist_{s}_mi" for s in C.SERVICE_TYPES])
for s in C.SERVICE_TYPES:
    sub = rng.choice(len(homes), 20000, replace=False)
    rho, lo, hi, p, n = spearman_ci(hd[f"dist_{s}_mi"].to_numpy()[sub], homes[f"felt_rating_{s}_k1"].to_numpy()[sub],
                                    n_boot=300)
    rows.append({"x": f"dist_{s}_mi", "y": f"rating of nearest {s}", "level": "home (20k sample)",
                 "meaning": f"{s}: home distance vs. nearest place's rating", "spearman_rho": rho, "ci_low": lo,
                 "ci_high": hi, "p_value": p, "n": n, "uses_aspect_labels": False, "aspect_labels": ""})
corr = pd.DataFrame(rows)
corr.round(4).to_csv(C.OUT_DIR / "step4_correlations.csv", index=False)

# =============================================================== 6. equity by quadrant
qe = (z[main].groupby("quadrant").agg(n_zips=("zip", "size"), homes=("n_homes", "sum"),
                                      median_rent_zestimate=("median_rent_zestimate", "median"),
                                      median_sale_price=("median_sale_price", "median"),
                                      felt_rating=("felt_rating", "median"),
                                      distance_score=("distance_score", "median"),
                                      **{f"complaint_rate_{a}": (f"complaint_rate_{a}", "median") for a in ASPECTS})
      .reset_index())
kw = stats.kruskal(*[g["median_rent_zestimate"].dropna() for _, g in z[main].groupby("quadrant")])
qe.round(4).to_csv(C.OUT_DIR / "step4_quadrant_equity.csv", index=False)

# =============================================================== 7. exports
keep = (["zip", "city", "county", "n_homes", "low_n", "lat", "lon", "quadrant", "distance_score"]
        + [f"med_dist_{s}_mi" for s in C.SERVICE_TYPES] + [f"med_n_{s}_1mi" for s in C.SERVICE_TYPES]
        + [f"share_homes_over_1mi_{s}" for s in C.SERVICE_TYPES]
        + ["felt_rating", "felt_low_share", "felt_rating_k1"] + [f"felt_rating_{s}" for s in C.SERVICE_TYPES]
        + [f"complaint_rate_{a}" for a in ASPECTS] + ["n_low_sampled", "aspect_labels"]
        + ["median_rent_zestimate", "median_rent_listing", "median_sale_price"])
# PRIVACY: a "centroid" of 1-2 homes is basically a home location, so blank lat/lon for low_n zips
# (Tableau can still place every zip from the zip code itself).
z.loc[~main, ["lat", "lon"]] = np.nan
z[keep].round(4).to_csv(C.OUT_DIR / "zip_summary.csv", index=False)

import folium  # noqa: E402

colors = {"close+good": "#2a9d8f", "close+bad (access mirage)": "#e76f51", "far+good": "#8ab17d",
          "far+bad": "#9b2226", "insufficient homes (low_n)": "#adb5bd"}
fm = folium.Map(location=[37.75, -122.25], zoom_start=9, tiles="cartodbpositron")
for r in z.dropna(subset=["lat"]).itertuples():
    folium.CircleMarker(
        [r.lat, r.lon], radius=4 + 8 * np.sqrt(r.n_homes / z.n_homes.max()), color=colors[r.quadrant],
        fill=True, fill_opacity=0.75, weight=1,
        popup=folium.Popup(f"<b>{r.zip} {r.city}</b><br>{r.quadrant}<br>homes: {r.n_homes}<br>"
                           f"distance score: {r.distance_score:.2f}<br>avg rating nearby: {r.felt_rating:.2f}<br>"
                           f"1-2 star share: {r.felt_low_share:.1%}<br>median rent est: ${r.median_rent_zestimate:,.0f}",
                           max_width=260)).add_to(fm)
legend = "".join(f'<div><span style="color:{c}">&#9679;</span> {q}</div>' for q, c in colors.items())
fm.get_root().html.add_child(folium.Element(
    f'<div style="position:fixed;bottom:20px;left:20px;z-index:999;background:white;padding:8px;'
    f'border:1px solid #ccc;font:12px sans-serif"><b>Close &ne; Accessible</b>{legend}</div>'))
fm.save(str(C.OUT_DIR / "zip_map.html"))

# =============================================================== 8. print
pd.set_option("display.width", 200)
print(f"\nzips analyzed: {int(main.sum())} (excluded {int((~main).sum())} low_n)")
print("\nCORRELATIONS (Spearman rho, 95% bootstrap CI):")
print(corr[["meaning", "level", "spearman_rho", "ci_low", "ci_high", "p_value", "n", "aspect_labels"]]
      .round(3).to_string(index=False))
print("\nQUADRANTS x EQUITY:")
print(qe.round(3).to_string(index=False))
print(f"Kruskal-Wallis, rent across quadrants: H = {kw.statistic:.2f}, p = {kw.pvalue:.4f}")
print(f"\nwrote zip_summary.csv, step4_correlations.csv, step4_quadrant_equity.csv, zip_map.html to {C.OUT_DIR}")
