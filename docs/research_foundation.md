# Foundational Research: AI Data Center Buildout Promises vs. Reality

## Core Premise
Investigating what parameters actually influence whether an AI data center buildout promise is kept, evaluated against the current economic climate. The ultimate goal is to build a predictive ML model trained on historical (finished/failed) projects to forecast the feasibility and success probability of *currently ongoing or newly promised* projects.

## Scope & Definitions
- **Target Companies**: Global scope across the entire industry (Hyperscalers, Colo & GPU Clouds, Enterprise, and AI Startups).
- **Success Metrics (The Target Variables)**: 
  - Timeline Adherence (Did it come online when promised?)
  - Capacity Delivered (Did it hit the promised Megawatt / GPU threshold?)
- **Key Parameters (The Features)**:
  - Economic / Financial (Firm size, capital access, stock performance)
  - Infrastructure Constraints (Grid availability, power availability)
  - Supply Chain (GPU/Transformer lead times)
  - Project specific (Scale/MW, Location)

## Methodology Outline
1. **Data Collection**: Assemble a dataset of past AI data center projects (successful, delayed, and failed).
2. **Exploratory Data Analysis (EDA)**: Understand correlations between scale, location, firm size, and delays/failures.
3. **Modeling**: Run simple regressions and advanced ML classification models.
4. **Inference/Application**: Feed currently ongoing/promised projects into the trained model to classify their probability of success/feasibility.

## Feasibility & Scoping Assessment (1-Month Timeline)
**Risk Level**: 🔴 High (Too broad for a 1-month timeframe if not carefully constrained).

*Why?* Assembling a project-level dataset globally is incredibly labor-intensive. While Yahoo Finance provides excellent firm-level financial data (CAPEX, cash flow, stock price), it *does not* provide project-level data (e.g., "Meta's Iowa data center delayed by 6 months due to transformer shortage"). 

### Recommended Scoping Adjustments for a 1-Month Project:
To ensure completion, we must shrink the data collection phase to 1-1.5 weeks. 
- **Option A (Constrain by Geography)**: Focus only on the US. This allows us to use public US power grid interconnection queues (like ERCOT in Texas or PJM in Virginia/East Coast), which publicly list stalled, active, and withdrawn power requests for data centers.
- **Option B (Constrain by Company)**: Focus *globally*, but strictly limit the dataset to the Top 10-15 public companies (e.g., MSFT, GOOG, AMZN, META, EQIX, DLR). We can use NLP to scrape earnings call transcripts to build the dataset programmatically.

### Proposed Data Sources (Beyond Yahoo Finance)
1. **Financial & Firm Level**: Yahoo Finance (yfinance), SEC EDGAR (10-K/10-Q CAPEX disclosures).
2. **Project Level (News & Transcripts)**: Seeking Alpha / Motley Fool earnings transcripts (for hyperscaler project updates).
3. **Grid / Power Level**: Regional Transmission Organization (RTO) public interconnection queues (e.g., PJM, ERCOT, CAISO) - *Goldmine for identifying "failed" or "stalled" projects.*
4. **Industry Reports**: Synergy Research Group, DatacenterHawk, Data Center Dynamics (scraping public press releases).
