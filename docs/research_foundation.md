# Foundational Research: AI Data Center Buildout Promises vs. Reality

## Executive Summary

This research project investigates what parameters actually influence whether an AI data center buildout promise is kept in the United States. We build a predictive ML model trained on historical projects (finished, stalled, and failed) to forecast the feasibility and success probability of currently ongoing or newly promised projects.

---

## 1. Research Question

**Primary Question:** What parameters most accurately predict whether an AI data center buildout promise will be delivered on time and at the promised capacity?

**Secondary Questions:**
- Do larger companies (by market cap) deliver more reliably?
- Does grid interconnection queue depth affect delivery probability?
- Do macroeconomic conditions (interest rates, market volatility) correlate with project success?
- Are there regional patterns (ERCOT vs. CAISO vs. PJM)?

---

## 2. Scope & Definitions

### Geographic Scope
- **Primary:** United States major grid operators (ISOs)
- **Target ISOs:** ERCOT, CAISO, MISO, PJM, NYISO, SPP

### Target Companies
We categorize data center builders into tiers:

| Tier | Description | Examples | Market Cap |
|------|-------------|----------|------------|
| **TIER_1** | Hyperscalers | MSFT, GOOGL, AMZN, META, NVDA, AAPL | >$100B |
| **TIER_2** | Large Data Center REITs | EQIX, DLR, AMT, PLD, SPG, PSA | $10B-$100B |
| **TIER_3** | Mid-tier Colocation | OUT, SBRA, HPP | $1B-$10B |
| **TIER_4** | Smaller/Speculative | REXR, FR, SITC | <$1B |

### Success Metrics (Target Variables)
1. **Promise Kept (Binary):** 1 = Delivered, 0 = Failed/Withdrawn/Cancelled
2. **Timeline Adherence:** Days early/late vs. promised date
3. **Capacity Delivered:** Actual MW vs. promised MW percentage

---

## 3. Feature Engineering

### Company Financial Features (from yfinance)
- Market capitalization, Enterprise value
- Revenue, EBITDA, Profit margins
- ROA, ROE, Return on assets
- Debt-to-equity, Current ratio, Quick ratio
- Dividend yield, Payout ratio
- Beta (volatility), PEG ratio
- Forward/Trailing P/E, Price-to-Book

### Grid/Infrastructure Features (from gridstatus)
- Interconnection queue position
- Requested capacity (MW)
- Project status (Operating, In Queue, Withdrawn, Suspended)
- Queue date, Requested online date
- ISO region

### Temporal Features (derived)
- Announcement quarter, month, day of week
- Days/months from announcement to target
- Construction season indicator (ideal: Q2-Q3)
- Fiscal year timing

### Macro Economic Features (from yfinance/fredapi)
- 10-Year Treasury yield (interest rate proxy)
- VIX (market volatility index)
- S&P 500 momentum
- GDP growth rate (FRED)
- Inflation rate (FRED)

### Census/Demographic Features (from pytidycensus) - *Future*
- Population by city/metro area
- Median household income
- Employment by industry (tech talent pool)
- Housing density

---

## 4. Data Sources (100% Free Python APIs)

### Active Data Sources

| Source | Python Library | Data Extracted |
|--------|---------------|----------------|
| Stock Prices & Fundamentals | `yfinance` | OHLCV, market cap, revenue, debt ratios |
| Grid Interconnection Queues | `gridstatus` | CAISO, MISO queue projects, MW capacity, status |
| SEC Filings | `sec-edgar-downloader` | 10-K, 10-Q for financial analysis |

### Pending Data Sources (API Keys Required)

| Source | Python Library | Data Extracted |
|--------|---------------|----------------|
| US Census Demographics | `pytidycensus` | Population, income, employment by location |
| Federal Reserve Economic Data | `fredapi` | GDP, inflation, interest rates, employment |

> **FRED API Key:** `4aeb77367579a1c44a91f61ed6b991fe` (stored in `.env`, added to Colab Secrets as `FRED_API_KEY`)
> **Census API:** Currently down — check https://api.census.gov/data/key_signup.html

---

## 5. Dataset Summary

### Current DVC-Tracked Files

| File | Rows | Description |
|------|------|-------------|
| `company_financials_expanded.csv` | 10,000 | 20 tickers × 500 days OHLCV + fundamentals |
| `company_financial_ratios.csv` | 16 | 22 financial metrics per company |
| `buildout_promises_expanded.csv` | 34 | Target variable: promises with outcomes |
| `buildout_promises_enhanced.csv` | 34 | Same + temporal features |
| `grid_interconnection_queue.csv` | 6,043 | CAISO + MISO interconnection projects |
| `macro_economic_indicators.csv` | 9 | Quarterly Treasury, VIX, S&P data |

---

## 6. Methodology

### Phase 1: Data Collection
1. Fetch company data from yfinance (20 tickers, 2-year history)
2. Fetch grid queues from gridstatus (CAISO, MISO)
3. Download SEC 10-K filings for financial analysis
4. Build target variable: manual collection of announced projects with outcomes

### Phase 2: Feature Engineering
1. Merge company financials with project announcements by date
2. Add ISO/region features from grid data
3. Add temporal features (quarter, month, seasonality)
4. One-hot encode company tier (TIER_1-4)

### Phase 3: Exploratory Data Analysis
1. Correlation analysis: Which features predict success?
2. Distribution analysis: Class imbalance handling
3. Feature selection: Remove redundant variables

### Phase 4: Modeling
- **Baseline:** Logistic Regression
- **Primary:** XGBoost Classifier (GPU-accelerated in Colab)
- **Comparison:** Random Forest

### Phase 5: Evaluation
- Accuracy, Precision, Recall, F1-Score
- Feature Importance Analysis
- ROC-AUC curve

---

## 7. Expected Outcomes

1. **Feature Importance Ranking:** Which parameters matter most for predicting buildout success?
2. **Success Probability Model:** Trained classifier for new project feasibility
3. **Regional Analysis:** Which ISO regions have highest failure rates?
4. **Company Tier Analysis:** Do TIER_1 companies deliver more reliably?

---

## 8. Technical Stack

| Component | Technology |
|----------|------------|
| Development Environment | Google Colab / GitHub Codespaces |
| Data Storage | Oracle Cloud Object Storage (via DVC) |
| Version Control | Git + GitHub |
| Notebooks | Jupyter |
| ML Models | scikit-learn, XGBoost |
| Report Generation | LaTeX (Elsevier elsarticle template) |
| CI/CD | GitHub Actions |

---

## 9. Timeline (1-Month Sprint)

| Week | Tasks |
|------|-------|
| **Week 1** | Data collection (yfinance, gridstatus, SEC), build target variable |
| **Week 2** | Feature engineering, EDA |
| **Week 3** | Model training (XGBoost), evaluation |
| **Week 4** | Analysis, LaTeX report writing, presentation |

---

## 10. References

- **gridstatus Documentation:** https://gridstatus.readthedocs.io/
- **yfinance Documentation:** https://pypi.org/project/yfinance/
- **SEC Edgar:** https://www.sec.gov/edgar.shtml
- **pytidycensus:** https://pytidycensus.readthedocs.io/
- **FRED API:** https://fred.stlouisfed.org/

---

*Last Updated: April 2026*
*Team: 4 Researchers*
*Repository: https://github.com/Aidas-dev/computer-data-analysis-report*
