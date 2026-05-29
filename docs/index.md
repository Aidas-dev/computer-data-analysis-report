# AI Data Center Buildout Promises vs. Reality

[![Compile LaTeX Report](https://github.com/Aidas-dev/computer-data-analysis-report/actions/workflows/compile_latex.yml/badge.svg)](https://github.com/Aidas-dev/computer-data-analysis-report/actions/workflows/compile_latex.yml)

## Abstract

This study investigates the gap between corporate announcements of AI data center buildouts and their realized outcomes. We combined the GDELT Project's event database with the FracTracker Open U.S. Data Centers Tracker to compile and analyze 5,295 buildout announcements from 17 major technology and REIT companies spanning 2020 to 2026, alongside 1,520 known data center facilities. Through systematic cross-referencing, we produced 428 matched events with validated facility statuses (Operating, Cancelled, or Proposed). Our methodology applies event study analysis (cumulative abnormal returns), sentiment analysis of announcement tone, and machine learning classification to identify the key determinants of project completion. We find that announcements associated with operating facilities show a mean cumulative abnormal return of +9.6%, while those tied to cancelled projects show -5.1%. V2Tone (tone) and megawatt capacity emerge as the two strongest predictors of outcome, each contributing approximately 43% to model accuracy. The association between announcement tone and actual project outcome approaches statistical significance (p=0.053). These findings suggest that market signals and project scale carry meaningful information about the likelihood of data center delivery.

## Key Findings

- 428 GDELT-FracTracker matched events across 17 major technology and REIT companies
- Operating announcements: +9.6% mean CAR; Cancelled: -5.1% mean CAR
- Logistic Regression achieves 40.7% accuracy (3-class), Random Forest 33.3%
- Announcement tone and MW capacity are the strongest predictors of project outcome

## Download

[Download the Full Paper (PDF)](AI_Data_Center_Report.pdf)

## Data & Code

All data, notebooks, and scripts used in this study are available in the repository:

- **Data**: [`data/`](https://github.com/Aidas-dev/computer-data-analysis-report/tree/main/data) — raw, interim, and processed datasets (tracked via DVC)
- **Notebooks**: [`notebooks/`](https://github.com/Aidas-dev/computer-data-analysis-report/tree/main/notebooks) — data extraction, analysis, and ML training workflows
- **Report**: [`report/`](https://github.com/Aidas-dev/computer-data-analysis-report/tree/main/report) — LaTeX source (`main.tex`) for the full paper

## Authors

**Aidas Krisciunas**, **Domas Pitrenas**, **Jokubas Narvydas**, **Karolis Boguska**

Faculty of Economics and Business Administration (FEBA)  
Vilnius University

[View the Repository](https://github.com/Aidas-dev/computer-data-analysis-report)
