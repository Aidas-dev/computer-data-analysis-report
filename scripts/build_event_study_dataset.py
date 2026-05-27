#!/usr/bin/env python3
"""
build_event_study_dataset.py — Dedup FracTracker-GDELT merged data, build event-study ML dataset.

Step 1: Load fractracker_gdelt_merged.csv, filter is_matched=True, dedup by gdelt_url
         (keep row with highest match_score per group).
Step 2: For each deduped event, align ±60 day stock window from timeseries_features.csv.
         Add FracTracker status as label. Compute CAR per event.

Inputs:
  data/processed/fractracker_gdelt_merged.csv
  data/processed/buildout_promises_real.csv
  data/processed/timeseries_features.csv

Outputs:
  data/processed/fractracker_gdelt_deduped.csv
  data/processed/event_study_dataset.csv

No external deps beyond pandas+numpy.
"""

import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

COMPANY_TICKER_MAP = {
    "Microsoft": "MSFT",
    "Microsoft Corp": "MSFT",
    "Google": "GOOGL",
    "Alphabet": "GOOGL",
    "Amazon": "AMZN",
    "Amazon Web Services": "AMZN",
    "AWS": "AMZN",
    "Meta": "META",
    "Facebook": "META",
    "NVIDIA": "NVDA",
    "Nvidia": "NVDA",
    "Apple": "AAPL",
    "Oracle": "ORCL",
    "Digital Realty": "DLR",
    "Digital Realty Trust": "DLR",
    "Equinix": "EQIX",
    "American Tower": "AMT",
    "Prologis": "PLD",
    "Crusoe": "CRUS",
    "Crusoe Energy": "CRUS",
    "Simon Property": "SPG",
    "Simon Property Group": "SPG",
    "Public Storage": "PSA",
    "Outfront Media": "OUT",
    "Outfront": "OUT",
    "Sabra Health": "SBRA",
    "Sabra": "SBRA",
    "Hudson Pacific": "HPP",
    "Hudson Pacific Properties": "HPP",
    "Rexford Industrial": "REXR",
    "Rexford": "REXR",
    "First Industrial": "FR",
    "First Industrial Realty": "FR",
    "SITC": "SITC",
    "SITE Centers": "SITC",
}

MERGED_PATH = "data/processed/fractracker_gdelt_merged.csv"
BUILDOUT_PATH = "data/processed/buildout_promises_real.csv"
TIMESERIES_PATH = "data/processed/timeseries_features.csv"
DEDUPED_OUTPUT = "data/processed/fractracker_gdelt_deduped.csv"
EVENT_STUDY_OUTPUT = "data/processed/event_study_dataset.csv"

EVENT_WINDOW_DAYS = 60


def log(msg):
    print(f"[build-event-study] {msg}", flush=True)


def parse_gdelt_date(val):
    """Parse float/int GDELT date YYYYMMDDHHMMSS -> datetime."""
    if pd.isna(val):
        return pd.NaT
    return pd.to_datetime(str(int(float(val))), format="%Y%m%d%H%M%S", errors="coerce")


# ── Step 1: Dedup ──


def step1_dedup():
    log("=" * 60)
    log("STEP 1: Loading & deduplicating merged dataset")
    log("=" * 60)

    df = pd.read_csv(MERGED_PATH, low_memory=False)
    log(f"Total rows loaded: {len(df)}")

    matched = df[df["is_matched"] == True].copy()
    log(f"Matched rows (is_matched=True): {len(matched)}")

    # Drop rows without valid gdelt_url
    has_url = matched["gdelt_url"].notna() & (matched["gdelt_url"] != "")
    matched = matched[has_url].copy()
    log(f"Rows with non-empty gdelt_url: {len(matched)}")

    unique_before = matched["gdelt_url"].nunique()
    log(f"Unique GDELT events before dedup: {unique_before}")

    # Dedup: group by gdelt_url, keep row with highest match_score
    idx = matched.groupby("gdelt_url")["match_score"].idxmax()
    deduped = matched.loc[idx].reset_index(drop=True)
    log(f"Rows after dedup: {len(deduped)}")

    # Parse dates and map tickers
    deduped["announcement_date"] = deduped["gdelt_date"].apply(parse_gdelt_date)
    deduped["ticker"] = deduped["gdelt_company"].map(COMPANY_TICKER_MAP)

    os.makedirs("data/processed", exist_ok=True)
    deduped.to_csv(DEDUPED_OUTPUT, index=False)
    log(f"Saved: {DEDUPED_OUTPUT}")

    # ── Print summary ──

    print(f"\n{'=' * 60}")
    print(f"  DEDUP SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total rows matched                   : {len(matched)}")
    print(f"  Unique GDELT events (pre-dedup)       : {unique_before}")
    print(f"  Rows after dedup                      : {len(deduped)}")
    print(f"  Date range                            : {deduped['announcement_date'].min()}  to  {deduped['announcement_date'].max()}")
    print(f"  Unique companies                      : {deduped['gdelt_company'].nunique()}")

    print(f"\n  Matches by company (top 10):")
    for comp, cnt in deduped["gdelt_company"].value_counts().head(10).items():
        t = COMPANY_TICKER_MAP.get(comp, "?")
        print(f"    {comp:30s} ({t:5s}) : {cnt}")

    print(f"\n  Matches by FracTracker status:")
    for status, cnt in deduped["ft_status"].value_counts().items():
        print(f"    {status:40s} : {cnt}")
    print(f"{'=' * 60}\n")

    return deduped


# ── Step 2: Event study ──


def step2_event_study(deduped):
    log("=" * 60)
    log("STEP 2: Building event-study dataset")
    log("=" * 60)

    # Load timeseries
    ts = pd.read_csv(TIMESERIES_PATH, low_memory=False)
    ts["Date"] = pd.to_datetime(ts["Date"], errors="coerce")
    ts_tickers = ts["ticker"].unique()
    log(f"Timeseries loaded: {len(ts)} rows, {len(ts_tickers)} tickers")
    log(f"Timeseries date range: {ts['Date'].min()}  to  {ts['Date'].max()}")

    # Load buildout_promises_real (for context / cross-reference)
    bp = pd.read_csv(BUILDOUT_PATH, low_memory=False)
    log(f"Buildout promises loaded: {len(bp)} rows")

    # Create URL lookup from buildout promises for optional enrichment
    bp_lookup = bp.set_index("url") if "url" in bp.columns else None
    if bp_lookup is not None:
        log("Buildout promises URL lookup ready for cross-reference")

    rows = []
    missing_ticker = 0
    missing_stock = 0
    missing_window = 0

    for _, event in deduped.iterrows():
        ticker = event.get("ticker")
        ann_date = event.get("announcement_date")

        if pd.isna(ticker):
            missing_ticker += 1
            continue

        if pd.isna(ann_date):
            missing_stock += 1
            continue

        # Stock data for this ticker
        stock = ts[ts["ticker"] == ticker]
        if stock.empty:
            missing_stock += 1
            continue

        window_start = ann_date - pd.Timedelta(days=EVENT_WINDOW_DAYS)
        window_end = ann_date + pd.Timedelta(days=EVENT_WINDOW_DAYS)

        window = stock[(stock["Date"] >= window_start) & (stock["Date"] <= window_end)].copy()
        if window.empty:
            missing_window += 1
            continue

        # Enrich with buildout_promises_real if URL matches
        gdelt_url = event.get("gdelt_url", "")
        bp_enrich = {}
        if bp_lookup is not None and pd.notna(gdelt_url) and gdelt_url in bp_lookup.index:
            bp_row = bp_lookup.loc[gdelt_url]
            bp_enrich = {
                "bp_confidence": bp_row.get("confidence", np.nan),
                "bp_tone": bp_row.get("v2_tone", np.nan),
                "bp_promise_kept": bp_row.get("promise_kept", np.nan),
                "bp_label_source": bp_row.get("label_source", np.nan),
                "bp_mw_capacity": bp_row.get("mw_capacity", np.nan),
            }

        # Attach event-level columns
        window["gdelt_url"] = gdelt_url
        window["gdelt_company"] = event.get("gdelt_company", "")
        window["announcement_date"] = ann_date
        window["ft_status"] = event.get("ft_status", "")
        window["ft_facility_name"] = event.get("ft_facility_name", "")
        window["ft_power_source"] = event.get("ft_power_source", "")
        window["match_score"] = event.get("match_score", np.nan)
        window["match_type"] = event.get("match_type", "")
        window["days_from_event"] = (window["Date"] - ann_date).dt.days

        for k, v in bp_enrich.items():
            window[k] = v

        rows.append(window)

    if not rows:
        log("ERROR: No events matched with stock data.")
        return None, None

    result = pd.concat(rows, ignore_index=True)
    n_events = result["gdelt_url"].nunique()
    n_tickers = result["ticker"].nunique()

    log(f"\nEvent-study dataset rows: {len(result)}")
    log(f"Unique events with stock data: {n_events}")
    log(f"Unique tickers: {n_tickers}")
    log(f"Missing (no ticker map): {missing_ticker}")
    log(f"Missing (no stock data for ticker): {missing_stock}")
    log(f"Missing (no data in window): {missing_window}")

    # Save
    result.to_csv(EVENT_STUDY_OUTPUT, index=False)
    log(f"Saved: {EVENT_STUDY_OUTPUT}")

    # ── Per-event CAR ──

    # Daily return (simple percentage change from Close)
    result["daily_return"] = result.groupby("gdelt_url")["Close"].transform(lambda x: x.pct_change())

    # Cumulative return over each event window
    car = (
        result.groupby(["gdelt_url", "ft_status"])
        .agg(
            car=("daily_return", lambda s: (1 + s.dropna()).prod() - 1),
            ticker=("ticker", "first"),
            announcement_date=("announcement_date", "first"),
            match_score=("match_score", "first"),
            window_days=("days_from_event", lambda d: f"{d.min()}:{d.max()}"),
            n_days=("days_from_event", "count"),
        )
        .reset_index()
    )

    # ── Print coverage & CAR ──

    total = len(deduped)
    print(f"\n{'=' * 60}")
    print(f"  EVENT STUDY SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total deduped events               : {total}")
    print(f"  Events with stock data             : {n_events}")
    print(f"  Coverage rate                      : {n_events / total * 100:.1f}%")
    print(f"  Missing (no ticker map)            : {missing_ticker}")
    print(f"  Missing (no stock for ticker)      : {missing_stock}")
    print(f"  Missing (no data in ±{EVENT_WINDOW_DAYS}d window): {missing_window}")
    print(f"  Total event-study rows             : {len(result)}")
    print(f"  Tickers represented                : {n_tickers}")

    print(f"\n  CAR by FracTracker status:")
    print(f"  {'Status':30s} {'Mean':>10s} {'Median':>10s} {'Std':>10s} {'N':>6s}")
    print(f"  {'-' * 30} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 6}")
    for status_val, grp in car.groupby("ft_status"):
        mean_car = grp["car"].mean()
        median_car = grp["car"].median()
        std_car = grp["car"].std()
        count = len(grp)
        print(f"  {str(status_val):30s} {mean_car:>+10.4f} {median_car:>+10.4f} {std_car:>10.4f} {count:>6d}")

    print(f"{'=' * 60}\n")

    return result, car


def main():
    log("Starting build_event_study_dataset.py")

    for path in [MERGED_PATH, BUILDOUT_PATH, TIMESERIES_PATH]:
        if not os.path.exists(path):
            log(f"ERROR: Required file not found: {path}")
            sys.exit(1)

    deduped = step1_dedup()
    step2_event_study(deduped)
    log("Done.")


if __name__ == "__main__":
    main()
