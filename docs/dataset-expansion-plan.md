# Dataset Expansion Plan

**Goal**: Expand AI data center buildout promises dataset for tabular ML.

**Current State** (from `(b5)`):
- `quarterly_panel.csv`: 231 rows × 30 cols, 11 tickers, **25 labeled** (19 kept / 6 not kept = 76% rate)
- `timeseries_features.csv`: 13,805 rows × 14 cols, **1,185 promise labels** (8.6% rate)
- Core bottleneck: **34 promise events** (23 kept + 11 pending)

---

## Bottleneck Analysis

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

### Phase 1: Quick Wins (1-2 days)

- [ ] Pull analyst recommendations + price targets for all 11 tickers
- [ ] Merge into quarterly_panel.csv
- [ ] Add to ML training
- **Expected**: +7 features, same rows

### Phase 2: Expand Labels (1 week)

- [ ] Extract additional promise events from SEC 10-K risk factors
- [ ] Search news/API for 2024-2025 announcements
- [ ] Validate and merge into promise dataset
- **Expected**: +50-80 new promises

### Phase 3: Add Features (2-3 days)

- [ ] Fetch options IV for key dates
- [ ] Fetch earnings surprises
- [ ] Merge all into timeseries_features.csv
- **Expected**: +10 features for 13,805 rows

### Phase 4: Expand Universe (1 week)

- [ ] Identify acquired companies with historical data
- [ ] Add new active expanders
- [ ] Retrain and compare
- **Expected**: +4 tickers, +200+ quarterly rows

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