# Dataset Expansion Plan (COMPLETED)

**Goal**: Expand AI data center buildout promises dataset for tabular ML.

**Status**: Phases 1 & 3 complete ✅

---

## What's Done

### ✅ Phase 1: Analyst Sentiment
- Added yfinance recommendations (strongBuy, buy, hold)
- Added analyst price targets (target_mean, target_premium_pct)
- Added earnings features (earnings_growth, profit_margins, operating_margins)

### ✅ Phase 3: Census Data
- County-level: 28 counties × 13 variables
- State-level: 52 states × 13 variables
- Variables: population, income, home value, rent, unemployment, education

### ✅ Unified Pipeline
- Created `notebooks/09-full-pipeline.ipynb` to regenerate everything

---

| Issue | Severity | Impact |
|---|---|---|
| Label sparsity in quarterly panel | **Critical** | 25 labeled / 231 rows = 10.8% |
| Only 8 companies | High | Limited cross-company generalization |
| No analyst sentiment | Medium | Missing key signal |
| Simple labels (kept/pending) | Medium | No uncertainty signal |

---

## Expansion Options

### Option A: Add Analyst Sentiment (Quick Win)

**What**: Fetch `ticker.recommendations` + `ticker.analyst_price_targets` via yfinance and merge quarterly.

| Metric | Source | Rows Impact |
|---|---|---|
| Buy/Sell/Hold distribution | yfinance.recommendations | +3 cols × 231 rows |
| Price target spread | yfinance.analyst_price_targets | +3 cols × 231 rows |
| Mean target premium | Derived | +1 col × 231 rows |

**Target**: Add 7 features to quarterly_panel.csv.

**Effort**: Small — one notebook cell.

**Priority**: 1

---

### Option B: Expand Promise Events (Core)

**What**: Identify and add more data center buildout promise events beyond the current 34.

| Source | Potential | Effort |
|---|---|---|
| SEC 10-K/10-Q risk factors | 50-100 new locations | Medium |
| News/API announcements | 20-50 announcements | Medium |
| State utility dockets | Varies by state | High |
| Data center operator press | 10-30 expansions | Medium |

**Target**: +50 promise events (total 80+).

**Priority**: 1

---

### Option C: Add Options Implied Volatility (Medium)

**What**: Fetch IV from options chains for significant dates.

| Metric | Source | Rows Impact |
|---|---|---|
| ATM IV | yfinance.option_chain | +1 col × 1,185 labeled rows |
| IV rank | Derived | +1 col × 1,185 rows |
| OI-weighted IV | Derived | +1 col × 1,185 rows |

**Effort**: Medium — need to fetch by expiry and ticker.

**Priority**: 2

---

### Option D: Add Earnings Features (Medium)

**What**: Quarterly earnings as regime indicators.

| Metric | Source | Cols |
|---|---|---|
| EPS surprise % | yfinance earnings | +3 cols |
| Revenue surprise % | yfinance earnings | +2 cols |
| Forward EPS | yfinance info | +2 cols |

**Priority**: 2

---

### Option E: Expand Company Coverage

**What**: Add more tickers to the data center / infrastructure universe.

| Ticker | Company | Rationale |
|---|---|---|
| CyrusOne (CONE) | Acquired by DigiRealty | Historical promises |
| CoreSite (COR) | Acquired by American Tower | Historical promises |
| QTS (QTS) | Acquired by BlackRock | Historical promises |
| Switch (SWCH) | Acquired by Schneider | Historical promises |
|晓 Chia (New) | GreenLane / Aligned | Active expansions |

**Target**: +5 tickers (total 16).

**Priority**: 3

---

## Recommended Roadmap

### ✅ Phase 1: Quick Wins (COMPLETED)
- [x] Pull analyst recommendations + price targets for all 11 tickers
- [x] Merge into quarterly_panel.csv
- [x] Add to ML training

### ⏳ Phase 2: Expand Labels (pending)
- [ ] Extract additional promise events from SEC 10-K risk factors
- [ ] Search news/API for 2024-2025 announcements

### ✅ Phase 3: Add Features (COMPLETED)
- [x] Fetch options IV (noted: yfinance IV returns near-zero)
- [x] Fetch earnings from ticker.info
- [x] Add Census county + state demographics

### ⏳ Phase 4: Expand Universe (pending)
- [ ] Add acquired company tickers (CONE, QTS, COR)

---

## Output Targets

| Dataset | Target Rows | Target Cols | Label Count |
|---|---|---|---|
| quarterly_panel.csv | 500+ | 40+ | 100+ |
| timeseries_features.csv | 20,000+ | 25+ | 2,000+ |

---

## Dependencies

- yfinance for all new features (no API key needed)
- SEC EDGAR for promise extraction (free)
- Existing notebooks 04, 05 for merging logic

---

## Risks

1. **Label quality**: New promises must be validated (announcement → completed)
2. **Look-ahead bias**: Ensure features are known at prediction time
3. **Class imbalance**: Will increase — use stratified sampling or class weights