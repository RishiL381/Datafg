# How we measured the Supervision Cliff (and how we know the gap is real)

Scripts: `build_school_data.py` (data + coverage), `extra_stats.py` (Indeed, 2+ BR check),
`disparity_and_policy.py` (statistical tests + library policy). Numbers below come from
`outputs/summary.json`, `outputs/extra_stats.json` and `outputs/disparity_tests.json`.

## 1. What counts as "covered"
For every K-12 school (2,529), we look at staffed youth spaces (libraries, community and rec centers, after-school
programs, youth organizations) within **1.5 miles**. A school is **covered until time T** if at least one of them:

1. **is open by 3:30 PM and still open at T** on at least 3 of 5 weekdays (from the Google Maps opening hours), and
2. **is reachable without a car:** within a 0.5 mi walk, or with a bus stop within 0.25 mi of both the school and the place.

Places with no listed hours never count as open, so coverage is a cautious (lower-bound) number.

Distances are great-circle ("as the crow flies") distances computed with a BallTree using the haversine formula.

## 2. The headline gap
We split schools by the median Zillow rent estimate of their ZIP code into thirds:
**affordable** (<= $3,969/mo, 782 schools), middle, and **expensive** (> $5,092/mo, 684 schools).

| Parent off at | Affordable | Expensive | Gap | 95% CI of gap | Risk ratio | p-value |
|---|---|---|---|---|---|---|
| 5 PM | 71.7% | 83.2% | 11.4 pts | 3.5 to 18.5 | 1.16x | 2e-7 |
| **6:30 PM** | **37.9%** | **69.0%** | **31.2 pts** | **20.0 to 42.9** | **1.82x** | **1e-32** |
| 8 PM | 28.6% | 64.0% | 35.4 pts | 24.1 to 46.4 | 2.24x | 5e-42 |
| 10 PM | 5.9% | 33.2% | 27.3 pts | 16.5 to 38.4 | 5.64x | 6e-41 |

**How to read the math**
- **Gap** = expensive share minus affordable share, in percentage points.
- **Risk ratio** = expensive share / affordable share. At 8 PM, a school in an expensive ZIP is 2.24 times as likely to be covered.
- **p-value** (two-proportion z-test): if rent tier had nothing to do with coverage, how likely is a gap this big by
  chance? z = (p_exp - p_aff) / sqrt(p(1-p)(1/n_aff + 1/n_exp)), where p is the pooled share. At 6:30 PM z = 11.9,
  so chance is ruled out.
- **95% CI (cluster bootstrap):** schools in the same ZIP share the same nearby places, so they are not independent.
  We resampled whole ZIP codes 2,000 times and recomputed the gap each time; 95% of the results fall in the range
  shown. Even the low end (20 points at 6:30 PM) is a large gap. This is the more honest uncertainty number.

These shares are recomputed from the exported page data and differ from `summary.json` by under 1 point (coordinates
in the export are rounded to 5 decimals, which moves a few places across the 0.5 mi / 1.5 mi lines).

## 3. Is it just that rich areas have more places?
Expensive-ZIP schools have about twice as many youth spaces nearby (13.6 vs 6.4 on average). To check that the gap
isn't only about counts, we compared schools **with the same number of nearby places**:

| Places within 1.5 mi | Affordable covered to 8 PM | Expensive covered to 8 PM |
|---|---|---|
| 0-4 | 11.1% | 33.3% |
| 5-8 | 28.8% | 47.7% |
| 9-14 | 53.1% | 63.6% |
| 15+ | 81.4% | 94.8% |

Expensive ZIPs are ahead in every group. Combining the groups with the **Mantel-Haenszel** method gives a common odds
ratio of **2.49** at 8 PM (1.91 at 6:30 PM): with the number of nearby places held equal, the odds of being covered
are about 2.5 times higher in an expensive ZIP. The **Cochran-Mantel-Haenszel test** gives p = 5e-13 (8 PM) and
3e-7 (6:30 PM).

**Why:** places in affordable areas close earlier. Of reachable youth spaces with listed hours, the share still open:

| Until | Near affordable-ZIP schools | Near expensive-ZIP schools |
|---|---|---|
| 5 PM | 79% | 86% |
| 6:30 PM | **22%** | **40%** |
| 8 PM | **13%** | **30%** |

So the gap has two causes: fewer places nearby, **and** the places that exist close earlier.

## 4. Checks that it isn't a data artifact
- **Missing hours:** about 59% of nearby spaces list hours in every rent tier, so missing data doesn't explain it.
- **Family housing:** rebuilding tiers from 2+ bedroom homes only gives the same gap (6:30 PM: 36% vs 68%).
- **Parents really work late:** of 17,745 hourly, non-degree Indeed postings that list a schedule, 66% include
  evening, night or weekend shifts.

## 5. The fix: keep five libraries open two hours later
We tried adding 2 hours to the weekday closing time of each of 238 library branches (open by 3:30, hours listed),
and counted schools that would get their **first** covering space at 6:30 PM and at 8 PM. We picked libraries one at
a time ("greedy"), each time choosing the one that adds the most affordable-ZIP schools not already helped, so no
school is counted twice.

| # | Library | Closes now | After | New schools covered at 6:30 PM | at 8 PM |
|---|---|---|---|---|---|
| 1 | Petaluma Regional Library | 6:00 PM | 8:00 PM | 16 | 16 |
| 2 | El Sobrante Library (Contra Costa) | 6:00 PM | 8:00 PM | 14 | 15 |
| 3 | Oakland Public Library: 81st Avenue Branch | 5:30 PM | 7:30 PM | 21 | 0 |
| 4 | Pittsburg Library (Contra Costa) | 6:00 PM | 8:00 PM | 10 | 10 |
| 5 | Concord Library (Contra Costa) | 6:00 PM | 8:00 PM | 10 | 10 |

All five are in affordable ZIPs, and every school they help is in an affordable ZIP.

**Effect:**

| | Affordable before | Affordable after | Expensive | Gap before | Gap after |
|---|---|---|---|---|---|
| 6:30 PM | 37.9% | **46.9%** | 69.0% | 31.2 pts | **22.1 pts** |
| 8 PM | 28.6% | **35.2%** | 64.0% | 35.4 pts | **28.9 pts** |

**71 schools** gain a covering space until 6:30 PM and **51** until 8 PM. That closes about **30% of the 6:30 PM
gap** with 10 extra library hours per weekday in total (5 libraries x 2 hours), using buildings that already exist.

## 6. Limits
- Straight-line distance; no bus timetables; no school enrollment (schools are not weighted by students).
- The coverage rule uses the general reach rule; elementary kids realistically need a closer, walkable place.
- The library effect assumes the branch stays staffed and that families use it; it is a scenario, not a forecast.
- Opening hours come from Google listings and can be out of date.
