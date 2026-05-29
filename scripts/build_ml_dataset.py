#!/usr/bin/env python3
"""
build_ml_dataset.py — Build minimum viable ML dataset from real buildout events.

Rebuilds dataset_for_ml.csv from real 5,295 buildout_promises_real.csv events.
Company name → ticker mapping, date features, derived features, label preserved.

Input:  data/processed/buildout_promises_real.csv
Output: data/processed/dataset_for_ml.csv
"""
import os
import sys
import subprocess
import warnings
import argparse

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdelt_utils import parse_v2_tone

warnings.filterwarnings('ignore')

COMPANY_TICKER_MAP = {
    'Microsoft': 'MSFT', 'Microsoft Corp': 'MSFT',
    'Google': 'GOOGL', 'Alphabet': 'GOOGL',
    'Amazon': 'AMZN', 'Amazon Web Services': 'AMZN', 'AWS': 'AMZN',
    'Meta': 'META', 'Facebook': 'META',
    'NVIDIA': 'NVDA', 'Nvidia': 'NVDA',
    'Apple': 'AAPL',
    'Oracle': 'ORCL',
    'Digital Realty': 'DLR', 'Digital Realty Trust': 'DLR',
    'Equinix': 'EQIX',
    'American Tower': 'AMT',
    'Prologis': 'PLD',
    'Crusoe': 'CRUS', 'Crusoe Energy': 'CRUS',
    'Simon Property': 'SPG', 'Simon Property Group': 'SPG',
    'Public Storage': 'PSA',
    'Outfront Media': 'OUT', 'Outfront': 'OUT',
    'Sabra Health': 'SBRA', 'Sabra': 'SBRA',
    'Hudson Pacific': 'HPP', 'Hudson Pacific Properties': 'HPP',
    'Rexford Industrial': 'REXR', 'Rexford': 'REXR',
    'First Industrial': 'FR', 'First Industrial Realty': 'FR',
    'SITC': 'SITC', 'SITE Centers': 'SITC',
}

INPUT_PATH = "data/processed/buildout_promises_real.csv"
OUTPUT_PATH = "data/processed/dataset_for_ml.csv"


def parse_tone(tone_str):
    """Parse v2_tone CSV string -> first 5 numeric components + count."""
    if pd.isna(tone_str) or not isinstance(tone_str, str):
        return pd.Series([np.nan]*6)
    parts = tone_str.split(',')
    avg_tone = parse_v2_tone(tone_str)  # first component via shared util
    vals = [avg_tone]
    for i in range(1, 5):
        try:
            vals.append(float(parts[i]) if i < len(parts) else np.nan)
        except (ValueError, IndexError):
            vals.append(np.nan)
    try:
        count = int(parts[6]) if len(parts) > 6 else np.nan
    except (ValueError, IndexError):
        count = np.nan
    vals.append(count)
    return pd.Series(vals)


def main():
    dry = "--dry-run" in sys.argv
    log("Build ML Dataset: rebuilding dataset_for_ml.csv from real data")

    if not os.path.exists(INPUT_PATH):
        log(f"ERROR: Input not found: {INPUT_PATH}")
        sys.exit(1)

    df = pd.read_csv(INPUT_PATH)
    log(f"Loaded {len(df)} events from {INPUT_PATH}")

    # ── Base columns to preserve ──
    base_cols = {
        'company': 'company',
        'date': 'announcement_date_raw',
        'location_city': 'location_city',
        'location_state': 'location_state',
        'mw_capacity': 'mw_capacity',
        'target_completion_date': 'target_completion_date',
        'confidence': 'confidence',
        'extracted_text_snippet': 'extracted_text_snippet',
        'promise_kept': 'promise_kept',
        'label_source': 'label_source',
        'url': 'url',
        'source_domain': 'source_domain',
    }

    keep = {}
    for src_col, dst_col in base_cols.items():
        if src_col in df.columns:
            keep[dst_col] = df[src_col]

    result = pd.DataFrame(keep)

    # ── 1. Company → ticker ──
    result['ticker'] = df['company'].map(COMPANY_TICKER_MAP)
    tickered = result['ticker'].notna().sum()
    log(f"Company→ticker mapped: {tickered}/{len(df)}")

    # ── 2. Parse announcement date from YYYYMMDDHHMMSS ──
    result['announcement_date'] = pd.to_datetime(
        df['date'].astype(str), format='%Y%m%d%H%M%S', errors='coerce'
    )
    result['year'] = result['announcement_date'].dt.year
    result['quarter'] = result['announcement_date'].dt.quarter
    result['month'] = result['announcement_date'].dt.month
    result['announcement_quarter'] = result['announcement_date'].dt.to_period('Q').astype(str)

    # ── 3. Promised MW features ──
    result['promised_mw'] = pd.to_numeric(df['mw_capacity'], errors='coerce').fillna(0)
    result['has_mw'] = df['mw_capacity'].notna().astype(int)
    # Log-transform: log(1+x) to handle zeros
    result['mw_log'] = np.log1p(result['promised_mw'])

    # ── 4. Confidence numeric ──
    conf_map = {'high': 2, 'medium': 1, 'low': 0}
    result['confidence_num'] = df['confidence'].map(conf_map).fillna(1).astype(int)

    # ── 5. Tone features from v2_tone ──
    tone_df = df['v2_tone'].apply(parse_tone)
    tone_df.columns = ['tone_sentiment', 'tone_magnitude',
                        'tone_score1', 'tone_score2',
                        'tone_score3', 'tone_token_count']
    result = pd.concat([result, tone_df], axis=1)

    # ── 6. Location ──
    result['location'] = df.apply(
        lambda r: f"{r['location_city']}, {r['location_state']}"
        if pd.notna(r['location_city']) and pd.notna(r['location_state'])
        else (r['location_city'] if pd.notna(r['location_city'])
              else (r['location_state'] if pd.notna(r['location_state']) else np.nan)),
        axis=1
    )

    # ── 7. Target date features ──
    result['target_date'] = pd.to_datetime(
        df['target_completion_date'], errors='coerce'
    )
    result['days_to_target'] = (
        result['target_date'] - result['announcement_date']
    ).dt.days

    # ── 8. Organize final column order ──
    final_cols = [
        # Identifiers
        'company', 'ticker',
        # Dates
        'announcement_date', 'year', 'quarter', 'month', 'announcement_quarter',
        'target_date', 'days_to_target',
        # MW features
        'promised_mw', 'has_mw', 'mw_log',
        # Location
        'location', 'location_city', 'location_state',
        # Source quality
        'confidence', 'confidence_num',
        # Text & tone
        'extracted_text_snippet', 'url', 'source_domain',
        'tone_sentiment', 'tone_magnitude', 'tone_score1', 'tone_score2',
        'tone_score3', 'tone_token_count',
        # Label
        'promise_kept', 'label_source',
    ]
    # Only keep columns that actually exist
    available = [c for c in final_cols if c in result.columns]
    result = result[available]

    # ── Summary ──
    kept = int(result['promise_kept'].sum())
    failed = int((result['promise_kept'] == 0).sum())
    pending = int(result['promise_kept'].isna().sum())
    log(f"Rows: {len(result)}, Cols: {len(result.columns)}")
    log(f"Labels: {kept} kept, {failed} failed, {pending} pending "
         f"({kept/len(result)*100:.1f}% / {failed/len(result)*100:.1f}% / {pending/len(result)*100:.1f}%)")
    log(f"Tickers mapped: {result['ticker'].notna().sum()}/{len(result)}")
    log(f"Has MW: {result['has_mw'].sum()}/{len(result)}")
    log(f"Date range: {result['announcement_date'].min()} to {result['announcement_date'].max()}")

    if dry:
        log("DRY RUN — skipping output")
        return

    os.makedirs("data/processed", exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)
    log(f"Saved {len(result)} rows to {OUTPUT_PATH}")

    # DVC
    log("Running DVC add...")
    try:
        subprocess.run(['dvc', 'add', OUTPUT_PATH], check=True, capture_output=True, text=True)
        subprocess.run(['dvc', 'push', OUTPUT_PATH + '.dvc'], capture_output=True, text=True)
        log("DVC add + push complete")
    except Exception as e:
        log(f"DVC step skipped: {e}")

    log("Build ML dataset complete.")


def log(msg):
    print(f"[build-ml] {msg}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build minimum viable ML dataset from real buildout events"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Quick check (no output file)"
    )
    args = parser.parse_args()
    if args.dry_run:
        sys.argv.append("--dry-run")
    main()
