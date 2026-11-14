# Close ≠ Accessible

Bay Area service access measured two ways:
1. **Physical access**: how far homes are from the nearest clinic, pharmacy, and grocery store.
2. **Felt access**: what 1-2 star Google reviews say goes wrong at those places (wait time, cost, staff, language access, hours).

A zip code can be close to services but still badly served (an "access mirage"). We combine both views per zip code and check who lives in each quadrant (rent, income).

## How to run (from repo root `Datafg/`)
```bash
bash scripts/download_data.sh          # raw data -> data/ (gitignored, ~8.2 GB)
python3.12 -m venv .venv && .venv/bin/pip install -r close_not_accessible/requirements.txt
.venv/bin/python close_not_accessible/src/step1_feasibility.py   # ~15 s
.venv/bin/python close_not_accessible/src/step2_physical_access.py  # ~50 s
TOKENIZERS_PARALLELISM=false .venv/bin/python close_not_accessible/src/step3a_topics.py  # ~6 min first run (embeddings)
.venv/bin/python close_not_accessible/src/step3b_make_labels.py
.venv/bin/python close_not_accessible/src/step3c_train.py --accept-llm-labels  # ~20 s (drop the flag once labels are hand-checked)
.venv/bin/python close_not_accessible/src/step4_combine.py  # ~15 s
```
Each step script reads from `data/` and writes to `close_not_accessible/outputs/`. Run them in order.

## Steps
| Step | Script | Status |
|---|---|---|
| 1. Feasibility (filter places, join reviews, count 1-2 star) | `src/step1_feasibility.py` | done: 7,183 low-star reviews (both sources) |
| 2. Physical access (BallTree distances, zip medians) | `src/step2_physical_access.py` | done: `outputs/step2_zip_physical_access.csv` |
| 3a. Complaint themes (BERTopic per service type) | `src/step3a_topics.py` | done: `outputs/step3a_topics.csv` |
| 3b. Label file (500 reviews, LLM pre-labels) | `src/step3b_make_labels.py` | done; Riley accepted the LLM labels as-is (not hand-checked) |
| 3c. Classifiers (keyword baseline, TF-IDF+LR, MiniLM+LR) + error analysis | `src/step3c_train.py` | done on LLM labels accepted without hand check: `outputs/step3c_*.csv` |
| 4. Combine (empirical Bayes, quadrants, equity, map) | `src/step4_combine.py` | done: `outputs/zip_summary.csv`, `outputs/zip_map.html` |

## Data decisions
Documented inline in each script and summarized in `../LOG.md`.
