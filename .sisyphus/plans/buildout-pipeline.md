# Buildout Pipeline: Real Data → Analysis → Elsevier Paper

## TL;DR

> **Core**: Replace 34 synthetic buildout promise events with real data mined from GDELT + gridstatus. Full pipeline: domain-filtered GDELT GKG query → article text extraction → gridstatus labeling → merge with existing financial/timeseries/census data → EDA + event study → Elsevier research paper.
>
> **Deliverables**:
> - 3 new notebooks (GDELT mining, article extraction, gridstatus labeling)
> - Updated 03/04/05 merge notebooks with real events
> - EDA + event study notebooks
> - Elsevier LaTeX paper via academic-pipeline
>
> **Estimated Effort**: Large (5-7 phases, 15+ tasks)
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: GDELT query → Article extraction → Gridstatus labeling → Data merge → EDA → Paper

---

## Context

### Original Request
User discovered 34 buildout promise events in `buildout_promises_expanded.csv` are synthetic (wrong ISOs, TICKER_ prefix, non-DC companies with MW values, no sources). Want to replace with real events from BigQuery GDELT, cross-referenced with gridstatus for labeling. Everything documented in notebooks, models on colab, DVC+git. Final deliverable: Elsevier research paper using academic-pipeline.

### Interview Summary
**Key Decisions**:
- Promise source: News/press release announcements via GDELT v2 GKG
- Query scope: DC industry domains only (datacenterdynamics.com, datacenterknowledge.com, siliconangle.com)
- Companies: Keep all 20 tickers across 4 tiers
- Labeling: Cross-reference with gridstatus ISO queue (Operating=kept, Withdrawn=failed)
- Timeline: This week (high priority)
- End deliverable: Elsevier research paper
- Infrastructure: colab for compute, DVC for data, git for notebooks

### Research Findings
- GDELT GKG partitioned by date; SourceCommonName not clustered. Domain-filtered query much cheaper than theme-based scan (~1-5 GB vs 148 GB)
- **gridstatus**: `get_interconnection_queues()` returns unified 19K+ projects across ALL ISOs (CAISO, MISO, PJM, ERCOT, NYISO, SPP, ISONE) with Queue Date, Status, Capacity, County, Withdrawn Date, Actual Completion Date
- **Event study**: `easy-event-study` (Darenar) and `eventstudy` {LemaireJean-Baptiste} packages for CAR/CAAR calculation with yfinance integration
- **Article extraction**: `trafilatura` outperforms newspaper3k (F1=0.910 vs 0.762). Recommended for research-grade text extraction
- **Key literature**:
  - Fitzsimmons et al. (2022) — Construction schedule risk with hybrid ML (ITcon). GMM + SVM + MCS on 293K tasks
  - Mosca, Hovhannisyan, Phillips (2026) — Neural network duration forecasts + MCS (Springer LNCE)
  - Johnston, Liu, Yang (2023) — Empirical analysis of interconnection queue (NBER w31946). Hand-collected 4,085 PJM requests
  - LBNL "Queued Up: 2025" — 10,300 active projects, only 13% reach operations. Median queue-to-COD: <2yr(2000-2007) → 4+yr(2018-2024)
  - arXiv (2026) — Multi-task Transformer for colocation data center capacity prediction
- **Critical insight**: Post-2024 bottleneck shifting *past* interconnection queue — transformer lead times 50→160 weeks, post-approval now dominates delays
- Academic: `academic-pipeline` skill available for full research → paper workflow

### Metis Review
- **Domain-only missing PR wires**: We might miss announcements published only on prnewswire. Solve: add reuters.com, bloomberg.com tech sections as secondary sources if needed.
- **Future events can't be labeled via gridstatus**: Events with 2026+ target dates may not appear in queue yet. Solve: mark as "pending" with placeholder, document as limitation.
- **Article text extraction failure**: Some domains block scraping. Solve: use newspaper3k with fallback, document failed URLs.
- **20 tickers across all ISOs**: Not all 20 companies operate in all ISOs. Solve: ISO mapping per project, not per company.

---

## Work Objectives

### Core Objective
Build a repeatable pipeline that produces real, sourced buildout promise events for 20 data-center-relevant companies, labels them via grid interconnection status, merges with financial/timeseries/census data, and produces an Elsevier research paper.

### Concrete Deliverables
- `notebooks/12-gdelt-domain-filter.ipynb` — GDELT v2 GKG query by domain + company
- `notebooks/13-article-extraction.ipynb` — Fetch article text, extract structured fields
- `notebooks/14-gridstatus-labeling.ipynb` — Cross-reference with ISO queue, label events
- `notebooks/15-eda-analysis.ipynb` — Exploratory data analysis of real events
- `notebooks/16-event-study.ipynb` — Stock price event study around announcements
- Updated `03-data-merging.ipynb` — Uses real buildout_events_labeled.csv
- Updated `04-quarterly-panel.ipynb` — Regenerated with real events
- Updated `05-timeseries-features.ipynb` — Regenerated with real events
- `data/processed/buildout_events_labeled.csv` — Final labeled dataset (DVC tracked)
- `data/processed/dataset_for_ml.csv` — Final ML dataset with real targets (DVC tracked)
- Elsevier LaTeX paper in `report/`

### Definition of Done
- [ ] GDELT query produces candidate article URLs with zero uncaught errors
- [ ] Article extraction produces structured events CSV with company, location, MW, dates
- [ ] Gridstatus labels each event as kept/failed/pending
- [ ] Merged ML dataset has >34 real events (target: 50-200)
- [ ] EDA + event study notebooks run on colab and produce output
- [ ] DVC pushed all datasets
- [ ] Committed all notebooks
- [ ] Elsevier paper drafted and reviewed

### Must Have
- GDELT query costs <5 GB per run (domain-filtered, not theme-matched)
- Every event has a source URL
- Gridstatus data covers at least 4 major ISOs (CAISO, MISO, PJM, ERCOT)
- Paper uses Elsevier elsarticle LaTeX template

### Must NOT Have (Guardrails)
- No broad GDELT theme matching (>10 GB queries)
- No synthetic/placeholder events without sources
- No non-DC companies assigned MW values
- No BQ dry-runs that cost >10 GB without user approval
- No manual labeling without documented methodology

---

## Verification Strategy

> **ALL verification agent-executed on colab. No manual confirmation required.**

### Test Decision
- **Infrastructure exists**: NO (no test framework)
- **Automated tests**: None (notebooks are verified by execution + output inspection)
- **Agent-Executed QA**: EVERY notebook runs end-to-end on colab. Output files inspected for correctness.

### QA Policy
Every notebook task includes agent-executed verification on colab:
- Notebook runs from scratch (`nbconvert --execute`) without errors
- Output CSV files non-empty with expected columns
- DVC push succeeds
- For GDELT: verify billed bytes <5 GB
- For extraction: verify MW values are numbers, locations are real US places
- For labeling: verify Operating label matches gridstatus data

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — Start Immediately, MAX PARALLEL):
├── Task 1: Academic research — deep-research for literature review
├── Task 2: 12-gdelt-domain-filter.ipynb — GDELT GKG domain query
├── Task 3: Update colab_refresh.py — add extraction tools (newspaper3k)
└── Task 4: Check gridstatus availability for all ISOs

Wave 2 (After Wave 1 — extraction + queue data, parallel):
├── Task 5: 13-article-extraction.ipynb — fetch + parse article text
├── Task 6: 14-gridstatus-labeling.ipynb — cross-reference + label
└── Task 7: Pull + validate gridstatus data for 6 ISOs

Wave 3 (After Wave 2 — merge pipeline, parallel):
├── Task 8: Update 03-data-merging.ipynb — use real events
├── Task 9: Update 04-quarterly-panel.ipynb — regenerate
├── Task 10: Update 05-timeseries-features.ipynb — regenerate
└── Task 11: DVC push all datasets

Wave 4 (After Wave 3 — analysis, parallel):
├── Task 12: 15-eda-analysis.ipynb — EDA of real events
├── Task 13: 16-event-study.ipynb — CAR analysis
└── Task 14: Summary statistics for paper

Wave FINAL (Paper):
├── Task 15: Run academic-pipeline (deep-research → write → review → finalize)
└── Task 16: Compile and verify Elsevier LaTeX output

Critical Path: Task 2 → Task 5 → Task 6 → Task 8 → Task 12 → Task 15
```

---

## TODOs

- [x] 1. **Academic Research — deep-research for literature review**

  **What to do**:
  - Run `deep-research` skill on topics:
    - Machine learning for infrastructure/construction project success prediction
    - Data center buildout completion analysis and lifecycle
    - Factors affecting large-scale construction project delivery
    - Grid interconnection queue delays and causes
    - Event study methodology for corporate investment announcements
  - Focus on US data center industry, grid interconnection processes
  - Save research synthesis for paper introduction + related work

  **Must NOT do**:
  - Don't over-research (>30 min). This is planning-level, not full paper literature review.
  - Don't modify any existing files or notebooks.

  **Recommended Agent Profile**:
  - **Subagent**: `deep-research` (quick mode) or `library` (librarian) for faster turnaround

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2, 3, 4)
  - **Blocks**: Task 15 (paper writing)
  - **Blocked By**: None

  **References**:
  - Existing research foundation in `docs/research_foundation.md`
  - Academic pipeline skills: `academic-paper`, `academic-paper-reviewer`, `academic-pipeline`

  **Acceptance Criteria**:
  - [ ] Research synthesis saved to `docs/literature_synthesis.md`
  - [ ] At least 10 relevant papers identified with key findings
  - [ ] Research covers: construction ML, DC lifecycle, event study methodology
  - [ ] Synthesis usable as paper introduction + related work foundation

  **QA Scenarios**:
  ```
  Scenario: Research output exists and covers required topics
    Tool: Bash (cat docs/literature_synthesis.md)
    Steps:
      1. Check file exists and non-empty
      2. Count referenced papers (>10)
      3. Verify topics include construction ML, DC lifecycle, event studies
    Expected Result: File exists with 10+ references across all required topics
    Evidence: .sisyphus/evidence/task-1-research-synthesis.md
  ```

  **Commit**: YES
  - Message: `docs: add literature synthesis for DC buildout pipeline`
  - Files: `docs/literature_synthesis.md`

- [x] 2. **12-gdelt-domain-filter.ipynb — domain-filtered GKG query**

  **What to do**:
  - Create `notebooks/12-gdelt-domain-filter.ipynb`
  - Universal first cell (pip install + imports) matching 06-panel-ml style
  - GDELT v2 GKG query:
    ```sql
    SELECT DATE, SourceCommonName, DocumentIdentifier, V2Organizations, V2Locations, V2Tone
    FROM `gdelt-bq.gdeltv2.gkg_partitioned`
    WHERE _PARTITIONTIME >= '2020-01-01'
      AND SourceCommonName IN ('datacenterdynamics.com', 'datacenterknowledge.com', 'siliconangle.com')
      AND (
        V2Organizations LIKE '%Microsoft%' OR V2Organizations LIKE '%Google%' OR
        V2Organizations LIKE '%Amazon%' OR V2Organizations LIKE '%Meta%' OR
        V2Organizations LIKE '%Oracle%' OR V2Organizations LIKE '%NVIDIA%' OR
        V2Organizations LIKE '%Apple%' OR V2Organizations LIKE '%Digital%Realty%' OR
        V2Organizations LIKE '%Equinix%' OR V2Organizations LIKE '%American%Tower%' OR
        V2Organizations LIKE '%Prologis%' OR V2Organizations LIKE '%Crusoe%' OR
        V2Organizations LIKE '%Simon%Property%' OR V2Organizations LIKE '%Public%Storage%' OR
        V2Organizations LIKE '%Outfront%' OR V2Organizations LIKE '%Sabra%' OR
        V2Organizations LIKE '%Hudson%Pacific%' OR V2Organizations LIKE '%Rexford%' OR
        V2Organizations LIKE '%First%Industrial%' OR V2Organizations LIKE '%SITC%'
      )
    ORDER BY DATE DESC
    ```
  - Dry run first to estimate cost. If >5 GB, tighten date range.
  - Execute query, save to `data/raw/buildout_candidates_gkg.csv`
  - Print summary: total candidates, per-domain, per-company, per-year
  - Save CSV and `.dvc` file

  **Must NOT do**:
  - No theme matching (ECON_INVESTMENT, etc.) — domain filter is the precision mechanism
  - No >10 GB query without user approval
  - No querying GDELT events table (wrong data type)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` — requires BQ auth, Python, GDELT schema knowledge
  - **Skills**: Not needed (no matching skill)

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1, 3, 4)
  - **Blocks**: Task 5 (article extraction)
  - **Blocked By**: None (BQ already authenticated)

  **References**:
  - `notebooks/10-bigquery-gdelt.ipynb` — Previous GDELT query patterns, BQ auth
  - `scripts/colab_refresh.py` — Colab deployment pattern
  - `docs/gcp_adc.json` — GCP ADC creds for BQ auth on colab

  **Acceptance Criteria**:
  - [ ] Notebook creates candidates CSV in `data/raw/buildout_candidates_gkg.csv`
  - [ ] Query billed <5 GB
  - [ ] At least 100 candidate articles returned
  - [ ] DVC tracked file

  **QA Scenarios**:
  ```
  Scenario: GDELT query runs successfully
    Tool: interactive_bash (tmux) on colab session
    Steps:
      1. colab exec -s gdelt-mining -f 12-gdelt-domain-filter.ipynb
      2. Check exit code and output
      3. Verify data/raw/buildout_candidates_gkg.csv exists and non-empty
    Expected Result: >100 rows, billed <5 GB
    Evidence: .sisyphus/evidence/task-2-gdelt-query.txt

  Scenario: Data quality check
    Tool: Bash
    Steps:
      1. Check columns: DATE, SourceCommonName, DocumentIdentifier, V2Organizations
      2. Check SourceCommonName values are from 3 allowed domains
      3. Verify date range covers 2020-2026
    Expected Result: All columns present, domains correct
    Evidence: .sisyphus/evidence/task-2-gdelt-quality.txt
  ```

  **Commit**: YES
  - Message: `feat: add GDELT domain-filtered buildout mining notebook`
  - Files: `notebooks/12-gdelt-domain-filter.ipynb`, `data/raw/buildout_candidates_gkg.csv.dvc`

- [x] 3. **Update colab_refresh.py — add extraction tools**

  **What to do**:
  - Add to `scripts/colab_refresh.py`:
    - `pip install newspaper3k lxml_html_clean trafilatura`
    - BQ auth check (GOOGLE_APPLICATION_CREDENTIALS)
    - gridstatus installation check

  **Must NOT do**:
  - Don't change existing setup logic
  - Don't create new scripts

  **Recommended Agent Profile**:
  - **Category**: `quick` — single file modification

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1 with Tasks 1, 2, 4)
  - **Blocks**: Task 5 (article extraction needs newspaper3k)
  - **Blocked By**: None

  **References**:
  - `scripts/colab_refresh.py` — existing setup script

  **Acceptance Criteria**:
  - [ ] newspaper3k and trafilatura in requirements
  - [ ] Script installs them on colab
  - [ ] Script verifies BQ auth

  **QA Scenarios**:
  ```
  Scenario: Extraction tools install
    Tool: interactive_bash on colab session
    Steps:
      1. Run pip install check for newspaper3k, trafilatura
      2. Import both in Python
    Expected Result: Both import without error
    Evidence: .sisyphus/evidence/task-3-extraction-tools.txt
  ```

  **Commit**: YES
  - Message: `chore: add article extraction deps to colab_refresh.py`
  - Files: `scripts/colab_refresh.py`, `requirements.txt`

- [x] 4. **Check gridstatus availability for all ISOs**

  **What to do**:
  - Create a quick colab script that tests gridstatus for:
    - CAISO, MISO, PJM, ERCOT, NYISO, SPP, ISONE
  - For each ISO: pull latest queue data (limit 100), check fields
  - Report which ISOs have queue data with what fields
  - Save to `docs/gridstatus_isos_report.md`

  **Must NOT do**:
  - Don't spend >30 min on this
  - Don't create a full notebook for this (script only)

  **Recommended Agent Profile**:
  - **Category**: `quick`

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 1 with Tasks 1, 2, 3)
  - **Blocks**: Task 6 (gridstatus labeling)
  - **Blocked By**: None

  **References**:
  - `requirements.txt` has `gridstatus>=0.34.0`
  - gridstatus docs: https://gridstatus.readthedocs.io/

  **Acceptance Criteria**:
  - [x] Report shows which ISOs have accessible queue data
  - [x] Field mapping documented

  **QA Scenarios**:
  ```
  Scenario: At least 4 ISOs accessible
    Tool: colab exec
    Steps:
      1. Run gridstatus test script
      2. Count ISOs with successful data pull
    Expected Result: CAISO, MISO, PJM, ERCOT all return data
    Evidence: .sisyphus/evidence/task-4-gridstatus-report.md
  ```

  **Commit**: YES
  - Message: `docs: add gridstatus ISO availability report`
  - Files: `docs/gridstatus_isos_report.md`

- [x] 5. **13-article-extraction.ipynb — fetch + parse article text**

  **What to do**:
  - Create `notebooks/13-article-extraction.ipynb`
  - Load candidates from `data/raw/buildout_candidates_gkg.csv`
  - For each URL:
    - Fetch article text using `newspaper3k` (primary) with `trafilatura` (fallback)
    - Extract: title, publish_date, text, top_image
    - Regex patterns for:
      - MW values: `(\d+[,\.]?\d*)\s*(MW|megawatt|megawatts)`
      - Location (city, state): from V2Locations field + article text
      - Company name: from V2Organizations field
      - Target completion dates: `Q[1-4]\s*\d{4}`, `\d{4}`, month+year patterns
    - Classify: is this a buildout announcement? (has MW + location + company)
  - Output: `data/raw/buildout_events_extracted.csv`
  - Columns: url, source_domain, publish_date, company, location_city, location_state, mw, target_date, is_buildout (bool), confidence (high/medium/low), raw_text_excerpt

  **Must NOT do**:
  - No LLM-based extraction (cost prohibitive for 1000+ articles)
  - No manual review of each article
  - Don't fail on fetch errors — log and continue

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` — requires web scraping, NLP, regex, data processing

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 2)
  - **Parallel Group**: Wave 2 (with Task 6, 7)
  - **Blocks**: Task 6 (labeling)
  - **Blocked By**: Task 2 (candidates CSV)

  **References**:
  - `notebooks/12-gdelt-domain-filter.ipynb` — upstream
  - newspaper3k docs: https://newspaper.readthedocs.io/
  - trafilatura docs: https://trafilatura.readthedocs.io/

  **Acceptance Criteria**:
  - [ ] Extracts >50% of candidate URLs successfully
  - [ ] At least 20 classified as buildout announcements (is_buildout=True)
  - [ ] MW values are numeric, locations are US places
  - [ ] Output CSV has all required columns

  **QA Scenarios**:
  ```
  Scenario: Article extraction runs
    Tool: interactive_bash on colab
    Steps:
      1. Run 13-article-extraction.ipynb via nbconvert
      2. Check data/raw/buildout_events_extracted.csv exists
      3. Check number of is_buildout=True events
    Expected Result: >20 buildout events, all columns present
    Evidence: .sisyphus/evidence/task-5-extraction-results.txt

  Scenario: Extraction quality
    Tool: Bash
    Steps:
      1. Check mw column values are numeric
      2. Check location_state validates against US states
      3. Check company column not empty
    Expected Result: Numeric MW, valid states, non-empty companies
    Evidence: .sisyphus/evidence/task-5-extraction-quality.txt
  ```

  **Commit**: YES
  - Message: `feat: add article extraction notebook for buildout events`
  - Files: `notebooks/13-article-extraction.ipynb`, `data/raw/buildout_events_extracted.csv.dvc`

- [x] 6. **14-gridstatus-labeling.ipynb — cross-reference + label**

  **What to do**:
  - Create `notebooks/14-gridstatus-labeling.ipynb`
  - For each ISO with queue data (from Task 4):
    - Pull full interconnection queue via gridstatus
    - Filter for relevant projects: data center companies, relevant MW range
  - Cross-reference extracted events with queue entries:
    - Match by: company name (fuzzy), location (county/city), MW range (±20%)
    - Or: company name (fuzzy), date proximity (±6 months), MW range
  - Labeling logic:
    - If ISO queue shows "Operating": promise_kept=1
    - If ISO queue shows "Withdrawn", "Suspended", "Cancelled": promise_kept=0
    - If ISO queue shows "In Queue", "Under Study": promise_kept=NULL (pending)
    - If no queue match: mark as "unmatched" (manual review needed)
  - Output: `data/raw/buildout_events_labeled.csv`
  - Columns: all from extracted + iso_region, queue_project_name, queue_status, promise_kept (1/0/NULL), matching_method, notes

  **Must NOT do**:
  - No manual labeling — all automated via gridstatus
  - Don't use ML for matching — use deterministic fuzzy matching
  - Don't hardcode queue data — always pull fresh

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` — gridstatus API, fuzzy matching, data pipeline

  **Parallelization**:
  - **Can Run In Parallel**: With Task 5 (both Wave 2, but labeling depends on extraction output)
  - **Parallel Group**: Wave 2 (Task 5 → Task 6 sequential within Wave 2)
  - **Blocks**: Task 8 (data merge)
  - **Blocked By**: Task 4 (gridstatus report), Task 5 (extraction)

  **References**:
  - `docs/gridstatus_isos_report.md` — which ISOs/have what data
  - gridstatus docs — queue data fields per ISO
  - `data/raw/buildout_events_extracted.csv` — input events

  **Acceptance Criteria**:
  - [ ] Pulls queue data for all available ISOs
  - [ ] Labels at least 30% of events (has match in queue)
  - [ ] Clear statistics: how many kept, failed, pending, unmatched
  - [ ] DVC tracked file

  **QA Scenarios**:
  ```
  Scenario: Labeling runs without errors
    Tool: interactive_bash on colab
    Steps:
      1. Run 14-gridstatus-labeling.ipynb
      2. Check output CSV
      3. Count labeled vs unmatched events
    Expected Result: Labeled output with clear stats
    Evidence: .sisyphus/evidence/task-6-labeling-results.txt

  Scenario: Label distribution
    Tool: Bash
    Steps:
      1. Count promise_kept=1, promise_kept=0, NULL
      2. Check no duplicate events
    Expected Result: Reasonable distribution, no duplicates
    Evidence: .sisyphus/evidence/task-6-label-distribution.txt
  ```

  **Commit**: YES
  - Message: `feat: add gridstatus labeling notebook for buildout events`
  - Files: `notebooks/14-gridstatus-labeling.ipynb`, `data/raw/buildout_events_labeled.csv.dvc`

- [x] 6b. **Repurpose step14: text-based labeling from article content**

  **Context**: Gridstatus interconnection queues are for power generation, not data centers. Step13 extracted article text for all 5,295 events. Use keyword heuristics on article text for labeling instead.

  **Approach**: Classify each event's `is_buildout` field (already extracted in step13) + add `promise_kept` label using text heuristics:
  - **kept** (promise_kept=1): keywords like "opened", "began operations", "launched", "goes live", "commissioned", "cut the ribbon", "inaugurated"
  - **failed** (promise_kept=0): keywords like "canceled", "scrapped", "shelved", "delayed indefinitely", "abandoned", "halted"
  - **in_progress** (promise_kept=NULL): keywords like "under construction", "breaking ground", "building", "construction underway", "started construction"
  - **pending** (promise_kept=NULL): default for weakly positive announcements, "announced", "to build", "planned", "proposed"

  **Modify** `scripts/pipeline_step14.py` to:
  1. Load `buildout_events_raw.csv` from step13
  2. Apply keyword classification to `raw_text_excerpt` column
  3. Add columns: `promise_kept` (1/0/NULL), `label_source` ("text_keywords")
  4. Preserve all existing columns from step13
  5. Output: `data/processed/buildout_promises_real.csv`
  6. DVC push

  **Must NOT do**:
  - No LLM/API call for classification (cost prohibitive at 5K events)
  - No manual review per event
  - No gridstatus dependency

  **Parallelization**: Sequential after task 6a
  **Blocks**: Task 7 (merge)
  **Blocked By**: Task 5 (extraction output)

  **Acceptance Criteria**:
  - [ ] All 5,295 events labeled (kept/failed/pending)
  - [ ] At least 10 "kept" and 5 "failed" events
  - [ ] `promise_kept` column is 1/0/NULL (not string)
  - [ ] Output CSV DVC pushed
  - [ ] Output columns include all step13 fields + label

  **Commit**: YES
  - Message: `feat: replace gridstatus with text-based labeling in pipeline`
  - Files: `scripts/pipeline_step14.py`, `data/processed/buildout_promises_real.csv.dvc`

- [x] 7. **Update 03-data-merging.ipynb — use real events**

  **Status**: Updated to load `buildout_promises_real.csv` with `COMPANY_TICKER_MAP`, date parsing from `%Y%m%d%H%M%S`, `promised_mw` mapping. 13 cells.

- [x] 8. **Update 04-quarterly-panel.ipynb — regenerate**

  **Status**: Updated CSV path to `buildout_promises_real.csv`, added `COMPANY_TICKER_MAP`, date parsing, `promised_mw` mapping. Removed old TICKER_ prefix. 26 cells.

- [x] 9. **Update 05-timeseries-features.ipynb — regenerate**

  **Status**: Updated CSV path to `buildout_promises_real.csv`, added `COMPANY_TICKER_MAP`, date parsing from `%Y%m%d%H%M%S`, `promised_mw` column mapping. 16 cells.

- [x] 10. **DVC push all datasets**

  **What to do**:
  - After Tasks 7-9 complete:
    - `dvc commit` all changed .dvc files
    - `dvc push` all datasets
    - Verify all files on remote

  **Must NOT do**:
  - Don't push without verifying data integrity

  **Acceptance Criteria**:
  - [ ] All .dvc files committed
  - [ ] dvc push succeeds
  - [ ] Remote has all latest versions

  **QA Scenarios**:
  ```
  Scenario: DVC push success
    Tool: Bash
    Steps:
      1. dvc status (check for modified files)
      2. dvc push
    Expected Result: All files up to date, push succeeds
    Evidence: .sisyphus/evidence/task-10-dvc-push.txt
  ```

  **Commit**: YES
  - Message: `data: update datasets with real buildout events`
  - Files: All changed .dvc files

- [x] 11. **15-eda-analysis.ipynb — EDA of real events**

  **What to do**:
  - Create `notebooks/15-eda-analysis.ipynb`
  - Sections:
    - **Descriptive statistics**: Count of events by company/tier/year/ISO
    - **Target distribution**: promise_kept ratio, by company tier, by ISO
    - **Event timing**: Announcement dates, target dates, time-to-operational
    - **MW analysis**: Distribution by company tier, by ISO
    - **Location analysis**: Geographic distribution, by state
    - **Feature correlations**: Correlation of economic/financial variables with promise_kept
    - **Comparison**: Real vs synthetic data comparison (how different)
    - **LaTeX-compatible tables**: All summary tables exportable to LaTeX
    - **Visualizations**: Bar plots, histograms, geographic maps (seaborn/matplotlib)
  - Save all figures to `reports/figures/`
  - Output: LaTeX-compatible summary stats for paper

  **Must NOT do**:
  - No ML modeling (that's for the paper methodology)
  - Don't use synthetic data as baseline for comparison

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering` — plots, tables, LaTeX output
  - **Skills**: Not needed

  **Parallelization**:
  - **Can Run In Parallel**: With Task 12 (Wave 4)
  - **Parallel Group**: Wave 4 (with Task 12, 13)
  - **Blocks**: Task 14 (paper writing)
  - **Blocked By**: Task 7 (merged dataset)

  **References**:
  - `notebooks/06-panel-ml.ipynb` — existing analysis pattern
  - `data/processed/dataset_for_ml.csv` — merged dataset
  - `notebooks/exploratory/` — any existing EDA notebooks

  **Acceptance Criteria**:
  - [ ] Notebook runs without errors
  - [ ] At least 10 visualizations saved
  - [ ] Summary stats exportable to LaTeX
  - [ ] Clear comparison: real vs synthetic

  **QA Scenarios**:
  ```
  Scenario: EDA produces outputs
    Tool: interactive_bash on colab
    Steps:
      1. Run 15-eda-analysis.ipynb
      2. Check reports/figures/ for generated plots
      3. Check summary statistics output
    Expected Result: 10+ plots, numeric summary stats
    Evidence: .sisyphus/evidence/task-11-eda-output.txt
  ```

  **Commit**: YES
  - Message: `feat: add EDA notebook for real buildout events`
  - Files: `notebooks/15-eda-analysis.ipynb`

- [x] 12. **16-event-study.ipynb — stock price reaction analysis**

  **What to do**:
  - Create `notebooks/16-event-study.ipynb`
  - For each buildout announcement event:
    - Define event window: [-20, +60] trading days around announcement date
    - Calculate abnormal returns using market model (S&P 500 as market proxy)
    - Estimate using [-120, -21] estimation window
    - Aggregate: Cumulative Abnormal Returns (CAR) across all events
    - Test: t-test for CAR significance
  - Subsample analysis: by company tier, by ISO, by year
  - Control sample: non-event periods for same companies
  - Output: event study summary statistics and visualizations

  **Must NOT do**:
  - No complex financial models beyond market model
  - Don't use look-ahead bias (event study is standard methodology)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` — requires statsmodels, event study knowledge

  **Parallelization**:
  - **Can Run In Parallel**: YES (Wave 4 with Task 11)
  - **Parallel Group**: Wave 4 (with Task 11, 13)
  - **Blocks**: Task 14 (paper)
  - **Blocked By**: Task 7 (merged dataset) + Task 9 (timeseries features)

  **References**:
  - `data/processed/timeseries_features.csv` — daily stock data with event labels
  - statsmodels docs: OLS regression for market model
  - MacKinlay (1997) event study methodology

  **Acceptance Criteria**:
  - [ ] Notebook runs without errors
  - [ ] CAR values calculated for each event
  - [ ] Aggregate CAR significance test
  - [ ] Subsample analysis by tier/ISO/year

  **QA Scenarios**:
  ```
  Scenario: Event study produces results
    Tool: interactive_bash on colab
    Steps:
      1. Run 16-event-study.ipynb
      2. Check CAR values are reasonable
      3. Check significance tests output
    Expected Result: Numeric CARs, p-values, subsample breakdowns
    Evidence: .sisyphus/evidence/task-12-event-study.txt
  ```

  **Commit**: YES
  - Message: `feat: add event study notebook for buildout announcements`
  - Files: `notebooks/16-event-study.ipynb`

- [x] 13. **Summary statistics for paper**

  **What to do**:
  - Create `reports/summary_statistics.tex` — LaTeX tables for the paper
  - Tables:
    - Table 1: Summary statistics (mean, median, SD for key variables)
    - Table 2: Events by company tier
    - Table 3: Events by ISO region
    - Table 4: Event study CAR results
    - Table 5: Feature correlations with promise_kept
  - Format as LaTeX table code ready for elsarticle

  **Must NOT do**:
  - No manual numbers — all from notebook outputs

  **Recommended Agent Profile**:
  - **Category**: `writing` — LaTeX formatting

  **Parallelization**:
  - **Can Run In Parallel**: With Tasks 11-12 (Wave 4)
  - **Blocks**: Task 14 (paper)
  - **Blocked By**: Tasks 11-12

  **Acceptance Criteria**:
  - [ ] All 5 tables present
  - [ ] Format compatible with elsarticle
  - [ ] Numbers match notebook outputs

  **Commit**: YES
  - Message: `docs: add summary statistics LaTeX tables for paper`
  - Files: `reports/summary_statistics.tex`

- [x] 14. **Run academic-pipeline for Elsevier paper**

  **What to do**:
  - Run `academic-pipeline` skill:
    - Stage 1 (RESEARCH): deep-research on data center buildout prediction
    - Stage 2 (WRITE): academic-paper full mode → complete paper draft
    - Stage 2.5 (INTEGRITY): verify all citations and claims
    - Stage 3 (REVIEW): academic-paper-reviewer → peer review
    - Stage 4 (REVISE): address reviewer comments
    - Stage 4.5 (FINAL INTEGRITY): final verification
    - Stage 5 (FINALIZE): format-convert → Elsevier LaTeX
  - Paper structure:
    - Title: "Predicting AI Data Center Buildout Completion: A Machine Learning Approach"
    - Abstract
    - Introduction (research gap, question, contribution)
    - Literature Review: Fitzsimmons(2022) construction ML, Mosca(2026) neural net durations, Johnston(2023) queue analysis, LBNL(2025) queue outcomes, arXiv(2026) DC Transformer
    - Methodology (data pipeline: GDELT→gridstatus→merge → features: queue depth, MW, ISO, financials, census → models: Logistic Ridge, GBM, survival analysis)
    - Results (EDA findings, event study CAR, model performance, feature importance)
    - Discussion (limitations: 34→real N, post-2024 bottleneck shift, transformer lead times)
    - Conclusion
    - References (elsarticle format)
  - Output: `report/main.tex` — Elsevier elsarticle format

  **Must NOT do**:
  - No fabricating citations (IRON RULE)
  - No skipping integrity checks (IRON RULE)

  **Recommended Agent Profile**:
  - **Category**: N/A (use `academic-pipeline` skill)
  - **Skills**: `academic-pipeline`, `deep-research`, `academic-paper`, `academic-paper-reviewer`

  **Parallelization**:
  - **Can Run In Parallel**: NO (sequential pipeline)
  - **Parallel Group**: Final Wave
  - **Blocks**: Project completion
  - **Blocked By**: Tasks 11-13 (EDA + event study + summary stats)

  **References**:
  - `report/main.tex` — existing LaTeX skeleton
  - `report/tex/main.tex` — alternative LaTeX skeleton
  - `academic-pipeline` skill docs
  - `reports/summary_statistics.tex` — paper tables
  - `notebooks/15-eda-analysis.ipynb` — EDA findings
  - `notebooks/16-event-study.ipynb` — event study findings

  **Acceptance Criteria**:
  - [ ] Paper drafted in full
  - [ ] All citations verified
  - [ ] Peer review completed
  - [ ] Elsevier LaTeX compiles without errors
  - [ ] All required sections present
  - [ ] Integrity check passes

  **QA Scenarios**:
  ```
  Scenario: Paper structure complete
    Tool: Bash (check report/main.tex sections)
    Steps:
      1. Verify Abstract, Introduction, Methodology, Results, Discussion, Conclusion exist
      2. Check LaTeX compiles (tectonic or pdflatex)
      3. Check reference list non-empty
    Expected Result: Complete, compilable Elsevier paper
    Evidence: .sisyphus/evidence/task-14-paper-compile.txt

  Scenario: Peer review passed
    Tool: Check academic-paper-reviewer output
    Steps:
      1. Verify editorial decision (not Reject)
      2. All critical issues addressed
    Expected Result: Accept or Minor Revision
    Evidence: .sisyphus/evidence/task-14-review-result.txt
  ```

  **Commit**: YES
  - Message: `docs: add Elsevier paper on DC buildout prediction`
  - Files: `report/main.tex`, `report/references.bib`

---

## Final Verification Wave

- [x] F1. **Plan Compliance Audit** — `oracle`
  Verify every task completed. Check: source URLs for all events, DVC hashes match, notebooks runnable.
  VERDICT: APPROVE/REJECT

- [x] F2. **Data Quality Review** — `unspecified-high`
  Spot-check 10 events: confirm URL works, MW makes sense, location is real, gridstatus match is documented.
  VERDICT: PASS/FAIL

- [x] F3. **Real Manual QA** — `unspecified-high`
  Deploy on fresh colab session. Run entire pipeline end-to-end from GDELT query → paper. Verify no step fails.
  VERDICT: PASS/FAIL

- [x] F4. **Scope Fidelity Check** — `deep`
  Verify: no synthetic data in final dataset, all notebooks documented, DVC tracked, git committed.
  VERDICT: PASS/FAIL

---

## Commit Strategy

- **1**: `docs: add literature synthesis for DC buildout pipeline` - `docs/literature_synthesis.md`
- **2**: `feat: add GDELT domain-filtered buildout mining notebook` - notebooks/12, data/raw/candidates.dvc
- **3**: `chore: add article extraction deps to colab_refresh.py` - scripts/colab_refresh.py, requirements.txt
- **4**: `docs: add gridstatus ISO availability report` - docs/gridstatus_isos_report.md
- **5**: `feat: add article extraction notebook for buildout events` - notebooks/13, data/raw/extracted.dvc
- **6**: `feat: add gridstatus labeling notebook for buildout events` - notebooks/14, data/raw/labeled.dvc
- **7-9**: `feat: update merge/panel/timeseries notebooks with real events` - 03, 04, 05 notebooks + .dvc
- **10**: `data: update datasets with real buildout events` - All .dvc files
- **11**: `feat: add EDA notebook for real buildout events` - notebooks/15
- **12**: `feat: add event study notebook for buildout announcements` - notebooks/16
- **13**: `docs: add summary statistics LaTeX tables for paper` - reports/summary_statistics.tex
- **14**: `docs: add Elsevier paper on DC buildout prediction` - report/main.tex, report/references.bib

---

## Success Criteria

### Verification Commands
```bash
# Verify DVC status
dvc status

# Verify notebooks run
jupyter nbconvert --to notebook --execute notebooks/12-*.ipynb --output /dev/null

# Verify datasets
python3 -c "import pandas as pd; df=pd.read_csv('data/processed/dataset_for_ml.csv'); print(f'{len(df)} events, {df.promise_kept.value_counts().to_dict()}')"

# Verify paper compiles
cd report && tectonic main.tex
```

### Final Checklist
- [ ] All events have source URLs
- [ ] No synthetic data artifacts (TICKER_, wrong ISOs)
- [ ] Gridstatus data covers 4+ ISOs
- [ ] ML dataset has labeled events
- [ ] EDA produces publishable figures
- [ ] Event study produces CAR results
- [ ] Paper drafted, reviewed, finalized
- [ ] All DVC datasets pushed
- [ ] All notebooks committed
