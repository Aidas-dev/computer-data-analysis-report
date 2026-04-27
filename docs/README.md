# AI Data Center Buildout Promises - Project Documentation

## Quick Start

1. **Clone & Setup**
   ```bash
   git clone https://github.com/Aidas-dev/computer-data-analysis-report.git
   cd computer-data-analysis-report
   ```
2. **Colab**: Run `notebooks/00-colab-setup.ipynb` first
3. **Pull Data**: `dvc pull`

## Notebooks

| # | Purpose |
|---|---------|
| 00 | Colab setup + API keys |
| 01 | yfinance data extraction |
| 02 | ML training example |
| 03 | Data merging |
| 04 | Quarterly panel |
| 05 | Timeseries features |
| 06 | Panel ML |
| 07 | Analyst sentiment |
| 08 | Census data extraction |
| 09 | Full pipeline (regenerate all) |

## Data Files

### Raw Data (`data/raw/`)
| File | Rows × Cols | Description |
|------|-------------|-------------|
| `buildout_promises_expanded.csv` | 34 × 29 | Promise events + Census |
| `company_financials_expanded.csv` | 13,816 × 10 | Daily OHLCV |
| `company_financial_ratios.csv` | 19 × 22 | Company ratios |
| `macro_economic_indicators.csv` | 1,665 × 7 | FRED data |
| `grid_interconnection_queue.csv` | 6,043 × 5 | Grid queue |
| `census_counties.csv` | 28 × 13 | County demographics |
| `census_demographics.csv` | 52 × 13 | State demographics |

### Processed (`data/processed/`)
| File | Rows × Cols | Labels |
|------|-------------|--------|
| `quarterly_panel.csv` | 231 × 36 | 25 |
| `timeseries_features.csv` | 13,805 × 14 | 1,185 |

## Census Variables

Both county and state files include:
- `total_pop` — Population
- `median_income` — Median household income
- `housing_units` — Total housing units
- `median_home_value` — Median home value
- `median_rent` — Median rent
- `unemployed` / `unemployment_rate`
- `workers_16_plus` — Labor force
- `bachelors_degree` / `pct_bachelors`
- `doctorate`

## API Keys

Store in `.env` or Colab Secrets:
- `CENSUS_API_KEY` — Get free at https://api.census.gov/data/key_signup.html
- `FRED_API_KEY` — Get free at https://fred.stlouisfed.org/fredapi/
- `OCI_ACCESS_KEY` / `OCI_SECRET_KEY` — For DVC remote

## DVC

```bash
dvc pull          # Download data
dvc push          # Upload changes
dvc status        # Check status
```

Remote: Oracle Cloud S3 (frankfurt-1)
