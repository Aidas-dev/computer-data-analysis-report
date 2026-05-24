#!/usr/bin/env python3
"""
pipeline_step14.py — Gridstatus ISO Queue Cross-Reference & Labeling.
Extracted from notebooks/14-gridstatus-labeling.ipynb.
Pulls ISO queue data, cross-references buildout events, labels outcomes.
"""
import os, sys, re, warnings, subprocess
from collections import defaultdict
from pathlib import Path

import pandas as pd

warnings.filterwarnings('ignore')

MARKER = "/tmp/done_pipeline_step14"
INPUT_PATH = "data/raw/buildout_events_raw.csv"
OUTPUT_PATH = "data/processed/buildout_promises_real.csv"

HAS_GRIDSTATUS = False
try:
    import gridstatus
    HAS_GRIDSTATUS = True
except ImportError:
    pass

ISO_DEFS = None
STATE_TO_ISO = None

def _init_isos():
    global ISO_DEFS, STATE_TO_ISO
    if ISO_DEFS is not None:
        return
    if not HAS_GRIDSTATUS:
        ISO_DEFS = []
        STATE_TO_ISO = {}
        return
    ISO_DEFS = [
        ('CAISO', gridstatus.CAISO, 'CAISO', ['CA']),
        ('MISO', gridstatus.MISO, 'MISO', ['IL', 'IN', 'MI', 'MN', 'WI', 'IA', 'MO', 'AR', 'LA', 'MS', 'ND', 'SD']),
        ('NYISO', gridstatus.NYISO, 'NYISO', ['NY']),
        ('SPP', gridstatus.SPP, 'SPP', ['KS', 'NE', 'OK', 'NM']),
        ('ISONE', gridstatus.ISONE, 'ISONE', ['CT', 'MA', 'ME', 'NH', 'RI', 'VT']),
        ('Ercot', gridstatus.Ercot, 'ERCOT', ['TX']),
        ('IESO', gridstatus.IESO, 'IESO', ['ON']),
    ]
    STATE_TO_ISO = {}
    for iso_name, iso_class, iso_code, states in ISO_DEFS:
        for state in states:
            STATE_TO_ISO[state] = iso_code
    for state in ['AR', 'LA', 'MO', 'SD', 'ND', 'MN', 'IA', 'TX']:
        if state not in STATE_TO_ISO:
            STATE_TO_ISO[state] = 'SPP'


def log(msg):
    print(f"[step14] {msg}", flush=True)


def parse_dates_robust(series):
    try:
        return pd.to_datetime(series, errors='coerce')
    except (ValueError, TypeError):
        # Handle mixed tz-aware and tz-naive values
        return pd.to_datetime(series, errors='coerce', utc=True)


def normalize_company(name):
    if pd.isna(name):
        return ''
    name = str(name).lower().strip()
    name = re.sub(r'\b(inc|llc|ltd|corp|corporation|company|technologies|technology|group|holdings|solutions|services|systems|na|north america|usa)\b', '', name)
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def normalize_location(loc):
    if pd.isna(loc):
        return ''
    loc = str(loc).lower().strip()
    loc = re.sub(r'\b(county|city|town|township|parish|cdp)\b', '', loc)
    loc = re.sub(r'[^a-z0-9\s]', '', loc)
    loc = re.sub(r'\s+', ' ', loc).strip()
    return loc


def company_name_match(ec, qn):
    """ec, qn are pre-normalized company strings (caller normalizes once)."""
    if not ec or not qn:
        return 0.0
    if ec == qn:
        return 1.0
    if ec in qn or qn in ec:
        return 0.8
    ec_words = set(ec.split())
    qn_words = set(qn.split())
    if len(ec_words) > 0 and len(qn_words) > 0:
        overlap = len(ec_words & qn_words) / max(len(ec_words), len(qn_words))
        if overlap >= 0.5:
            return 0.6 * overlap
    return 0.0


def location_match(ev_city_norm, ev_state, q_loc_norm):
    """ev_city_norm and q_loc_norm are pre-normalized. ev_state is raw."""
    if pd.isna(ev_state) or not q_loc_norm:
        return 0.0
    if ev_state.lower() not in q_loc_norm:
        return 0.0
    if ev_city_norm and ev_city_norm in q_loc_norm:
        return 1.0
    return 0.3


def mw_range_match(event_mw, queue_mw, tolerance=0.20):
    if pd.isna(event_mw) or pd.isna(queue_mw) or event_mw == 0:
        return 0.0
    event_mw = float(event_mw)
    queue_mw = float(queue_mw)
    if event_mw <= 0 or queue_mw <= 0:
        return 0.0
    ratio = queue_mw / event_mw
    lower = 1.0 - tolerance
    upper = 1.0 + tolerance
    if lower <= ratio <= upper:
        return 1.0 - abs(1.0 - ratio)
    elif 0.5 <= ratio <= 2.0:
        return 0.3
    return 0.0


def date_proximity(event_date, queue_date, max_days=180):
    if pd.isna(event_date) or pd.isna(queue_date):
        return 0.0
    diff = abs((event_date - queue_date).days)
    if diff <= max_days:
        return max(0.1, 1.0 - (diff / max_days))
    elif diff <= max_days * 2:
        return 0.1
    return 0.0


def score_match(event, queue_entry):
    company_score = company_name_match(
        event.get('_norm_company', ''),
        queue_entry.get('_norm_name', '')
    )
    location_score = location_match(
        event.get('_norm_location_city', ''),
        event.get('location_state'),
        queue_entry.get('_norm_county', '')
    )
    mw_score = mw_range_match(
        event.get('mw_capacity'),
        queue_entry.get('queue_mw')
    )
    date_score = date_proximity(
        event.get('announcement_date'),
        queue_entry.get('queue_date')
    )
    return (company_score * 40) + (location_score * 30) + (mw_score * 20) + (date_score * 10)


def _build_company_index(queue_df):
    """Build word→indices map from normalized queue project names.
    Returns dict[str, set[int]] mapping each word to set of row indices."""
    idx = defaultdict(set)
    for i, name in enumerate(queue_df['_norm_name']):
        if not name:
            continue
        for word in name.split():
            if len(word) >= 2:
                idx[word].add(i)
    return idx

def _get_candidate_indices(event_norm_company, company_idx):
    """Return set of queue row indices sharing at least one word with event company."""
    words = set(event_norm_company.split())
    candidates = set()
    for word in words:
        if word in company_idx:
            candidates.update(company_idx[word])
    return candidates

def find_best_queue_match(event, queue_df, min_score=50, company_idx=None):
    # Skip matching for events without location — can't meaningfully match without state
    iso = event.get('iso_region')
    event_state = event.get('location_state')
    if not iso and (pd.isna(event_state) or not str(event_state).strip()):
        return None, 0.0
    if iso and iso in queue_df['iso_region'].values:
        candidates = queue_df[queue_df['iso_region'] == iso]
    else:
        candidates = queue_df

    # Company-index filter: only score queue entries sharing a company word with event
    if company_idx is not None:
        event_words = set(event.get('_norm_company', '').split())
        if event_words:
            candidate_inds = set()
            for word in event_words:
                if word in company_idx:
                    candidate_inds.update(company_idx[word])
            if candidate_inds:
                # Intersect with ISO-filtered candidates (by index position)
                candidates = candidates.iloc[list(
                    candidate_inds & set(candidates.index)
                )] if len(candidates) > 0 else candidates

    best_score = 0
    best_match = None
    for _, qentry in candidates.iterrows():
        score = score_match(event, qentry)
        if score > best_score:
            best_score = score
            best_match = qentry
    if best_score >= min_score:
        return best_match, best_score
    return None, best_score


def assign_label(row):
    score = row.get('match_score', 0)
    if score < 50:
        return 'unmatched'
    status = str(row.get('queue_status', '')).lower().strip()
    if any(kw in status for kw in ['operating', 'completed', 'in service', 'commercial operation', 'active']):
        return 'kept'
    acd = row.get('actual_completion_date')
    if pd.notna(acd):
        try:
            if pd.to_datetime(acd) < pd.Timestamp.now():
                return 'kept'
        except Exception:
            pass
    if any(kw in status for kw in ['withdrawn', 'suspended', 'cancelled', 'terminated', 'denied', 'rejected']):
        return 'failed'
    wd = row.get('withdrawn_date')
    if pd.notna(wd):
        try:
            if pd.to_datetime(wd) < pd.Timestamp.now():
                return 'failed'
        except Exception:
            pass
    if any(kw in status for kw in ['queue', 'active', 'pending', 'queued', 'processing', 'review', 'study']):
        return 'pending'
    return 'pending'


def main():
    dry = "--dry-run" in sys.argv
    log("Step 14: Gridstatus ISO Queue Cross-Reference")
    _init_isos()

    if not HAS_GRIDSTATUS:
        log("ERROR: gridstatus not installed")
        sys.exit(1)

    if not os.path.exists(INPUT_PATH):
        log(f"ERROR: Input not found: {INPUT_PATH}")
        sys.exit(1)

    df_events = pd.read_csv(INPUT_PATH)
    log(f"Loaded {len(df_events)} events from {INPUT_PATH}")

    if 'is_buildout' in df_events.columns:
        n_total = len(df_events)
        df_events = df_events[df_events['is_buildout']].copy()
        log(f"Filtered to {len(df_events)} buildout events (from {n_total})")

    def assign_iso(row):
        state = row.get('location_state')
        if pd.isna(state):
            return None
        state = str(state).upper().strip()
        return STATE_TO_ISO.get(state, None)

    df_events['iso_region'] = df_events.apply(assign_iso, axis=1)

    queue_dfs = []
    failed_isos = []

    for iso_name, iso_class, iso_code, states in ISO_DEFS:
        log(f"Pulling {iso_name} ({iso_code})...")
        try:
            iso = iso_class()
            qdf = iso.get_interconnection_queue()
            if qdf is not None and len(qdf) > 0:
                qdf['iso_region'] = iso_code
                queue_dfs.append(qdf)
                log(f"{len(qdf)} projects loaded")
            else:
                log("empty result")
        except Exception as e:
            failed_isos.append(iso_code)
            log(f"FAILED: {e}")

    if not queue_dfs:
        log("ERROR: No queue data from any ISO")
        sys.exit(1)

    df_queue = pd.concat(queue_dfs, ignore_index=True)
    log(f"Unified queue: {len(df_queue)} projects from {len(queue_dfs)} ISOs")
    if failed_isos:
        log(f"Failed ISOs: {', '.join(failed_isos)}")

    col_map = {}
    for candidate in ['Status', 'status', 'queue_status', 'QUEUE_STATUS', 'project_status']:
        if candidate in df_queue.columns:
            col_map['queue_status'] = candidate
            break
    for candidate in ['Capacity (MW)', 'capacity_mw', 'Capacity MW', 'MW', 'capacity', 'Capacity', 'Size (MW)']:
        if candidate in df_queue.columns:
            col_map['queue_mw'] = candidate
            break
    for candidate in ['Queue Date', 'queue_date', 'Queue Date (Application)', 'application_date', 'queue_date_submitted']:
        if candidate in df_queue.columns:
            col_map['queue_date'] = candidate
            break
    for candidate in ['County', 'county', 'County (State)', 'location', 'Location', 'State', 'state']:
        if candidate in df_queue.columns:
            col_map['queue_county'] = candidate
            break
    for candidate in ['Project Name', 'project_name', 'Project', 'project', 'Queue Name']:
        if candidate in df_queue.columns:
            col_map['project_name'] = candidate
            break
    for candidate in ['Withdrawn Date', 'withdrawn_date', 'Withdrawal Date', 'Date Withdrawn']:
        if candidate in df_queue.columns:
            col_map['withdrawn_date'] = candidate
            break
    for candidate in ['Actual Completion Date', 'actual_completion_date', 'Completion Date', 'Commercial Operation Date',
                      'COD', 'In Service Date', 'Operating Date']:
        if candidate in df_queue.columns:
            col_map['actual_completion_date'] = candidate
            break

    rename_dict = {v: k for k, v in col_map.items()}
    df_queue = df_queue.rename(columns=rename_dict)
    for col in ['queue_status', 'queue_mw', 'queue_date', 'queue_county', 'project_name']:
        if col not in df_queue.columns:
            df_queue[col] = None

    ecm = {}
    for candidate in ['announcement_date', 'date', 'DATE', 'published_date', 'ArticleDate']:
        if candidate in df_events.columns:
            ecm['announcement_date'] = candidate
            break
    if 'announcement_date' not in ecm:
        ecm['announcement_date'] = 'announcement_date'
        if 'announcement_date' not in df_events.columns:
            df_events['announcement_date'] = None
    for candidate in ['company', 'Company', 'company_name', 'matched_company', 'v2_organizations']:
        if candidate in df_events.columns:
            ecm['company'] = candidate
            break
    if 'company' not in ecm:
        ecm['company'] = 'company'
        if 'company' not in df_events.columns:
            df_events['company'] = None
    for candidate in ['mw_capacity', 'MW', 'mw', 'capacity_mw', 'Capacity_MW', 'promised_mw']:
        if candidate in df_events.columns:
            ecm['mw_capacity'] = candidate
            break
    if 'mw_capacity' not in ecm:
        ecm['mw_capacity'] = 'mw_capacity'
        if 'mw_capacity' not in df_events.columns:
            df_events['mw_capacity'] = None
    for candidate in ['location_city', 'city', 'City', 'location']:
        if candidate in df_events.columns:
            ecm['location_city'] = candidate
            break
    if 'location_city' not in ecm:
        ecm['location_city'] = 'location_city'
        if 'location_city' not in df_events.columns:
            df_events['location_city'] = None
    for candidate in ['location_state', 'state', 'State', 'location_state_code']:
        if candidate in df_events.columns:
            ecm['location_state'] = candidate
            break
    if 'location_state' not in ecm:
        ecm['location_state'] = 'location_state'
        if 'location_state' not in df_events.columns:
            df_events['location_state'] = None
    for candidate in ['target_completion_date', 'target_date', 'completion_date', 'Target Completion Date']:
        if candidate in df_events.columns:
            ecm['target_completion_date'] = candidate
            break
    if 'target_completion_date' not in ecm:
        ecm['target_completion_date'] = 'target_completion_date'
        if 'target_completion_date' not in df_events.columns:
            df_events['target_completion_date'] = None

    for col in ['announcement_date', 'target_completion_date']:
        if col in df_events.columns:
            df_events[col] = parse_dates_robust(df_events[col])

    for col in ['queue_date', 'withdrawn_date', 'actual_completion_date']:
        if col in df_queue.columns:
            df_queue[col] = parse_dates_robust(df_queue[col])

    if 'queue_mw' in df_queue.columns:
        df_queue['queue_mw'] = pd.to_numeric(df_queue['queue_mw'], errors='coerce')

    if 'mw_capacity' in df_events.columns:
        df_events['mw_capacity'] = pd.to_numeric(df_events['mw_capacity'], errors='coerce')

    log("Pre-normalizing text columns for matching...")
    df_events['_norm_company'] = df_events['company'].apply(normalize_company)
    df_events['_norm_location_city'] = df_events['location_city'].apply(
        lambda x: normalize_location(str(x)) if pd.notna(x) else ''
    )
    df_events['_norm_location_state'] = df_events['location_state'].apply(
        lambda x: str(x).upper().strip() if pd.notna(x) else ''
    )
    df_queue['_norm_name'] = df_queue['project_name'].apply(
        lambda x: normalize_company(str(x)) if pd.notna(x) else ''
    )
    df_queue['_norm_county'] = df_queue['queue_county'].apply(
        lambda x: normalize_location(str(x)) if pd.notna(x) else ''
    )

    company_idx = _build_company_index(df_queue)

    matches = []
    total_events = len(df_events)
    log(f"Cross-referencing {total_events} events vs {len(df_queue)} queue projects...")

    if dry:
        log(f"DRY RUN — would process {total_events} events")
        Path(MARKER).write_text("OK\ndry-run")
        return

    for idx, event in df_events.iterrows():
        best_match = None
        score = 0.0
        if pd.notna(event.get('iso_region')):
            best_match, score = find_best_queue_match(event, df_queue, company_idx=company_idx)
        if best_match is not None:
            matches.append({
                'event_idx': idx,
                'match_score': round(score, 1),
                'matched_iso': best_match.get('iso_region'),
                'queue_status': best_match.get('queue_status'),
                'queue_mw': best_match.get('queue_mw'),
                'queue_date': best_match.get('queue_date'),
                'queue_county': best_match.get('queue_county'),
                'actual_completion_date': best_match.get('actual_completion_date'),
                'withdrawn_date': best_match.get('withdrawn_date'),
                'project_name': best_match.get('project_name'),
            })
        else:
            matches.append({
                'event_idx': idx, 'match_score': 0,
                'matched_iso': None, 'queue_status': None,
                'queue_mw': None, 'queue_date': None,
                'queue_county': None, 'actual_completion_date': None,
                'withdrawn_date': None, 'project_name': None,
            })
        if (idx + 1) % 50 == 0:
            log(f"  Processed {idx+1}/{total_events}")

    df_matches = pd.DataFrame(matches).set_index('event_idx')
    n_matched = (df_matches['match_score'] >= 50).sum()
    log(f"Matched: {n_matched}/{total_events} (score >= 50)")

    df_events['queue_status'] = df_matches['queue_status']
    df_events['queue_date'] = df_matches['queue_date']
    df_events['queue_mw'] = df_matches['queue_mw']
    df_events['queue_county'] = df_matches['queue_county']
    df_events['actual_completion_date'] = df_matches['actual_completion_date']
    df_events['match_score'] = df_matches['match_score']
    df_events['label'] = df_matches.apply(assign_label, axis=1)

    label_counts = df_events['label'].value_counts()
    for label in ['kept', 'failed', 'pending', 'unmatched']:
        c = label_counts.get(label, 0)
        log(f"  {label}: {c} ({c/len(df_events)*100:.1f}%)")

    OUTPUT_COLS = [
        'url', 'source_domain', 'announcement_date', 'company',
        'location_city', 'location_state', 'mw_capacity',
        'target_completion_date', 'is_buildout', 'confidence',
        'iso_region', 'queue_status', 'queue_date', 'queue_mw',
        'queue_county', 'actual_completion_date', 'match_score', 'label'
    ]
    for col in OUTPUT_COLS:
        if col not in df_events.columns:
            df_events[col] = None

    existing_cols = [c for c in OUTPUT_COLS if c in df_events.columns]
    df_output = df_events[existing_cols].copy()

    date_cols = ['announcement_date', 'target_completion_date', 'queue_date', 'actual_completion_date']
    for col in date_cols:
        if col in df_output.columns:
            df_output[col] = df_output[col].apply(
                lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else ''
            )

    os.makedirs("data/processed", exist_ok=True)
    df_output.to_csv(OUTPUT_PATH, index=False)
    log(f"Saved {len(df_output)} rows to {OUTPUT_PATH}")

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
    main()
