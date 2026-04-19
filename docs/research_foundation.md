# Foundational Research: AI Data Center Buildout Promises vs. Reality

## Core Premise
Investigating what parameters actually influence whether an AI data center buildout promise is kept, evaluated against the current economic climate. The ultimate goal is to build a predictive ML model trained on historical (finished, stalled, and failed) projects to forecast the feasibility and success probability of *currently ongoing or newly promised* projects.

## Scope & Definitions (Officially Constrained for 1-Month Timeline)
- **Geographic Scope**: United States (PJM, ERCOT, CAISO, NYISO).
- **Target Companies**: Hyperscalers and Colo providers building in the US (e.g., MSFT, GOOG, AMZN, META, EQIX, DLR, CoreWeave).
- **Success Metrics (The Target Variables)**: 
  - Timeline Adherence (Did it come online when promised?)
  - Capacity Delivered (Did it hit the promised Megawatt threshold?)
  - Status (Active vs. Withdrawn vs. Suspended)
- **Key Parameters (The Features)**:
  - Economic / Financial (Firm size, capital access, stock performance, interest rates)
  - Infrastructure Constraints (Grid availability, power capacity)
  - Project specific (Scale/MW, specific US ISO region)

## Definitive Data Extraction Stack (100% Free & Open Source)
To guarantee the feasibility of data collection without manual scraping, we rely entirely on free Python APIs:

1. **`gridstatus` (Grid Infrastructure Data)**
   - Extracts real-world Interconnection Queues from major US grid operators (PJM, ERCOT, CAISO).
   - *Why?* This provides the ground truth on data center power requests, Megawatt scale, and if projects actually reached "In Service" or were "Withdrawn" (failed) / "Suspended" (stalled).

2. **`sec-edgar-downloader` (Corporate Promises & CAPEX)**
   - Automatically downloads 10-K and 10-Q reports directly from the US government's SEC database.
   - *Why?* To extract the actual hyperscaler/colo promises regarding data center scale and capital expenditure timelines.

3. **`yfinance` (Macroeconomic & Financial Data)**
   - Scrapes Yahoo Finance's public API.
   - *Why?* To gather stock prices, interest rates, and firm-level financial performance to use as economic predictors in our model.

## Methodology Outline
1. **Data Collection**: Fetch grid interconnection queues (`gridstatus`), merge with firm-level financials (`yfinance`), and supplement with corporate text (`sec-edgar-downloader`).
2. **Exploratory Data Analysis (EDA)**: Understand correlations between scale, region, firm size, and project failures (Withdrawn status).
3. **Modeling**: Run simple regressions and advanced ML classification models (e.g., Random Forest, XGBoost).
4. **Inference/Application**: Feed currently ongoing/promised US projects into the trained model to classify their probability of success/feasibility.
