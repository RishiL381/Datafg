# supervision_cliff: "The Supervision Cliff" (Track 1)

School ends around 3 PM. Libraries, community centers and after-school programs mostly close by 6 PM.
Many working parents get off at 6:30, 8 or 10 PM. Pick a school and a clock-out time: the left list ranks nearby
staffed youth spaces by distance (a standard map), the right list re-ranks them by whether a kid can actually be
there from 3 PM until the parent is off work. A bar chart shows how many reachable spaces are still open at each
half hour from 3 to 10 PM: the "cliff".

## Run (from repo root `Datafg/`)
```bash
.venv/bin/pip install numpy pandas pyarrow scikit-learn      # light; no model
.venv/bin/python supervision_cliff/build_school_data.py       # ~5 s; needs data/google_maps/google_maps.csv
python3 -m http.server 8766 --directory supervision_cliff     # then open http://localhost:8766
```
It also reads Riley's committed `close_not_accessible/outputs/step2_zip_physical_access.csv` for ZIP rent tiers.

## Headline numbers (`outputs/summary.json`)
- 2,529 K-12 schools; 1,358 staffed youth spaces (549 community centers, 436 after-school programs, 316 libraries,
  31 rec centers, 26 youth orgs).
- 94% of schools have a youth space within 1.5 mi. Only **51%** have one a kid can reach that is open 3:30 PM to
  6:30 PM; **40%** to 8 PM; **15%** to 10 PM.
- Equity gap: schools in affordable ZIPs (median rent estimate <= $3,969/mo) vs expensive ZIPs (> $5,092/mo):
  usable space until 6:30 PM **37% vs 69%**; until 8 PM **29% vs 64%**; until 10 PM **6% vs 33%**.
  Check: hours are listed for ~59% of nearby spaces in every rent tier, so the gap is not a missing-data artifact.
  Expensive-ZIP schools also have about twice as many spaces nearby (13.6 vs 6.4).
- Of youth spaces with listed hours, only 6% of after-school programs and 32% of libraries stay open past 8 PM.

## Rules
| Rule | Value |
|---|---|
| Candidate radius | 1.5 mi from the school |
| Covers your hours | open by 3:30 PM and open at least until clock-out, on >= 3 of 5 weekdays |
| Reach (middle / high school) | walk <= 0.5 mi, or a bus stop <= 0.25 mi from both school and place |
| Reach (elementary) | walk <= 0.25 mi only; no solo bus rides |
| Free / public | libraries, community and rec centers, youth orgs; after-school programs only if the name says city, parks, YMCA etc. |

Scoring in the page: 100, minus up to 30 for distance, minus 50 if closed by clock-out, minus 20 if hours are not
listed, minus 15 if it opens after 3:30, minus 45 if unreachable, plus 5 if free or public. Each rule shows as a tag.

## Known limits (for the ethics / limitations slide)
- Parks, rec centers, museums, YMCAs and Boys & Girls Clubs are nearly absent: the Places data was filtered to
  essential services. Destinations are staffed places only.
- Hours are missing for about half of community centers and after-school programs; unknown hours never count as open.
- No bus timetables; straight-line distances; no price data (free/public is a category rule).
- No school enrollment, so schools are not weighted by number of kids.
- No safety scores on purpose: review-based safety ratings are biased against public spaces in lower-income areas.
- Not built yet from the pitch: Indeed clock-out evidence, Zillow 2+ bedroom overlay, Reddit / review waitlist quotes.

## Extra evidence (`extra_stats.py` -> `outputs/extra_stats.json`, `outputs/extend_hours_top5.csv`)
Run after `build_school_data.py`; about 1 minute the first time (reads Indeed + Zillow, then cached).
- **Indeed:** 47,301 hourly, non-degree postings (deduped). Of the 17,745 that list a schedule, **66%** include
  evening, night or weekend shifts (35% evening/night, 56% weekend). Only 37% of postings list a schedule at all,
  so 25% of all hourly non-degree postings are known to need these hours (a floor, not an estimate).
- **2+ bedroom check:** with rent tiers built from 2+ bedroom homes only (affordable <= $4,057/mo,
  expensive > $5,238/mo), the gap holds: usable space until 6:30 PM **36% vs 68%**; until 8 PM **28% vs 64%**.
- *(Earlier draft, superseded: `outputs/extend_hours_top5.csv` mixed libraries and community centers with an
  "until 8 PM" rule. Use the library scenario below.)*

## Statistical tests and the 5-library scenario (`disparity_and_policy.py`, explained in [METHODS.md](METHODS.md))
- **Gap is not chance:** 6:30 PM coverage 37.9% (affordable) vs 69.0% (expensive), 31 pts, 95% CI 20-43 from a
  bootstrap that resamples whole ZIP codes, two-proportion z = 11.9. At 8 PM: 28.6% vs 64.0%, risk ratio 2.24.
- **Not just "more places":** with schools grouped by number of nearby spaces, the Mantel-Haenszel odds ratio is
  2.49 at 8 PM (p = 5e-13). Places near affordable-ZIP schools close earlier (22% vs 40% open until 6:30 PM).
- **Fix:** add 2 hours to the weekday closing time of 5 library branches (greedy pick among 238, counting
  affordable-ZIP schools that gain their first covering space at 6:30 PM and 8 PM, no double counting):

  | # | Library | Now → after | New schools 6:30 PM / 8 PM |
  |---|---|---|---|
  | 1 | Petaluma Regional Library | 6 → 8 PM | 16 / 16 |
  | 2 | El Sobrante Library | 6 → 8 PM | 14 / 15 |
  | 3 | Oakland Public Library: 81st Avenue Branch | 5:30 → 7:30 PM | 21 / 0 |
  | 4 | Pittsburg Library | 6 → 8 PM | 10 / 10 |
  | 5 | Concord Library | 6 → 8 PM | 10 / 10 |

  71 schools gain coverage at 6:30 PM (51 at 8 PM), all in affordable ZIPs. Affordable coverage at 6:30 PM:
  37.9% → 46.9%; gap 31.2 → 22.1 pts. Uses the general reach rule (walk 0.5 mi or bus at both ends).
