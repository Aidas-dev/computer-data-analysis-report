# Learnings

## colab deploy pipeline fix (2026-05-24)
- nbconvert --execute spawns Jupyter kernel = crashes colab session
- Fix: extract notebook logic into standalone Python scripts with `if __name__ == "__main__": main()` entry point
- `run_script()` in deploy pipeline: nohup python3 script.py, poll /tmp/done_{name} marker
- Marker files: /tmp/done_pipeline_stepXX — written by each script on completion
- Each script supports --dry-run for quick syntax/import verification
- Dry-run gracefully handles missing deps (BQ creds, trafilatura, gridstatus)
- Scripts use direct Python — no Jupyter/IPython magics
- Step14 ISO_DEFS needs lazy init (via _init_isos()) because gridstatus may not be installed at module load time

## 03-data-merging real data switch (2026-05-24)
- Notebook now loads `data/processed/buildout_promises_real.csv` (5,295 real GDELT events) instead of 34 synthetic rows
- Added COMPANY_TICKER_MAP for company name → ticker resolution (no more `company_ticker` / `TICKER_` prefix)
- Date parsed from `date` column in `YYYYMMDDHHMMSS` format → `announcement_date`
- `mw_capacity` parsed as numeric → `promised_mw` (coerces errors to 0)
- Final cell now runs `dvc add` + `dvc push` on `dataset_for_ml.csv` with try/except
- Print statement updated to show "real buildout events"
- JSON edit tool can deform notebook structure (duplicate keys, lost commas) — best to validate with `python3 -c "import json; json.load(open(...))"` after each edit
- Key JSON gotchas: last element in source array can't have trailing comma; last cell in cells array can't have trailing comma before `]`

## 15-eda-analysis notebook (2026-05-24)
- Created `notebooks/15-eda-analysis.ipynb` — 29 cells (18 code, 11 markdown), 11 figures saved to `reports/figures/`
- Data: 5,295 rows, 16 cols. promise_kept: 105 kept, 22 failed, 5,168 pending (NaN)
- `~df['col'].str.match()` fails on NaN entries (TypeError: bad operand type for unary ~: 'float') — workaround: `dropna()` first, apply mask on clean series, then `.loc` back to original index
- `plt.pie(explode=...)` needs tuple/list, not generator expression
- MW capacity range: 1–90,000 MW (mean 1,235; median 150); 1,638 non-null
- 17 unique companies, 50 US states + DC represented, 3,049 missing location_state (58%)
- v2_tone has 7 comma-separated numeric fields; tone_1 and tone_3 show moderate correlation with promise_kept
- All `label_source` = `text_keywords`; all `is_buildout` = True
- Date column is int64 YYYYMMDDHHMMSS format; parse via `pd.to_datetime(..., format='%Y%m%d%H%M%S')`
- Figure 11 (synthetic_vs_real) is summary panel; LaTeX tables printed in final code cell via `df.to_latex()`
- nbconvert --execute runs fine locally (12s for 5,295 rows); keep `--ExecutePreprocessor.timeout=120`

## 2026-05-24 C3 + H1: dataset_for_ml rebuild + step14 keyword expansion
- C3: Created `scripts/build_ml_dataset.py` — builds dataset_for_ml.csv from real 5,295 events
  - COMPANY_TICKER_MAP covers all 17 companies → all 5,295 events mapped to tickers
  - Features: ticker, announcement_date, year/quarter/month, promised_mw, has_mw, mw_log, confidence_num, tone_sentiment, location, target_date, days_to_target
  - 28 columns total vs old 46 (old had financial/macro merges that require missing data files)
  - DVC tracked (3aa60701) and pushed
- H1: Expanded step14 keyword lists — 15→30+ kept keywords, 11→20+ failed keywords
  - Sorted by length desc to avoid false positives from short substrings
  - Added conditional title-based classification (currently 0 hits — no title column in input)
  - Added `text_matched`/`title_matched` tracking columns
  - Before: 105 kept, 22 failed, 5,168 pending (2.0% / 0.4% / 97.6%)
  - After:  146 kept, 25 failed, 5,124 pending (2.8% / 0.5% / 96.8%)
  - 39% improvement in kept labels. DVC tracked and pushed.
- Key insight: no `title` column in `buildout_events_raw.csv` — title matching is future-proofing only

## 2026-05-24 F1 Plan Compliance Audit
- T2 GDELT candidates DVC file (`buildout_candidates_gkg.csv.dvc`) was never committed — notebook exists but output artifact missing
- T11-T14 deliverables exist on disk but are uncommitted (untracked/modified)
- Paper compiles to 29-page PDF, 43 references, 11 figures, 5 LaTeX tables — substantive work complete
- DVC status clean, no synthetic data leaks (TICKER_ check passed)
