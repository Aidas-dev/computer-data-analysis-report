#!/usr/bin/env python3
"""
fetch_fractracker_sources.py — Fetch and extract text from FracTracker
source URLs using trafilatura with newspaper3k fallback.

Input:  data/raw/fractracker_datacenters.csv  (1,520 rows)
Output: data/raw/fractracker_sources.parquet
  - All original columns preserved
  - Added source_text column with extracted article content

Usage:
  python scripts/fetch_fractracker_sources.py
  python scripts/fetch_fractracker_sources.py --max-urls 50   # quick test
  python scripts/fetch_fractracker_sources.py --workers 10    # more parallelism
  python scripts/fetch_fractracker_sources.py --dry-run       # syntax/import check
"""
import argparse
import os
import sys
import subprocess
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

warnings.filterwarnings("ignore")

# ── Bootstrap dependencies (install on demand) ──
REQUIRED_PACKAGES = ["trafilatura", "newspaper3k", "pandas", "pyarrow", "tqdm"]


def _bootstrap_deps():
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    if missing:
        print(
            f"[bootstrap] Installing: {', '.join(missing)}",
            flush=True,
        )
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q"] + missing
        )
        print("[bootstrap] Done.", flush=True)


_bootstrap_deps()

# ── Imports (safe after bootstrap) ──
import pandas as pd
import trafilatura
from tqdm import tqdm

# ── Defaults ──
DEFAULT_INPUT = "data/raw/fractracker_datacenters.csv"
DEFAULT_OUTPUT = "data/raw/fractracker_sources.parquet"
FETCH_TIMEOUT = 15
DEFAULT_WORKERS = 5


def log(msg):
    print(f"[fetch_sources] {msg}", flush=True)


def extract_first_url(field_value):
    """Extract first URL from *info_source_1* field.

    - Returns ``None`` for empty / non-http values
    - Splits on ``;`` to handle multi-URL fields
    - Returns the first (clean) substring
    """
    if not field_value or not isinstance(field_value, str):
        return None
    val = field_value.strip()
    if not val.lower().startswith("http"):
        return None
    # Split on semicolons — some fields contain multiple URLs
    first = val.split(";")[0].strip()
    return first


def fetch_and_extract(url):
    """Fetch *url* and extract clean article text.

    **Primary:** ``trafilatura.fetch_url`` → ``trafilatura.extract``
    **Fallback:** ``newspaper3k`` ``Article``

    Returns ``(url, text, ok)`` where *ok* is ``True`` when extracted
    text is ≥ 50 non-whitespace characters.
    """
    # ── Primary: trafilatura ──
    try:
        downloaded = trafilatura.fetch_url(url, timeout=FETCH_TIMEOUT)
        if downloaded:
            text = trafilatura.extract(downloaded)
            if text and len(text.strip()) >= 50:
                return url, text.strip(), True
    except Exception:
        pass

    # ── Fallback: newspaper3k ──
    try:
        from newspaper import Article

        article = Article(url)
        article.config.request_timeout = FETCH_TIMEOUT
        article.download()
        article.parse()
        text = article.text
        if text and len(text.strip()) >= 50:
            return url, text.strip(), True
    except Exception:
        pass

    return url, "", False


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and extract text from FracTracker source URLs"
    )
    parser.add_argument(
        "--input-path",
        default=DEFAULT_INPUT,
        help=f"Input CSV path (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output-path",
        default=DEFAULT_OUTPUT,
        help=f"Output Parquet path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--max-urls",
        type=int,
        default=0,
        help="Limit to first N URLs for testing (default: all)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Parallel fetch workers (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Quick syntax/import check (no processing)",
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

    COL = "info_source_1"
    if COL not in df.columns:
        log(f"ERROR: '{COL}' column not found in input")
        sys.exit(1)

    # ── Extract first URL from each row ──
    df["_extracted_url"] = df[COL].apply(extract_first_url)
    mask = df["_extracted_url"].notna() & (df["_extracted_url"] != "")
    df_urls = df[mask].copy()
    log(
        f"Rows with extractable URLs: {len(df_urls)} "
        f"(out of {len(df)})"
    )

    if args.max_urls and args.max_urls < len(df_urls):
        df_urls = df_urls.head(args.max_urls).copy()
        log(f"Limited to {len(df_urls)} URLs for testing")

    # ── Initialise output column (empty for all rows) ──
    df["source_text"] = ""

    urls = df_urls["_extracted_url"].tolist()
    total = len(urls)

    if total == 0:
        log("No URLs to fetch — saving empty result.")
        os.makedirs(os.path.dirname(args.output_path) or ".", exist_ok=True)
        df = df.drop(columns=["_extracted_url"])
        df.to_parquet(args.output_path, index=False)
        log(f"Saved {len(df)} rows to {args.output_path}")
        return

    # ── Parallel fetch ──
    log(f"Fetching {total} URLs ({args.workers} workers, "
        f"timeout={FETCH_TIMEOUT}s)...")

    stats = {"success": 0, "error": 0, "domains": {}}
    results = {}

    start_t = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        fut_map = {
            executor.submit(fetch_and_extract, url): url
            for url in urls
        }
        for fut in tqdm(
            as_completed(fut_map), total=total, desc="Fetching", unit="url"
        ):
            url, text, ok = fut.result()
            results[url] = text
            if ok:
                stats["success"] += 1
                domain = urlparse(url).netloc
                stats["domains"][domain] = (
                    stats["domains"].get(domain, 0) + 1
                )
            else:
                stats["error"] += 1

    elapsed = time.time() - start_t

    # ── Write results back into the main dataframe ──
    for idx, row in df.iterrows():
        url = row.get("_extracted_url")
        if url and url in results:
            df.at[idx, "source_text"] = results[url]

    df = df.drop(columns=["_extracted_url"])

    # ── Save Parquet ──
    os.makedirs(os.path.dirname(args.output_path) or ".", exist_ok=True)
    df.to_parquet(args.output_path, index=False)
    log(f"Saved {len(df)} rows to {args.output_path}")

    # ── Summary ──
    log("=" * 60)
    log("FETCH SUMMARY")
    log(f"  Total rows:       {len(df)}")
    log(f"  URLs attempted:   {total}")
    log(f"  Success:          {stats['success']}")
    log(f"  Failed/empty:     {stats['error']}")
    log(f"  Time:             {elapsed:.1f}s")
    if total > 0:
        log(f"  Avg time/url:     {elapsed / total:.2f}s")
    top_domains = sorted(
        stats["domains"].items(), key=lambda x: -x[1]
    )[:10]
    if top_domains:
        log("  Top domains:")
        for dom, cnt in top_domains:
            log(f"    {dom}: {cnt}")
    log("=" * 60)
    log("Done.")


if __name__ == "__main__":
    main()
