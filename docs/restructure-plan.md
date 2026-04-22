# Data Restructuring Plan

**Goal**: Leverage the 10K+ row datasets (financials, grid, macro) to enable statistically meaningful analysis on a 34-row promise dataset.
**Constraint**: 34 promise events alone is insufficient for tabular ML. Work around it by using the full time-series as primary analytical unit.

---

## Problem Statement

| Current Approach | Limitation |
|---|---|
| Promise-centric merge (34 rows) | Small N → high variance, no holdout testing |
| Financial data as background join | 10K rows exist but used as static lookup |
| Macro indicators at quarter level | No time-series feature engineering |

**Core Insight**: Each promise anchors to a (Company, Announcement Quarter, ISO) triple. We can build features for every company-quarter and use promises as labels on top.

---

## Target Datasets

### 1. `quarterly_panel.csv` — Panel Dataset

**Structure**: (Company × Quarter) grid, one row per quarter per company, ~500 rows.

| Column | Source | Description |
|--------|--------|-------------|
| `ticker` | buildout | Company identifier |
| `quarter` | derived | Quarter period (e.g., 2021Q1) |
| `q_avg_close` | financials | Mean daily Close for quarter |
| `q_avg_volume` | financials | Mean daily Volume |
| `q_volatility` | financials | Stddev of daily Close |
| `q_market_cap` | financials | Mean market cap |
| `q_revenue` | financials | Mean quarterly revenue |
| `q_ebitda` | financials | Mean EBITDA |
| `debt_to_equity` | ratios | Static per ticker |
| `current_ratio` | ratios | Static per ticker |
| `profit_margin` | ratios | Static per ticker |
| `return_on_assets` | ratios | Static per ticker |
| `return_on_equity` | ratios | Static per ticker |
| `real_gdp` | macro | Real GDP for quarter |
| `core_cpi` | macro | Core CPI for quarter |
| `fed_funds_rate` | macro | Fed Funds Rate |
| `unemployment_rate` | macro | Unemployment Rate |
| `iso_queue_depth` | grid | Number of projects in queue that quarter |
| `promise_kept` | buildout | Target label if promise exists that quarter, else NaN |
| `promise_mw` | buildout | MW promised if promise exists, else 0 |

**Why this works**: ~500 rows (8 companies × ~62 quarters) is statistically meaningful for regression, feature importance, and cross-validation.

---

### 2. `timeseries_features.csv` — Time-Series Feature Dataset

**Structure**: Rolling-window features per (Ticker, Date), ~10K rows aligned with financial daily observations.

| Column | Source | Description |
|--------|--------|-------------|
| `ticker` | financials | Company identifier |
| `date` | financials | Daily date |
| `Close` | financials | Daily close price |
| `Volume` | financials | Daily volume |
| `sma_20` | derived | 20-day Simple Moving Average |
| `sma_60` | derived | 60-day SMA |
| `volatility_20d` | derived | 20-day rolling stddev |
| `momentum_20d` | derived | % change over 20 days |
| `rsi_14` | derived | 14-day Relative Strength Index |
| `volume_ma_ratio` | derived | Volume / 20-day volume MA |
| `qtr_return` | derived | Quarter-to-date return |
| `yoy_return` | derived | Year-over-year return |
| `fed_funds_rate` | macro | Latest Fed Funds Rate |
| `unemployment_rate` | macro | Latest Unemployment Rate |
| `iso_queue_depth` | grid | Queue depth at this date |
| `promise_label` | buildout | Binary: promise kept in this quarter? |

**Why this works**: Enables time-series models (LSTM, Prophet, ARIMA), regime detection, and technical indicator analysis.

---

## Implementation Steps

### Step 1: Build Quarterly Panel

```
notebooks/04-quarterly-panel.ipynb

1. Load company_financials_expanded.csv (with Date column)
2. Load company_financial_ratios.csv
3. Load macro_economic_indicators.csv
4. Load grid_interconnection_queue.csv
5. Load buildout_promises_expanded.csv (labels)

For each (ticker, quarter):
   → Aggregate financials: mean Close, mean Volume, std Close, mean market_cap
   → Join static ratios (debt_to_equity, profit_margin, etc.)
   → Join macro: GDP, CPI, Fed Funds, Unemployment (quarterly resample)
   → Join grid: iso_queue_depth (aggregated by ISO × quarter)
   → Label: if a promise exists in that quarter → promise_kept, promised_mw

Output: data/processed/quarterly_panel.csv (~500 rows × 25 features)
```

### Step 2: Build Time-Series Features

```
notebooks/05-timeseries-features.ipynb

1. Load company_financials_expanded.csv
2. Load macro_economic_indicators.csv
3. Load grid_interconnection_queue.csv
4. Load buildout_promises_expanded.csv (labels)

For each row in financials:
   → Calculate rolling features: SMA(20/60), volatility(20d), momentum, RSI
   → Join macro at exact date (forward-fill for daily series)
   → Join grid iso_queue_depth at exact date
   → Label: set promise_label = promise_kept for that quarter

Output: data/processed/timeseries_features.csv (~10K rows × 17 features)
```

### Step 3: Train Models on Panel

```
notebooks/06-panel-ml.ipynb

1. Load quarterly_panel.csv
2. Filter to quarters with promise labels (promise_kept not NaN) → 34 rows
3. Split: 80% train / 20% test (stratified by company_tier)
4. Train XGBoost on full panel for feature importance
5. Evaluate on held-out promises
6. Generate feature importance → write to report

Metrics: Accuracy, ROC-AUC, Precision, Recall, Feature Importance
```

---

## Data Sources Used

| Source | File | Key Variables |
|--------|------|-------------|
| Company financials | `company_financials_expanded.csv` | Close, Volume, market_cap |
| Financial ratios | `company_financial_ratios.csv` | debt_to_equity, profit_margin |
| Grid interconnection | `grid_interconnection_queue.csv` | iso_queue_depth |
| Macro indicators | `macro_economic_indicators.csv` | GDP, CPI, Fed Funds, Unemployment |
| Promise labels | `buildout_promises_expanded.csv` | promise_kept, promised_mw |

---

## Output Files

| File | Rows | Columns | Purpose |
|------|------|--------|--------|
| `quarterly_panel.csv` | ~500 | 25 | Regression, feature importance |
| `timeseries_features.csv` | ~10,000 | 17 | Time-series models, regime analysis |

---

## Verification Criteria

- [ ] `quarterly_panel.csv` ≥ 100 rows (sufficient for regression)
- [ ] `timeseries_features.csv` ≥ 5,000 rows (sufficient for time-series)
- [ ] Both files merge cleanly with promise labels (34 promise rows match)
- [ ] Notebooks execute without errors (`nbconvert --execute`)
- [ ] DVC tracks output files
- [ ] Git commits push to main