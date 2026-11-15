# The Supervision Cliff

**School ends at 3 PM. Libraries, community centers and after-school programs mostly close by 6. Many Bay Area
parents get off at 6:30, 8 or 10 PM.** Standard maps call a neighborhood "family-friendly" because a library is
nearby. We check whether a kid can actually be there from the end of school until a parent clocks out.

**Live app:** https://rishil381.github.io/Datafg/
2026 Datathon for Social Good · Track 1

## What we found
- 94% of Bay Area K-12 schools have a staffed youth space within 1.5 miles. Only **51%** have one a kid can reach
  that is open until 6:30 PM, and **15%** until 10 PM.
- **The gap is unequal.** Schools in affordable ZIP codes have a reachable space open until 6:30 PM **37%** of the
  time, against **69%** in expensive ZIPs (8 PM: 29% vs 64%). It holds when rent is measured on 2+ bedroom family
  homes only (36% vs 68%), and it is not a missing-data effect: hours are listed for about 59% of spaces in every
  rent tier.
- **Parents' schedules are real:** of hourly, non-degree Bay Area job postings that list a schedule, 66% include
  evening, night or weekend shifts (Indeed).
- **A fixable problem:** keeping three public buildings open two hours later (Roosevelt Community Center in San Jose,
  Petaluma Regional Library, El Sobrante Library) would give 49 more schools their first reachable youth space open
  until 8 PM.

## The app
Pick a school (or a demo example) and your clock-out time. The map shows nearby staffed youth spaces and bus stops; a
bar chart shows how many reachable spaces are still open each half hour from 3 to 10 PM; two lists compare
**ranked by distance** (what a normal map shows) with **ranked by what covers your hours**. Click a place to see how
a kid would get there (walk, or walk-bus-walk). Optional: kid's age, weekend work, free places only.

## Data
Google Maps Places (schools, youth spaces, bus stops, opening hours) and Zillow (rents) from the datathon's Bright
Data datasets; Indeed job postings for shift schedules. Raw data is not in this repo (`scripts/download_data.sh`).

## Run it yourself
```bash
python3.12 -m venv .venv && .venv/bin/pip install numpy pandas pyarrow scikit-learn
bash scripts/download_data.sh                                    # raw data -> data/
.venv/bin/python supervision_cliff/build_school_data.py          # ~5 s
.venv/bin/python supervision_cliff/extra_stats.py                # Indeed + Zillow checks, ~1 min
python3 -m http.server 8766 --directory supervision_cliff        # open http://localhost:8766
```
Method, rules and limitations: [`supervision_cliff/README.md`](supervision_cliff/README.md).

## Ethics and limits
- No "safety" scores: review-based safety ratings penalize public spaces in lower-income areas.
- Opening hours are missing for about half of community centers and after-school programs; unknown hours never count as open.
- Reach uses straight-line distance and a kid who can walk 0.5 mi (0.25 mi for elementary, no solo bus rides). It
  ignores wheelchair access, disabilities, traffic and timetables.
- Parks, rec centers and museums are almost absent from the dataset, so the app covers staffed places only.
- Research demo, not a childcare or safety recommendation. Data may be out of date.

## Repo map
| Folder | What |
|---|---|
| `supervision_cliff/` | **The final project**: data builder, extra stats, the app |
| `close_not_accessible/` | Earlier exploration (Riley): distance to clinics/pharmacies/grocery vs. 1-2 star review complaints |
| `access_gap_mvp/` | Earlier exploration: errands ranker (grocery, pharmacy, clinic, bank) |
| `analysis/` | TF-IDF on low-star reviews (null result: complaints look the same in cheap and expensive ZIPs) |
| `CLAUDE_CHAT.md`, `LOG.md` | Working notes between our AI coding assistants |
