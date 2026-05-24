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

# ── Keyword lists ──
# Sorted by length (longest first) to avoid false positives from short substrings.
# Case-insensitive matching on extracted_text_snippet (and title if available).

KEPT_KEYWORDS = sorted([
    # Construction completion
    'achieved substantial completion', 'substantially complete',
    'completed construction', 'construction complete',
    'reached completion', 'project completed', 'phase completed',
    'first phase operational', 'initial phase live',
    # Launch / go-live (longer phrases first)
    'formally launched', 'declared open', 'now serving customers',
    'started operations', 'commenced operations',
    'opening ceremony', 'cut the ribbon',
    'fully operational', 'became operational',
    'began operations', 'began offering',
    'started serving', 'began operations',
    'goes live', 'went live', 'is now live', 'has gone live',
    'came online', 'went online', 'brought online',
    'has launched', 'has opened',
    'now open', 'now live',
    'in production', 'live and running',
    'commissioned', 'inaugurated', 'opened',
    'delivered',
], key=len, reverse=True)

FAILED_KEYWORDS = sorted([
    # Full cancellation (longest first)
    'indefinitely postponed', 'postponed indefinitely',
    'delayed indefinitely', 'paused indefinitely',
    'deferred indefinitely',
    'facing cancellation', 'facing delays',
    'significantly delayed', 'hit with delays',
    'no longer planned', 'not moving forward',
    'will not build', 'pulled the plug',
    'construction halted', 'construction suspended',
    'project canceled', 'project cancelled',
    'stopped work', 'work stopped',
    'on the back burner', 'placed on hold',
    'put on hold', 'under review',
    'scaling back', 'scaled back',
    # Core failure terms
    'canceled', 'cancelled',
    'scrapped', 'shelved', 'abandoned',
    'halted', 'suspended', 'mothballed',
], key=len, reverse=True)


def log(msg):
    print(f"[step14] {msg}", flush=True)


def classify_promise(text_snippet, title_snippet=None):
    """Return (promise_kept: int|None, label_source: str, matched_on: str).

    Matches keywords on text_snippet. If title_snippet provided, also checks
    that. Returns which source matched: 'text', 'title', or ''.
    """
    matched_on = ''

    def _check(text):
        """Check a single text string, return (label, source_tag) or (None, '')."""
        if pd.isna(text) or not isinstance(text, str) or not text.strip():
            return None, ''
        lower = text.lower()
        for kw in KEPT_KEYWORDS:
            if kw in lower:
                return 1, 'text_keywords'
        for kw in FAILED_KEYWORDS:
            if kw in lower:
                return 0, 'text_keywords'
        return None, ''

    # Check text snippet first
    label, src = _check(text_snippet)
    if label is not None:
        return label, src, 'text'

    # Check title if available
    if title_snippet is not None:
        label, src = _check(title_snippet)
        if label is not None:
            return label, src, 'title'

    return None, 'text_keywords', ''


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

    has_title = 'title' in df.columns

    n_kept = 0
    n_failed = 0
    n_pending = 0
    n_title_matched = 0

    kept_list = []
    failed_list = []
    pending_list = []
    text_matched_list = []
    title_matched_list = []

    for idx, row in df.iterrows():
        snippet = row.get('extracted_text_snippet', '')
        title_snippet = row.get('title') if has_title else None
        promise_kept, label_source, matched_on = classify_promise(snippet, title_snippet)
        df.at[idx, 'promise_kept'] = promise_kept
        df.at[idx, 'label_source'] = label_source
        df.at[idx, 'text_matched'] = 1 if matched_on == 'text' else 0
        df.at[idx, 'title_matched'] = 1 if matched_on == 'title' else 0

        text_matched_list.append(1 if matched_on == 'text' else 0)
        title_matched_list.append(1 if matched_on == 'title' else 0)

        if promise_kept == 1:
            n_kept += 1
            kept_list.append(row.get('company', ''))
        elif promise_kept == 0:
            n_failed += 1
            failed_list.append(row.get('company', ''))
        else:
            n_pending += 1
            pending_list.append(row.get('company', ''))

        if matched_on == 'title':
            n_title_matched += 1

    log(f"Classified: {n_kept} kept, {n_failed} failed, {n_pending} pending"
         f" (title-matched: {n_title_matched})")

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
    output_cols = existing_base + ['promise_kept', 'label_source', 'text_matched', 'title_matched']
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
