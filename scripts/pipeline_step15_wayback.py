#!/usr/bin/env python3
"""
pipeline_step15_wayback.py — Fetch full article text for buildout events
via Wayback Machine CDX archive lookups + trafilatura extraction.

Input:  data/processed/buildout_promises_real.csv  (5,295 rows)
Output: data/processed/buildout_promises_real_enriched_v2.csv
  - All original columns preserved
  - Added article_text_full column

Two-phase pipeline:
  1. Parallel CDX API queries to discover earliest 200-snapshot timestamps
  2. Parallel fetch+extract batches (500 at a time, 5 workers)

Usage:
  python scripts/pipeline_step15_wayback.py
  python scripts/pipeline_step15_wayback.py --max-urls 50   # quick test
  python scripts/pipeline_step15_wayback.py --dvc-push       # also dvc add + push
  python scripts/pipeline_step15_wayback.py --dry-run        # syntax/import check
"""
import argparse
import os
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from tqdm import tqdm

warnings.filterwarnings('ignore')

try:
    import trafilatura
except ImportError:
    trafilatura = None

# ── Defaults ──
DEFAULT_INPUT = "data/processed/buildout_promises_real.csv"
DEFAULT_OUTPUT = "data/processed/buildout_promises_real_enriched_v2.csv"
DEFAULT_CKPT_DIR = "/tmp"
CDX_WORKERS = 10
FETCH_WORKERS = 5
CHECKPOINT_EVERY = 500
FETCH_BATCH_SIZE = 500

CDX_URL_TEMPLATE = (
    "http://web.archive.org/cdx/search/cdx"
    "?url={url}&limit=1&output=json&fl=timestamp,statuscode"
)
FETCH_URL_TEMPLATE = "https://web.archive.org/web/{timestamp}/{url}"

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BuildoutResearch/1.0)"}
CDX_TIMEOUT = 30
FETCH_TIMEOUT = 60


def log(msg):
    print(f"[step15] {msg}", flush=True)


def query_cdx(url):
    """Query Wayback CDX API for earliest 200-status snapshot timestamp.

    Returns (url, timestamp_or_None).
    """
    cdx_url = CDX_URL_TEMPLATE.format(url=url)
    try:
        resp = requests.get(cdx_url, headers=REQUEST_HEADERS, timeout=CDX_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # data[0] is header row; subsequent rows are [timestamp, statuscode]
        for row in data[1:]:
            if len(row) >= 2 and row[1] == "200":
                return url, row[0]
        return url, None
    except Exception as exc:
        log(f"CDX query failed for {url[:80]}: {exc}")
        return url, None


def fetch_and_extract(url, timestamp):
    """Fetch archived page from Wayback and extract text with trafilatura.

    Returns extracted text string (empty on failure).
    """
    if not timestamp:
        return ""
    fetch_url = FETCH_URL_TEMPLATE.format(timestamp=timestamp, url=url)
    try:
        resp = requests.get(fetch_url, headers=REQUEST_HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        if trafilatura is not None:
            text = trafilatura.extract(resp.text)
            if text and len(text) >= 100:
                return text
        return ""
    except Exception as exc:
        log(f"Fetch failed for {url[:80]} @ {timestamp}: {exc}")
        return ""


def save_checkpoint(df, idx, ckpt_dir, label=""):
    """Save intermediate checkpoint CSV."""
    ckpt_path = os.path.join(ckpt_dir, f"wayback_ckpt_{idx}.csv")
    df.to_csv(ckpt_path, index=False)
    log(f"Checkpoint saved: {ckpt_path}  ({label})")


def run_dvc_push(output_path):
    """Run DVC add + push on output file."""
    log("Running DVC add...")
    try:
        import subprocess
        result = subprocess.run(
            ["dvc", "add", output_path],
            capture_output=True, text=True, check=True,
        )
        log(result.stdout.strip())
        result_push = subprocess.run(
            ["dvc", "push", output_path + ".dvc"],
            capture_output=True, text=True,
        )
        if result_push.returncode == 0:
            log("DVC push OK")
        else:
            log(f"DVC push issue: {result_push.stderr[:200]}")
    except Exception as e:
        log(f"DVC step skipped: {e}")


def build_output_path(args_output):
    """Resolve output path (support relative/absolute)."""
    path = args_output if args_output else DEFAULT_OUTPUT
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Step 15: Wayback Machine article text enrichment"
    )
    parser.add_argument(
        "--input-path", default=DEFAULT_INPUT,
        help=f"Input CSV path (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output-path", default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--checkpoint-dir", default=DEFAULT_CKPT_DIR,
        help=f"Checkpoint directory (default: {DEFAULT_CKPT_DIR})",
    )
    parser.add_argument(
        "--cdx-workers", type=int, default=CDX_WORKERS,
        help=f"Parallel CDX query workers (default: {CDX_WORKERS})",
    )
    parser.add_argument(
        "--fetch-workers", type=int, default=FETCH_WORKERS,
        help=f"Parallel fetch+extract workers (default: {FETCH_WORKERS})",
    )
    parser.add_argument(
        "--max-urls", type=int, default=0,
        help="Limit to first N URLs for testing (default: all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Quick syntax/import check (no processing)",
    )
    parser.add_argument(
        "--dvc-push", action="store_true",
        help="Run DVC add + push after output",
    )
    args = parser.parse_args()

    if args.dry_run:
        log("DRY RUN — syntax/import check passed")
        return

    # ── Load CSV ──
    if not os.path.exists(args.input_path):
        log(f"ERROR: Input not found: {args.input_path}")
        sys.exit(1)

    df = pd.read_csv(args.input_path)
    log(f"Loaded {len(df)} rows from {args.input_path}")

    if "url" not in df.columns:
        log("ERROR: 'url' column not found in input")
        sys.exit(1)

    if args.max_urls and args.max_urls < len(df):
        df = df.head(args.max_urls).copy()
        log(f"Limited to {len(df)} URLs for testing")

    df["article_text_full"] = ""

    total = len(df)
    urls = df["url"].tolist()

    # ── Stats accumulators ──
    stats = {
        "archived": 0,
        "failed": 0,
        "text_lengths": [],
        "domain_counts": {},
    }

    # ════════════════════════════════════════════════════════════
    # PHASE 1: CDX timestamp discovery (parallel)
    # ════════════════════════════════════════════════════════════
    log(f"Phase 1: Discovering Wayback timestamps for {total} URLs "
        f"({args.cdx_workers} workers)...")
    timestamp_map = {}

    start_t = time.time()
    with ThreadPoolExecutor(max_workers=args.cdx_workers) as executor:
        fut_map = {executor.submit(query_cdx, url): url for url in urls}
        for fut in tqdm(as_completed(fut_map), total=total, desc="CDX queries",
                        unit="url"):
            url, ts = fut.result()
            timestamp_map[url] = ts

    phase1_elapsed = time.time() - start_t
    found = sum(1 for ts in timestamp_map.values() if ts is not None)
    log(f"Phase 1 done: {found}/{total} URLs have snapshots "
        f"({phase1_elapsed:.1f}s)")

    # ── Pre-build list of (idx, url, timestamp) for phase 2 ──
    fetch_queue = []
    for idx, row in df.iterrows():
        url = row["url"]
        ts = timestamp_map.get(url)
        if ts:
            fetch_queue.append((idx, url, ts))

    log(f"Queueing {len(fetch_queue)} fetch+extract tasks "
        f"({total - len(fetch_queue)} have no snapshot)")

    # ════════════════════════════════════════════════════════════
    # PHASE 2: Fetch + extract (parallel, batched)
    # ════════════════════════════════════════════════════════════
    log(f"Phase 2: Fetching archived pages ({args.fetch_workers} workers, "
        f"batch size {FETCH_BATCH_SIZE})...")

    done_count = 0
    fetch_start = time.time()

    # Process in batches to checkpoint regularly
    for batch_start in range(0, len(fetch_queue), FETCH_BATCH_SIZE):
        batch = fetch_queue[batch_start:batch_start + FETCH_BATCH_SIZE]
        batch_results = {}

        with ThreadPoolExecutor(max_workers=args.fetch_workers) as executor:
            fut_map = {}
            for idx, url, ts in batch:
                fut = executor.submit(fetch_and_extract, url, ts)
                fut_map[fut] = (idx, url, ts)

            for fut in tqdm(as_completed(fut_map), total=len(batch),
                            desc=f"Batch {batch_start // FETCH_BATCH_SIZE + 1}",
                            unit="page"):
                idx, url, ts = fut_map[fut]
                try:
                    text = fut.result()
                except Exception as exc:
                    log(f"Unexpected error for {url[:80]}: {exc}")
                    text = ""
                batch_results[idx] = text

                # Stats
                if text and len(text) >= 100:
                    stats["archived"] += 1
                    stats["text_lengths"].append(len(text))
                    domain = url.split("/")[2] if "//" in url else "unknown"
                    stats["domain_counts"][domain] = (
                        stats["domain_counts"].get(domain, 0) + 1
                    )
                else:
                    stats["failed"] += 1

                done_count += 1

        # Write batch results into dataframe
        for idx, text in batch_results.items():
            df.at[idx, "article_text_full"] = text

        # Checkpoint after each batch
        current_checkpoint = batch_start + len(batch)
        save_checkpoint(
            df, current_checkpoint, args.checkpoint_dir,
            f"{done_count}/{total} processed"
        )

    phase2_elapsed = time.time() - fetch_start
    total_elapsed = time.time() - start_t

    # ── Summary ──
    log("=" * 60)
    log("FINAL SUMMARY")
    log(f"  Total URLs:       {total}")
    log(f"  Archived:         {stats['archived']}")
    log(f"  Failed/empty:     {stats['failed']}")
    if stats["text_lengths"]:
        log(f"  Mean text length: {sum(stats['text_lengths']) // len(stats['text_lengths'])} chars")
        log(f"  Median text len:  {sorted(stats['text_lengths'])[len(stats['text_lengths']) // 2]}")
    log(f"  Phase 1 (CDX):    {phase1_elapsed:.1f}s")
    log(f"  Phase 2 (fetch):  {phase2_elapsed:.1f}s")
    log(f"  Total time:       {total_elapsed:.1f}s")
    top_domains = sorted(stats["domain_counts"].items(),
                         key=lambda x: -x[1])[:10]
    if top_domains:
        log("  Top domains:")
        for dom, cnt in top_domains:
            log(f"    {dom}: {cnt}")
    log("=" * 60)

    # ── Final save ──
    output_path = build_output_path(args.output_path)
    df.to_csv(output_path, index=False)
    log(f"Saved {len(df)} rows to {output_path}")

    # Optional DVC
    if args.dvc_push:
        run_dvc_push(output_path)

    log("Step 15 complete.")


if __name__ == "__main__":
    main()
