# Close ≠ Accessible

Bay Area service access measured two ways:
1. **Physical access**: how far homes are from the nearest clinic, pharmacy, and grocery store.
2. **Felt access**: what 1-2 star Google reviews say goes wrong at those places (wait time, cost, staff, language access, hours).

A zip code can be close to services but still badly served (an "access mirage"). We combine both views per zip code and check who lives in each quadrant (rent, income).

## How to run (from repo root `Datafg/`)
```bash
bash scripts/download_data.sh          # raw data -> data/ (gitignored, ~8.2 GB)
python3.12 -m venv .venv && .venv/bin/pip install -r close_not_accessible/requirements.txt
.venv/bin/python close_not_accessible/src/step1_feasibility.py | tee close_not_accessible/outputs/cache/step1_feasibility_log.txt
```
Each step script reads from `data/` and writes to `close_not_accessible/outputs/`. Run them in order.

## Steps
| Step | Script | Status |
|---|---|---|
| 1. Feasibility (filter places, join reviews, count 1-2 star) | `src/step1_feasibility.py` | done, below 1,500 gate; waiting on review-source decision |
| 2. Physical access (BallTree distances, zip medians) | `src/step2_physical_access.py` | not started |
| 3. Felt access (themes, labels, classifiers) | `src/step3_*` | not started |
| 4. Combine (empirical Bayes, quadrants, equity, map) | `src/step4_combine.py` | not started |

## Data decisions
Documented inline in each script and summarized in `../LOG.md`.
