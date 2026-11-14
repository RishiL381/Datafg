# access_gap_mvp: "Equity Maps" (Close Doesn't Count)

Track 1 MVP. Two things live here:

1. **Side-by-side ranker** (`ranker.html`): pick a starting point and a service. The left list ranks nearby
   places by distance (what a standard map shows). The right list re-ranks the same places by whether you can
   actually use them, based on optional questions.
2. **ZIP access-gap table and heatmap** (`build_access_gap.py` -> `outputs/bay_area_access_gap.csv`, `map.html`):
   an "Illusion" score and a "Reality" score for every Bay Area ZIP.

## Status
**Code is written but has not been run end to end.** Rishi's Mac was too overloaded, so all runs are meant for
the home PC. `hours.py` was unit-tested on sample strings. Expect to fix small bugs on the first real run.

## Run order (from repo root `Datafg/`)
Needs Python 3.12 and the raw data in `data/` (see `scripts/download_data.sh`; on Windows run it in Git Bash,
or copy the `data/` folder over).

```bash
python -m venv .venv
# Windows: .venv\Scripts\pip ...   macOS/Linux: .venv/bin/pip ...
.venv/bin/pip install numpy pandas pyarrow scikit-learn
.venv/bin/python close_not_accessible/src/step1_feasibility.py   # Riley's Step 1: builds places_target.parquet (~15 s)
.venv/bin/python access_gap_mvp/build_access_gap.py              # ZIP table + map.html (reads 7.4 GB of Zillow once, then cached)
.venv/bin/python access_gap_mvp/export_ranker_data.py            # outputs/ranker_data.js for ranker.html (light)
```
Then open `access_gap_mvp/ranker.html` and `access_gap_mvp/map.html` in a browser (they need internet for map tiles).
Run `build_access_gap.py` before `export_ranker_data.py` if you want the ZIP box in the ranker to work;
without it you can still click the map to set a start.

## Files
| File | What it does |
|---|---|
| `hours.py` | Parses Google `open_hours` JSON into closing times. 3 states: open late / not / unknown |
| `build_access_gap.py` | Per-ZIP raw vs usable scores for grocery, pharmacy, clinic, bank; writes CSV, `summary.json`, `map.html` |
| `map_template.html` | Heatmap page template (5 view buttons); the build script injects the data |
| `export_ranker_data.py` | Exports places (with hours, rating, bus distance), bus stops, and ZIP lookups for the ranker |
| `ranker.html` | The side-by-side ranker. All scoring happens in the browser |

## Ranker questions (all optional)
| Question | Effect on the usable-access score |
|---|---|
| When are you free for errands? | Places closed by then lose 50; unknown hours lose 20 |
| How do you get around? | Bus: beyond walking distance needs a bus stop within 0.25 mi at both ends, else lose 45. Walking only: beyond walking distance loses 60 |
| How far will you walk? | Sets walking distance (0.25 / 0.5 / 0.75 mi) |
| I'm on a tight budget | Adds food banks to grocery searches; +10 for food banks and lower-price grocery chains |
| Mark down places rated under 3.0 | Lose 20 |

Base score is 100 minus up to 30 for distance (within a 2-mile candidate radius). Every deduction shows as a
chip next to the place, so the ranking is explainable.

## Known limits (put these on the limitations slide)
- Hours are missing for about 60% of clinics and 65% of food banks. Unknown hours are shown as "Hours not listed"
  and never counted as open.
- No bus timetables: "bus stop at both ends" does not prove a direct route or a short trip.
- Distances are straight-line, not walking routes.
- The lower-price grocer list is a hand-picked list of chain names in `export_ranker_data.py`, not price data.
- The 6:30 PM default is justified by Indeed shift data only at the regional level (not per ZIP).
- Homes are Zillow listings, not all households.
