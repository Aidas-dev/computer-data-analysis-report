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

## External Data Sources

### Data Center Project Databases
- **FracTracker Open U.S. Data Centers Tracker** — `https://www.fractracker.org/2026/04/open-u-s-data-centers-tracker/` — 1,520 sites, 53 fields. Downloaded via `scripts/fetch_fractracker.py`. Tracks status (Proposed/Operating/Construction/Cancelled), MW capacity, operator, location. DVC-tracked at `data/raw/fractracker_datacenters.csv`.
- **Silicon Report Datacenter Tracker** — `https://www.siliconreport.com/datacenters/tracker` — 5,759 US facilities, status breakdown by state, MW capacity, operator leaderboard.
- **AI Data Center Index** — `https://aidatacenterindex.com/pipeline/` — 149 projects, 101 GW globally. Downloadable pipeline data by stage (Announced/Planned/Construction/Operational).
- **Scrutica Facility Directory** — `https://scrutica.com/facilities` — 4,529 facilities across 110 countries. Filterable by type, status, country, owner.
- **Michael Bommarito Data Center Projects DB** — `https://michaelbommarito.com/wiki/datacenters/projects/` — 604 projects, $1,123B investment, 131,731 MW. Curated wiki with investment tier, purpose, and sponsor data.

### Construction & Permitting
- **Buildermuse Data Center Permit Tracker 2026** — `https://buildermuse.com/commercial/tracking-every-data-center-permit-filed-in/` — Q1 2026: 20 major permits, 2,192 MW, $18.8B. Leading indicator (permits to construction 18-36 months).

### Government & Energy
- **DOE IM3 Projected US Data Center Locations** — `https://data.msdlive.org/records/8fd09-xhn32/latest` — Model-predicted DC facility locations through 2035, 20 scenarios, GeoJSON format.

Our GDELT-derived dataset (5,295 buildout events from 17 companies) supplements these external sources with high-frequency press coverage since 2020.
