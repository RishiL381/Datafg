# Agent Work Log

Running log of what each agent is doing in this repo. **Read this before you start, and update it as you work.**
For short back-and-forth messages between agents, also see `CLAUDE_CHAT.md` (created by Claude-A on Rishi's machine).

## Rules for agents
1. `git pull` before reading. Append new entries at the **bottom** of the Log section; never delete others' entries.
2. Update the **Now** board when you start or finish something, so others know what is in flight and which files you own.
3. Timestamps are local (America/Los_Angeles), `YYYY-MM-DD HH:MM`.
4. Raw data lives in `data/` (gitignored, re-download with `bash scripts/download_data.sh`). Never commit CSVs from `data/`.
5. Privacy: no street addresses, no reviewer names/urls/profile pics in any output. Outputs are zip-level only.

## Repo layout
```
Datafg/
├── LOG.md                    <- this file
├── CLAUDE_CHAT.md            <- agent-to-agent message board (Claude-A)
├── scripts/download_data.sh  <- pulls raw data from the team Google Drive
├── data/                     <- shared raw data for ALL ideas (gitignored)
│   ├── google_maps/          google_maps.csv (~506 MB), google_maps_reviews_sample.csv
│   ├── google_maps_reviews/  google_maps_reviews.csv (~222 MB)
│   └── zillow/               zillow_part1-3.csv (~7.4 GB total), zillow_sample.csv
└── close_not_accessible/     <- idea: "Close ≠ Accessible" (distance vs. what reviews say)
    ├── src/                  pipeline code (run top to bottom)
    ├── notebooks/
    └── outputs/              zip-level results only
```

## Now (who is doing what)
| Agent | Working on | Files owned right now | Status |
|---|---|---|---|
| Claude-R (Riley's machine) | "Close ≠ Accessible": Steps 1-4 run; aspect results PRELIMINARY until Riley checks labels | `close_not_accessible/**`, `scripts/download_data.sh`, `.gitignore` | waiting on Riley |

---

## Log

### 2026-11-14 13:30  Claude-R (Riley)
- Found `Datafg/` already cloned from https://github.com/RishiL381/Datafg; ran `git pull` (picked up `CLAUDE_CHAT.md` from Claude-A).
- Created idea subfolder `close_not_accessible/` with `src/`, `outputs/`, `notebooks/`.
- Created shared `data/` at repo root (not inside the idea folder) so every idea can use it.
- Wrote `scripts/download_data.sh` (curl from the link-shared Drive folder) and started downloading:
  google_maps.csv, google_maps_reviews.csv, zillow_part1-3.csv, plus the two sample files.
- Added `.gitignore` so raw CSVs and `.venv/` are never committed.
- Creating Python venv at `Datafg/.venv` (python 3.12: pandas, numpy, scikit-learn, pyarrow, jupyter).
- Machine note: Apple M1, 8 GB RAM, no CUDA GPU. Zillow must be read in chunks with `usecols`.
- Next: inspect real column names, then build Step 1 (feasibility) and stop for Riley's review.

### 2026-11-14 13:40  Claude-R (Riley): data downloaded + Step 1 feasibility done
- All 7 Drive files downloaded into `data/`; sizes match Drive byte-for-byte.
- Venv ready: `.venv` (python 3.12, pandas 3.1, sklearn 1.9, pyarrow). Pinned in `close_not_accessible/requirements.txt`.
- Added `close_not_accessible/src/config.py` (paths, seed=42, allowed columns, service-type rules) and
  `close_not_accessible/src/step1_feasibility.py`. Runs in ~15 s.
- **Real column facts (other agents: don't assume the README):**
  - Places: 147,429 rows (not ~100k), 41 cols. `permanently_closed` is the string "true"/"false". No zip column (zip only inside `address`).
    Also has `top_reviews` (JSON, <=8 reviews/place, includes reviewer_name -> strip it) and `review_distribution` (1-5 star counts, 60% filled).
  - Reviews file: 213,536 rows (not ~100k). 42,184 rows have `review_rating` = 0 (mostly hotel reviews), dropped.
    It is NOT Bay-Area essential services: top places are Panera, Dunkin', hotels, even Las Vegas casinos.
  - Zillow: 139 cols, 3 parts (1.5 + 3.9 + 2.0 GB). Not loaded yet.
- **Decisions made (commented in code):** drop 12,167 permanently closed; keep 359 temporarily closed; classify by MAIN
  `category` (all_categories adds dentists/convenience stores); the exact tag "Pharmacy" in all_categories also sets the pharmacy flag.
  Target places: clinic 6,516 | grocery 2,558 | pharmacy 1,181.
- **Result: below the 1,500 gate.** Reviews file -> only 1.3% of reviews join to a target place: 570 one-to-two-star
  reviews, ALL clinics, 0 grocery, 0 pharmacy, and 55% of them come from 10 places (Carbon Health alone 311).
- **Rescue found:** Places `top_reviews` gives 25,404 reviews with text across 5,718 target places, of which 7,145 are 1-2 star
  (clinic 3,047 | grocery 2,510 | pharmacy 1,588), spread out (top 10 places = 1.1%). Union with the reviews file, deduped = 7,700.
  Caveat: Google "most relevant" sort, not random, so 1-star share is inflated (28% vs ~18% in the reviews file).
- **Clinic filter issue:** ~1,000 of 6,516 clinics (16%) are specialty programs by name (imaging, dermatology, spine, blood-draw labs,
  "Sleep Surgery Program"). Proposed a name-keyword exclusion; not applied yet.
- Caches (gitignored, row-level): `outputs/cache/places_target.parquet`, `reviews_matched.parquet`, `reviews_embedded.parquet`, `step1_feasibility_log.txt`.
  Shareable aggregate: `outputs/step1_feasibility_summary.json`.
- **Paused** for Riley: (1) review source, (2) clinic specialty filter. Nothing committed or pushed yet.

### 2026-11-14 13:50  Claude-R (Riley): Riley's decisions applied, Step 1 passes
- **Decision 1 (Riley): use BOTH review sources** (`config.REVIEW_SOURCES`). Reviews file + Places `top_reviews`, deduped on (place_id, text).
- **Decision 2 (Riley): exclude specialty clinics by name** (`config.is_specialty_clinic_name`): dropped 1,315 (imaging, cardiology, surgery
  centers, GI, rehab...). A name with a general word (urgent, primary, family, community, pediatric, walk-in, clinica...) is kept.
- **Decision 3 (Riley): commit + push to main** after each step. `data/` and `outputs/cache/` are never committed.
- Final target places: clinic 5,201 | grocery 2,558 | pharmacy 1,181 (pharmacy flag 1,213 incl. in-house pharmacies).
- Combined reviews: 25,352 (all stars) at 5,157 places; **7,183 at 1-2 stars** (clinic 3,085 | grocery 2,510 | pharmacy 1,588). PASS.
- Place zip parsed from `address` for 98.9% of target places; only the zip is kept.
- Cache now: `outputs/cache/places_target.parquet` (8,940 rows), `outputs/cache/reviews_all.parquet` (25,352 rows, stable id `rid`).
- Next: Step 2 (Zillow homes -> BallTree haversine distance to nearest clinic/pharmacy/grocery + counts within 1 mile -> zip medians).

### 2026-11-14 14:05  Claude-R (Riley): Step 2 physical access done
- `close_not_accessible/src/step2_physical_access.py` (~50 s). Streams Zillow with usecols (+ `county`, added for the Bay filter and as "region").
- Zillow facts: full parts = 148,005 rows, all 9 Bay counties; statuses only FOR_RENT 50% / RECENTLY_SOLD 42% / FOR_SALE 8%
  (the 41 MB `zillow_sample.csv` is statewide with OTHER/SOLD statuses: don't use it for Bay Area work).
- Dropped 799 homes (bad coords or zip not 94xxx/95xxx). Kept 147,206 homes in 291 zips (46 flagged `low_n` < 30 homes).
- BallTree haversine: median home is 0.32 mi to a clinic, 0.48 mi to a pharmacy, 0.31 mi to a grocery; 10% / 17% / 9% of homes are > 1 mi.
  Farthest zips: Bodega Bay, Sea Ranch, Geyserville, Discovery Bay, Bethel Island.
- Prices split by status: `median_rent_zestimate` (all homes, main rent measure), `median_rent_listing` (FOR_RENT), `median_sale_price`.
- Output: `outputs/step2_zip_physical_access.csv` (zip level). Home-level rows only in `outputs/cache/homes.parquet` (gitignored).
- Next: Step 3 (BERTopic on the 7,183 one-to-two-star reviews, then build `label_template.csv`).

### 2026-11-14 14:30  Claude-R (Riley): Step 3a themes + 3b label sample
- `src/step3a_topics.py`: MiniLM sentence embeddings for all 25,352 reviews (cached `outputs/cache/emb_minilm.npy`, ~6 min CPU once),
  then BERTopic on the 7,090 one-to-two-star reviews with >= 5 words.
  - A single model just split by service type, so BERTopic is fit **per service type**: clinic 37 / pharmacy 20 / grocery 30 topics.
  - `outputs/step3a_topics.csv` (top words per topic) + `outputs/step3a_topic_aspect_map.csv` (my mapping of each topic -> aspect or "other").
  - All 5 aspects show up as clear topics (billing/insurance, lines/refill delays, rude staff, phones never answered, wrong hours,
    Spanish-speaker treatment). **Gap:** 59% of clustered grocery complaints are food quality (expired, moldy, rotten), which no aspect covers.
- `src/aspects.py`: the 5 aspect definitions + the keyword baseline matcher.
- `src/step3b_make_labels.py` -> `labels/label_template.csv` (500 rows, gitignored: review text). 400 random (150 clinic / 125 grocery /
  125 pharmacy) + 40 language-keyword + 30 hours-topic + 30 non-English. `stratum` column records which.
- `labels/LABELING_GUIDE.md`: rules for each aspect.
- Now: pre-labeling the 500 myself (LLM pre-labels; an API-key check was blocked, so no API calls). Then PAUSE for Riley's hand check.

### 2026-11-14 15:10  Claude-R (Riley): 500 LLM pre-labels done -> PAUSED for Riley's hand check
- Pre-labeled all 500 rows by reading each review (Claude Opus 5.5 in this session; reviews > 1,400 chars were read truncated).
  Saved as `labels/prelabels_llm.csv`; `step3b_make_labels.py` merges them into `labels/label_template.csv`.
- Pre-label prevalence: staff 63% | wait_time 30% | cost 22% | hours_availability 19% | language_access 5% (25 rows) | none 10%.
  language_access is thin: expect only ~5 positives in a 20% test split, so its F1 will be noisy. Flag this in results.
- Judgment calls Riley should check: staff vs clinical quality (I marked a dismissive/incompetent provider = staff);
  phone hold = wait_time vs phone never answered = hours_availability; "refunds refused" = cost; language_access includes being
  mistreated for speaking Spanish/Cantonese and staff who can't communicate in English.
- `labels/*.csv` are gitignored (row-level review text). Only `labels/LABELING_GUIDE.md` is in git.
- **Do not start Step 3c training until `checked` is filled in label_template.csv.**

### 2026-11-14 15:40  Claude-R (Riley): Step 3c script written + smoke-tested (no real results yet)
- `close_not_accessible/src/step3c_train.py`. Models: keyword baseline, TF-IDF (word / word+char) + LR, MiniLM embeddings + LR,
  fine-tuned `distilbert-base-uncased` on Apple MPS. All tuning (C, features, DistilBERT epoch, per-aspect thresholds) on VAL only.
- Split: 60/20/20 iterative multi-label stratification on the 5 aspects + service type (seed 42).
- Reports TEST macro-F1 with 1,000-sample bootstrap CI, per-aspect P/R/F1, on all test rows AND random-stratum-only rows.
- Error analysis by service type, county (place zip -> county via Step 2 table), short (bottom quartile, <= 41 words), non-English, stratum.
  10 example failures go to `labels/step3c_failures.csv` (gitignored, has text).
- Scores all 7,183 low-star reviews with the VAL-best model (gold labels override for the 500 checked rows)
  -> `outputs/cache/review_aspects.parquet` for Step 4.
- Guard: a real run exits unless >= 300 rows have `checked=1`. `--smoke` runs on the unverified pre-labels and writes only to
  `outputs/cache/smoke/` (gitignored). Smoke run completes end to end in ~2 min (DistilBERT 1 epoch). Smoke numbers are NOT results.
- Still waiting on Riley's label check. Step 4 not started.

### 2026-11-14 16:10  Claude-R (Riley): Step 4 combine done -> first results
- `close_not_accessible/src/step4_combine.py` (~15 s). Felt access per place from FULL Google star counts (`review_distribution`,
  matches reviews_count): empirical-Bayes shrunk mean rating (normal-normal) and 1-2 star share (beta-binomial) per service type.
  Zip felt access = avg over homes of their 3 nearest clinics/pharmacies/groceries. Distance score = mean percentile of the 3 median distances.
- Aspect complaint rates = P(low star) x P(aspect | low star, EB-shrunk per zip). **PRELIMINARY**: uses the smoke-run model trained on
  unverified LLM labels. Re-run step3c (real) then step4 after Riley's check; `aspect_labels` column says which.
- **Main result (label-free, 245 zips with >= 30 homes):** farther zips have BETTER-rated nearby services. Spearman rho = +0.25
  [95% CI 0.13, 0.37], p < 0.001; 1-2 star share rho = -0.25. Driven by grocery (+0.22) and pharmacy (+0.20); clinics ~0 (-0.04).
  Robust: nearest-1 instead of 3 -> +0.20; within-county ranks -> +0.15 (p = 0.02); dropping SF -> +0.28. Alameda goes the other way (-0.21).
  Home level (20k sample): rho 0.01-0.05 -> it's a neighborhood-level pattern, not "the closer store is always worse".
- Quadrants: close+bad "access mirage" = 70 zips, 58,606 homes (40% of homes). SF 50% of zips, Santa Clara 42%, San Mateo 36%.
- Equity (rent only, no ACS income in data/): no rent difference across quadrants (Kruskal-Wallis p = 0.78); rent vs rating rho = -0.05 (n.s.).
- Outputs: `outputs/zip_summary.csv` (Tableau), `step4_correlations.csv`, `step4_quadrant_equity.csv`, `zip_map.html`.
  lat/lon = zip centroid of homes, blanked for low_n zips (privacy).
- Caveat for write-up: "close" zips are dense urban areas with chain stores; the pattern may be chain vs. independent, not distance itself.
