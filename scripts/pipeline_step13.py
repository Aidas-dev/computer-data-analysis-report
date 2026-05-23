#!/usr/bin/env python3
"""
pipeline_step13.py — Article text extraction for buildout candidates.
Extracted from notebooks/13-article-extraction.ipynb.

Phase 1 (no network): URL pre-filtering — classify each URL by priority
  priority=2  strong buildout signal (2+ keywords or 1 + company)
  priority=1  possible (1 keyword or company in V2Organizations)
  priority=0  weak (no signal — still fetch, lower priority)
  priority=-1 skip (exclusion keywords — lawsuit, layoff, SEC, etc.)

Phase 2: Parallel fetch with per-domain rate limiting.
  ThreadPoolExecutor(max_workers=10), Semaphore(MAX_PER_DOMAIN=3)
  trafilatura primary, newspaper3k fallback.
  Progress every 200 URLs with throughput rate.
"""
import os, sys, re, time, warnings, subprocess
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore

import pandas as pd

warnings.filterwarnings('ignore')

MARKER = "/tmp/done_pipeline_step13"
INPUT_PATH = "data/raw/buildout_candidates_gkg.csv"
OUTPUT_PATH = "data/raw/buildout_events_raw.csv"

HAS_TRAFILATURA = False
HAS_NEWSPAPER = False

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    pass

try:
    from newspaper import Article
    HAS_NEWSPAPER = True
except ImportError:
    pass

# ── URL-level pre-filtering keywords ──────────────────────────────────
URL_SIGNAL_KEYWORDS = [
    'data-center', 'datacenter', 'build', 'construction',
    'break-ground', 'groundbreaking', 'campus', 'expansion',
    'investment', 'megawatt', 'capacity', 'opens', 'opening',
    'announces', 'unveils', 'planned', 'facility', 'new-', 'launch'
]

URL_EXCLUSION_KEYWORDS = [
    'lawsuit', 'layoff', 'class-action', 'sec-', 'sec/',
    'fire', 'wildfire', 'flood', 'earthquake', 'hurricane',
    'disaster', 'pandemic'
]

# ── Parallel fetch configuration ──────────────────────────────────────
MAX_WORKERS = 10
MAX_PER_DOMAIN = 3
FETCH_TIMEOUT = 15

# ── Text-level extraction constants (EXACTLY as in original) ──────────
MW_PATTERNS = [
    r'(\d{1,5}(?:[.,]\d{1,2})?)\s*-?\s*MW',
    r'(\d{1,5}(?:[.,]\d{1,2})?)\s*megawatts?',
    r'(\d{1,5}(?:[.,]\d{1,2})?)\s*-?\s*megawatt',
    r'(\d{1,5}(?:[.,]\d{1,2})?)\s*mw',
    r'(\d{1,2})\s*(?:GW|gigawatts?)',
]

LOCATION_PATTERN = r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s*,\s*([A-Z]{2})'

BUILDOUT_KEYWORDS = [
    r'\bdata center\b', r'\bdatacenter\b',
    r'\bbuild\b', r'\bconstruction\b', r'\bbreak\s*ground\b',
    r'\bcampus\b', r'\bfacility\b', r'\bexpansion\b',
    r'\binvestment\b', r'\bcapex\b', r'\bcapital\s*expenditure\b',
    r'\bmegawatt\b', r'\bcapacity\b',
    r'\bannounce\b', r'\bplan\b', r'\bunveil\b',
    r'\bnew\s*(?:data|cloud|AI|server)\s*(?:center|campus|facility|region)\b',
]

EXCLUSION_KEYWORDS = [
    r'\blayoff\b', r'\bquit\b', r'\bresign\b',
    r'\blawsuit\b', r'\blitigation\b',
    r'\bclass\s*action\b', r'\bSEC\b',
    r'\bfire\b', r'\bwildfire\b', r'\bflood\b',
    r'\bearthquake\b', r'\bdisaster\b',
]

COMPANY_KEYWORDS = [
    'Microsoft', 'Microsoft Corp',
    'Google', 'Alphabet',
    'Amazon', 'AWS', 'Amazon Web Services',
    'Meta', 'Facebook',
    'NVIDIA', 'Nvidia',
    'Apple',
    'Oracle', 'Crusoe',
    'Equinix', 'Digital Realty',
    'American Tower', 'Prologis',
    'Simon Property', 'Public Storage',
    'Outfront', 'Sabra',
    'Hudson Pacific', 'Rexford',
    'First Industrial', 'SITC',
]


# ── Helper ────────────────────────────────────────────────────────────
def log(msg):
    print(f"[step13] {msg}", flush=True)


# ── Phase 1: URL priority classification (no network) ─────────────────
def classify_url_priority(url, v2_organizations=None):
    """
    Classify URL into priority without fetching.
    Returns: -1 (skip), 0 (weak), 1 (possible), 2 (strong)
    """
    if not url or not isinstance(url, str):
        return -1
    url_lower = url.lower()

    for kw in URL_EXCLUSION_KEYWORDS:
        if kw in url_lower:
            return -1

    signal_count = 0
    for kw in URL_SIGNAL_KEYWORDS:
        if kw in url_lower:
            signal_count += 1

    has_company = False
    if v2_organizations and isinstance(v2_organizations, str):
        orgs_clean = v2_organizations.strip()
        if orgs_clean and orgs_clean.lower() not in ('nan', 'none'):
            orgs_lower = orgs_clean.lower()
            for kw in COMPANY_KEYWORDS:
                if kw.lower() in orgs_lower:
                    has_company = True
                    break

    if signal_count >= 2 or (signal_count >= 1 and has_company):
        return 2
    if signal_count >= 1 or has_company:
        return 1
    return 0


# ── Extraction functions (EXACTLY as in original) ─────────────────────
def extract_article_text(url, timeout=15):
    method = None
    text = None
    if HAS_TRAFILATURA:
        try:
            downloaded = trafilatura.fetch_url(url, timeout=timeout)
            if downloaded:
                text = trafilatura.extract(downloaded, output_format='text',
                                           include_links=False, include_images=False,
                                           include_tables=False)
                if text and len(text.strip()) > 100:
                    method = 'trafilatura'
                    return text.strip(), method
        except Exception:
            pass
    if HAS_NEWSPAPER:
        try:
            article = Article(url, timeout=timeout)
            article.download()
            article.parse()
            if article.text and len(article.text.strip()) > 100:
                text = article.text.strip()
                method = 'newspaper3k'
                return text, method
        except Exception:
            pass
    return None, None


def extract_mw(text):
    if not text:
        return None
    text_lower = text.lower()
    found_values = []
    gw_match = re.search(r'(\d{1,2}(?:\.\d{1,2})?)\s*(?:GW|gigawatts?)', text_lower)
    if gw_match:
        val = float(gw_match.group(1).replace(',', '')) * 1000
        found_values.append(val)
    for pattern in MW_PATTERNS:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        for m in matches:
            try:
                val = float(m.replace(',', ''))
                if 1 <= val <= 50000:
                    found_values.append(val)
            except ValueError:
                continue
    if not found_values:
        return None
    return max(found_values)


def extract_location(text, v2_locations=None):
    city, state = None, None
    if v2_locations and isinstance(v2_locations, str) and v2_locations.strip():
        try:
            for loc_entry in v2_locations.split(';'):
                parts = loc_entry.strip().split('|')
                if len(parts) >= 5:
                    city = parts[4] if parts[4] and parts[4] != 'None' else None
                    state = parts[3] if parts[3] and parts[3] != 'None' else None
                    country = parts[2] if len(parts) > 2 else ''
                    if country.strip().upper() in ('US', 'UNITED STATES', 'USA', ''):
                        if city and state:
                            state_clean = state.split(',')[0].strip()
                            if len(state_clean) == 2:
                                return city, state_clean
        except Exception:
            pass
    if text:
        matches = re.findall(LOCATION_PATTERN, text)
        if matches:
            city, state = matches[-1]
            return city.strip(), state.strip()
    return None, None


def extract_company(v2_organizations=None, text=None):
    found = []
    if v2_organizations and isinstance(v2_organizations, str):
        orgs_lower = v2_organizations.lower()
        for kw in COMPANY_KEYWORDS:
            if kw.lower() in orgs_lower:
                found.append(kw)
    if not found and text:
        text_lower = text.lower()
        for kw in COMPANY_KEYWORDS:
            if kw.lower() in text_lower:
                found.append(kw)
    if not found:
        return None
    found.sort(key=len, reverse=True)
    return found[0]


def extract_target_completion_date(text):
    if not text:
        return None
    date_patterns = [
        r'(?:target|expected|planned|scheduled|to be (?:operational|complete|ready)|by)\s*(?:for\s*)?(?:completion|operational|opening|launch)?\s*:?\s*(\d{4})',
        r'(\d{4})\s*(?:target|expected|planned|scheduled)',
        r'(?:open|launch|complete|operational|ready)\s*(?:in|by)\s*(\d{4})',
        r'(?:Q[1-4]\s*\d{4})',
        r'(?:H[12]\s*\d{4})',
    ]
    text_lower = text.lower()
    for pattern in date_patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def classify_buildout(text, company, mw_capacity):
    if not text:
        return False, 'fetch_failed'
    text_lower = text.lower()
    for pattern in EXCLUSION_KEYWORDS:
        if re.search(pattern, text_lower):
            return False, 'excluded'
    buildout_score = 0
    for pattern in BUILDOUT_KEYWORDS:
        if re.search(pattern, text_lower):
            buildout_score += 1
    if buildout_score == 0:
        return False, 'no_signal'
    has_company = company is not None
    has_mw = mw_capacity is not None
    if has_company and has_mw and buildout_score >= 3:
        return True, 'high'
    if has_company and buildout_score >= 4:
        return True, 'high'
    if has_company and (has_mw or buildout_score >= 2):
        return True, 'medium'
    if has_company and buildout_score >= 1:
        return True, 'low'
    if has_mw and buildout_score >= 3:
        return True, 'low'
    return False, 'weak_signal'


def get_text_snippet(text, max_chars=200):
    if not text:
        return ''
    return text[:max_chars].replace('\n', ' ').strip()


# ── Phase 2: single-URL processing (runs in thread pool) ──────────────
def process_url(row, url_col):
    url = row[url_col]
    domain = row.get('SourceCommonName', row.get('source_domain', ''))
    gkg_date = str(row.get('DATE', row.get('date', '')))
    v2_orgs = str(row.get('V2Organizations', ''))
    v2_locs = str(row.get('V2Locations', ''))
    v2_tone = row.get('V2Tone', None)

    text, method = extract_article_text(url, timeout=FETCH_TIMEOUT)
    if text is None:
        text = ''

    company = extract_company(v2_organizations=v2_orgs, text=text)
    mw_capacity = extract_mw(text)
    city, state = extract_location(text, v2_locations=v2_locs)
    target_date = extract_target_completion_date(text)
    is_buildout, confidence = classify_buildout(text, company, mw_capacity)

    return {
        'url': url,
        'source_domain': domain,
        'date': gkg_date,
        'company': company,
        'location_city': city,
        'location_state': state,
        'mw_capacity': mw_capacity,
        'target_completion_date': target_date,
        'is_buildout': is_buildout,
        'confidence': confidence,
        'extracted_text_snippet': get_text_snippet(text),
        'v2_organizations': v2_orgs,
        'v2_locations': v2_locs,
        'v2_tone': v2_tone,
    }


# ── Main ──────────────────────────────────────────────────────────────
def main():
    dry = "--dry-run" in sys.argv
    log("Step 13: Article Text Extraction")

    if not HAS_TRAFILATURA and not HAS_NEWSPAPER:
        if dry:
            log("DRY RUN — skipping lib check")
            Path(MARKER).write_text("OK\ndry-run")
            return
        log("ERROR: No article extraction library (trafilatura or newspaper3k)")
        sys.exit(1)
    log(f"Libs: trafilatura={HAS_TRAFILATURA}, newspaper3k={HAS_NEWSPAPER}")

    if not os.path.exists(INPUT_PATH):
        if dry:
            log(f"DRY RUN — input not found ({INPUT_PATH}), skipping")
            Path(MARKER).write_text("OK\ndry-run")
            return
        log(f"ERROR: Input not found: {INPUT_PATH}")
        sys.exit(1)

    df = pd.read_csv(INPUT_PATH)
    log(f"Loaded {len(df)} candidates from {INPUT_PATH}")

    url_col = None
    for col in ['DocumentIdentifier', 'url']:
        if col in df.columns:
            url_col = col
            break
    if url_col is None:
        log("ERROR: No URL column found")
        sys.exit(1)

    n_before = len(df)
    df = df.drop_duplicates(subset=[url_col])
    log(f"Removed {n_before - len(df)} duplicate URLs, {len(df)} unique")

    OUTPUT_COLS = [
        'url', 'source_domain', 'date', 'company', 'location_city',
        'location_state', 'mw_capacity', 'target_completion_date',
        'is_buildout', 'confidence', 'extracted_text_snippet',
        'v2_organizations', 'v2_locations', 'v2_tone'
    ]

    total_before_filter = len(df)

    # ── Phase 1: URL pre-filtering (no network) ──────────────────────
    log("Phase 1: URL priority classification...")
    df['priority'] = df.apply(
        lambda row: classify_url_priority(
            row[url_col],
            str(row.get('V2Organizations', ''))
        ),
        axis=1
    )

    n_skipped = int((df['priority'] == -1).sum())
    n_weak = int((df['priority'] == 0).sum())
    n_possible = int((df['priority'] == 1).sum())
    n_strong = int((df['priority'] == 2).sum())

    log(f"Priority breakdown: strong={n_strong}, possible={n_possible}, weak={n_weak}, skipped={n_skipped}")

    # Filter out skipped, sort by priority descending (highest first)
    df_work = df[df['priority'] >= 0].sort_values('priority', ascending=False).reset_index(drop=True)
    total = len(df_work)

    if dry:
        estimated = total * 0.5  # rough estimate: 0.5s per URL with 10 workers
        log(f"DRY RUN — would process {total} URLs ({total_before_filter} before filter, {n_skipped} skipped)")
        log(f"  Priority: {n_strong} strong, {n_possible} possible, {n_weak} weak")
        log(f"  Parallel: {MAX_WORKERS} workers, {MAX_PER_DOMAIN} per domain")
        log(f"  Estimated: ~{estimated:.0f}s ({estimated/60:.1f}min)")
        Path(MARKER).write_text("OK\ndry-run")
        return

    # ── Phase 2: Parallel fetch ──────────────────────────────────────
    log(f"Phase 2: Parallel fetch ({MAX_WORKERS} workers, {MAX_PER_DOMAIN}/domain cap)...")
    start_ts = time.time()

    results = []
    errors = []
    processed = 0
    progress_lock = threading.Lock()

    domain_sems = {}
    domain_lock = threading.Lock()

    def get_domain_sem(domain):
        with domain_lock:
            if domain not in domain_sems:
                domain_sems[domain] = Semaphore(MAX_PER_DOMAIN)
            return domain_sems[domain]

    def process_with_rate_limit(row):
        domain = row.get('SourceCommonName', row.get('source_domain', ''))
        with get_domain_sem(domain):
            return process_url(row, url_col)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_with_rate_limit, row): idx
            for idx, (_, row) in enumerate(df_work.iterrows())
        }

        for future in as_completed(futures):
            with progress_lock:
                processed += 1
                if processed % 200 == 0 or processed == total:
                    elapsed = time.time() - start_ts
                    rate = processed / elapsed if elapsed > 0 else 0
                    log(f"[{processed}/{total}] {rate:.1f} URLs/s, {elapsed:.0f}s elapsed")

            try:
                result = future.result()
                results.append(result)
                if not result['extracted_text_snippet']:
                    errors.append({'url': result['url'], 'reason': 'fetch_failed'})
            except Exception as e:
                idx = futures[future]
                url = df_work.at[idx, url_col] if idx < len(df_work) else 'unknown'
                errors.append({'url': url, 'reason': str(e)})

    elapsed = time.time() - start_ts
    rate = total / elapsed if elapsed > 0 else 0
    log(f"Fetch complete: {total} URLs in {elapsed:.0f}s ({rate:.1f} URLs/s)")

    # ── Build output ──────────────────────────────────────────────────
    df_results = pd.DataFrame(results, columns=OUTPUT_COLS)
    df_errors = pd.DataFrame(errors) if errors else pd.DataFrame()

    fetched = df_results['extracted_text_snippet'].str.len().gt(0).sum()
    buildout_count = df_results['is_buildout'].sum()
    log(f"Total: {len(df_results)}, Fetched: {fetched}, Buildouts: {buildout_count}, Errors: {len(errors)}")

    os.makedirs("data/raw", exist_ok=True)
    df_results.to_csv(OUTPUT_PATH, index=False)
    log(f"Saved {len(df_results)} rows to {OUTPUT_PATH}")

    if not df_errors.empty:
        errors_path = "data/raw/buildout_fetch_errors.csv"
        df_errors.to_csv(errors_path, index=False)
        log(f"Saved {len(df_errors)} errors to {errors_path}")

    # ── DVC ───────────────────────────────────────────────────────────
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
    log("Step 13 complete.")


if __name__ == "__main__":
    main()
