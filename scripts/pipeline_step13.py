#!/usr/bin/env python3
"""
pipeline_step13.py — Article text extraction for buildout candidates.
Extracted from notebooks/13-article-extraction.ipynb.
Fetches article text via trafilatura/newspaper3k, extracts structured data.
"""
import os, sys, re, time, warnings, subprocess
from pathlib import Path

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


def log(msg):
    print(f"[step13] {msg}", flush=True)


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

    REQUEST_DELAY = 1.0
    total = len(df)

    if dry:
        log(f"DRY RUN — would process {total} URLs (1s delay each = ~{total//60}min)")
        Path(MARKER).write_text("OK\ndry-run")
        return

    results = []
    errors = []

    for idx, row in df.iterrows():
        url = row[url_col]
        domain = row.get('SourceCommonName', row.get('source_domain', ''))
        gkg_date = str(row.get('DATE', row.get('date', '')))
        v2_orgs = str(row.get('V2Organizations', ''))
        v2_locs = str(row.get('V2Locations', ''))
        v2_tone = row.get('V2Tone', None)

        if (idx + 1) % 10 == 0 or idx == 0:
            log(f"[{idx+1}/{total}] {url[:80]}...")

        if not url or not isinstance(url, str) or not url.startswith('http'):
            errors.append({'url': url, 'reason': 'invalid_url'})
            continue

        text, method = extract_article_text(url)
        if text is None:
            errors.append({'url': url, 'reason': 'fetch_failed'})
            text = ''

        company = extract_company(v2_organizations=v2_orgs, text=text)
        mw_capacity = extract_mw(text)
        city, state = extract_location(text, v2_locations=v2_locs)
        target_date = extract_target_completion_date(text)
        is_buildout, confidence = classify_buildout(text, company, mw_capacity)

        results.append({
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
        })

        time.sleep(REQUEST_DELAY)

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
