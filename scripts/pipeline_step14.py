#!/usr/bin/env python3
"""
pipeline_step14.py — Text keyword classification for buildout promises.
Replaces gridstatus ISO queue cross-referencing with deterministic
text-based keyword matching on extracted_text_snippet.

Input:  data/raw/buildout_events_raw.csv  (from step13)
Output: data/processed/buildout_promises_real.csv
  - All original columns preserved
  - promise_kept: 1 (kept), 0 (failed), NaN (pending/unknown)
  - label_source: "text_keywords"
"""
import argparse
import os
import sys
import warnings
import subprocess
from pathlib import Path

import pandas as pd

warnings.filterwarnings('ignore')

MARKER = "/tmp/done_pipeline_step14"
INPUT_PATH = "data/raw/buildout_events_raw.csv"
OUTPUT_PATH = "data/processed/buildout_promises_real.csv"

# ── Keyword lists (case-insensitive, checked on extracted_text_snippet) ──

KEPT_KEYWORDS = [
    'opened', 'began operations', 'goes live', 'went live', 'is now live',
    'commissioned', 'cut the ribbon', 'inaugurated', 'now open',
    'opening ceremony', 'commenced operations',
    'fully operational', 'became operational', 'has launched', 'has opened',
    'completed construction', 'construction complete',
]

FAILED_KEYWORDS = [
    'canceled', 'cancelled', 'scrapped', 'shelved', 'abandoned',
    'delayed indefinitely', 'halted', 'suspended', 'put on hold',
    'no longer planned', 'will not build', 'pulled the plug',
]


def log(msg):
    print(f"[step14] {msg}", flush=True)


def classify_promise(text_snippet):
    """Return (promise_kept: int|None, label_source: str)."""
    if pd.isna(text_snippet) or not isinstance(text_snippet, str) or not text_snippet.strip():
        return None, 'text_keywords'

    lower = text_snippet.lower()

    # Priority 1: kept keywords (first match wins)
    for kw in KEPT_KEYWORDS:
        if kw in lower:
            return 1, 'text_keywords'

    # Priority 2: failed keywords
    for kw in FAILED_KEYWORDS:
        if kw in lower:
            return 0, 'text_keywords'

    # Everything else: pending/unknown
    return None, 'text_keywords'


def main():
    dry = "--dry-run" in sys.argv
    log("Step 14: Text Keyword Classification")

    if not os.path.exists(INPUT_PATH):
        if dry:
            log(f"DRY RUN — input not found ({INPUT_PATH}), skipping")
            Path(MARKER).write_text("OK\ndry-run")
            return
        log(f"ERROR: Input not found: {INPUT_PATH}")
        sys.exit(1)

    df = pd.read_csv(INPUT_PATH)
    log(f"Loaded {len(df)} events from {INPUT_PATH}")

    # Filter to buildout events only
    if 'is_buildout' in df.columns:
        n_total = len(df)
        df = df[df['is_buildout']].copy()
        log(f"Filtered to {len(df)} buildout events (from {n_total})")
    else:
        log("WARNING: 'is_buildout' column not found, using all events")

    if len(df) == 0:
        log("WARNING: Empty dataframe after filtering")

    # Warn if extracted_text_snippet is missing
    if 'extracted_text_snippet' not in df.columns:
        log("WARNING: 'extracted_text_snippet' column missing, all will be pending")
        df['extracted_text_snippet'] = ''

    n_kept = 0
    n_failed = 0
    n_pending = 0

    kept_list = []
    failed_list = []
    pending_list = []

    for idx, row in df.iterrows():
        snippet = row.get('extracted_text_snippet', '')
        promise_kept, label_source = classify_promise(snippet)
        df.at[idx, 'promise_kept'] = promise_kept
        df.at[idx, 'label_source'] = label_source

        if promise_kept == 1:
            n_kept += 1
            kept_list.append(row.get('company', ''))
        elif promise_kept == 0:
            n_failed += 1
            failed_list.append(row.get('company', ''))
        else:
            n_pending += 1
            pending_list.append(row.get('company', ''))

    log(f"Classified: {n_kept} kept, {n_failed} failed, {n_pending} pending")

    # Sample counts per company
    def top_companies(company_list, label):
        counts = pd.Series([c for c in company_list if pd.notna(c) and c]).value_counts()
        top = counts.head(8)
        top_str = ", ".join(f"{k}={v}" for k, v in top.items())
        log(f"  Top companies ({label}): {top_str}")

    top_companies(kept_list, "kept")
    top_companies(failed_list, "failed")
    top_companies(pending_list, "pending")

    if dry:
        log("DRY RUN — skipping output")
        Path(MARKER).write_text("OK\ndry-run")
        return

    # Ensure promise_kept is proper int/NaN
    df['promise_kept'] = pd.to_numeric(df['promise_kept'], errors='coerce')

    # Build output columns: original + promise_kept + label_source
    base_cols = [
        'url', 'source_domain', 'date', 'company', 'location_city',
        'location_state', 'mw_capacity', 'target_completion_date',
        'is_buildout', 'confidence', 'extracted_text_snippet',
        'v2_organizations', 'v2_locations', 'v2_tone',
    ]
    existing_base = [c for c in base_cols if c in df.columns]
    output_cols = existing_base + ['promise_kept', 'label_source']
    df_output = df[output_cols].copy()

    os.makedirs("data/processed", exist_ok=True)
    df_output.to_csv(OUTPUT_PATH, index=False)
    log(f"Saved {len(df_output)} rows to {OUTPUT_PATH}")

    # DVC
    log("Running DVC add...")
    try:
        result = subprocess.run(
            ['dvc', 'add', OUTPUT_PATH],
            capture_output=True, text=True, check=True
        )
        log(result.stdout.strip())
        result_push = subprocess.run(
            ['dvc', 'push', OUTPUT_PATH + '.dvc'],
            capture_output=True, text=True
        )
        if result_push.returncode == 0:
            log("DVC push OK")
        else:
            log(f"DVC push issue: {result_push.stderr[:200]}")
    except Exception as e:
        log(f"DVC step skipped: {e}")

    Path(MARKER).write_text("OK\n")
    log("Step 14 complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Step 14: Text keyword classification for buildout promises"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Quick syntax/import check (no output file)"
    )
    args = parser.parse_args()
    if args.dry_run:
        sys.argv.append("--dry-run")
    main()
