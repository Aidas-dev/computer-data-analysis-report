#!/usr/bin/env python3
"""
consolidate_fractracker_gdelt.py — Match FracTracker datacenter sites
to GDELT buildout events via multi-factor scoring, produce merged dataset.

Inputs:
  data/raw/fractracker_datacenters.csv
  data/processed/buildout_promises_real.csv

Output:
  data/processed/fractracker_gdelt_merged.csv

Matching (threshold >= 50):
  - Company name overlap (40 pts): word-set overlap between
    operator_name/tenant and company
  - State match (30 pts): same state
  - MW proximity (20 pts): ±20% range overlap
  - Name substring (10 pts): facility_name contains company name
"""

import argparse
import os
import re
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

# ── Default paths ──
FRACTRACKER_PATH = "data/raw/fractracker_datacenters.csv"
GDELT_PATH = "data/processed/buildout_promises_real.csv"
OUTPUT_PATH = "data/processed/fractracker_gdelt_merged.csv"

# ── Scoring weights ──
W_COMPANY = 40
W_LOCATION = 30
W_MW = 20
W_SUBSTRING = 10
MATCH_THRESHOLD = 50

# ── Text normalisation ──
PUNCT_RE = re.compile(r"[^\w\s]")
STOPWORDS = {
    "llc", "inc", "corp", "corporation", "lp", "ltd", "limited",
    "company", "co", "group", "partners", "holdings", "capital",
    "management", "trust", "properties", "property", "realty",
    "ventures", "development", "data", "center", "centers",
    "dc", "services", "solutions", "technologies", "technology",
    "and", "the", "of", "for", "a", "an",
}


def log(msg: str):
    print(f"[consolidate] {msg}", flush=True)


# ── MW parsing ──

def parse_mw(val):
    """Parse MW value to float (midpoint for ranges).

    Handles: '100', '100-200', '1,000', '100-1,000', '100+', empty, NaN.
    Returns float or None.
    """
    if pd.isna(val):
        return None
    s = str(val).strip().replace(",", "").replace("+", "").replace("?", "")
    if not s:
        return None
    m = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", s)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2.0
    try:
        return float(s)
    except ValueError:
        return None


# ── Name normalisation ──

def normalize_name(name):
    """Lowercase, strip punctuation, remove stopwords, return word set."""
    if pd.isna(name) or not isinstance(name, str):
        return set()
    cleaned = PUNCT_RE.sub(" ", name.lower()).strip()
    return set(w for w in cleaned.split() if w not in STOPWORDS and len(w) > 1)


def word_overlap(words_a: set, words_b: set) -> float:
    """Jaccard overlap between two word sets."""
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


# ── Scoring functions (each returns unweighted 0-1 or weighted 0-W_*) ──

def company_score(operator, tenant, company) -> float:
    """Score 0-1 for company name overlap between operator/tenant and company."""
    g_words = normalize_name(company)
    if not g_words:
        return 0.0
    scores = []
    for src in [operator, tenant]:
        if pd.isna(src) or not isinstance(src, str) or not src.strip():
            continue
        scores.append(word_overlap(normalize_name(src), g_words))
    return max(scores) if scores else 0.0


def location_score(ft_state, gdelt_state) -> int:
    """Score W_LOCATION if states match, else 0."""
    ft_s = str(ft_state).strip().upper() if pd.notna(ft_state) else ""
    gd_s = str(gdelt_state).strip().upper() if pd.notna(gdelt_state) else ""
    return W_LOCATION if ft_s and gd_s and ft_s == gd_s else 0


def mw_score(ft_mw, gdelt_mw) -> float:
    """Score 0-W_MW based on MW proximity (±20% range overlap).

    If values are within 20% of each other, score scales linearly
    from W_MW (identical) to 0 (exactly 20% apart). Beyond 20% → 0.
    """
    ft_val = parse_mw(ft_mw)
    gd_val = parse_mw(gdelt_mw)
    if ft_val is None and gd_val is None:
        return 0
    if ft_val is None or gd_val is None:
        return W_MW / 2.0
    if ft_val <= 0 or gd_val <= 0:
        return 0
    max_val = max(ft_val, gd_val)
    ratio = abs(ft_val - gd_val) / max_val
    if ratio >= 0.2:
        return 0
    return W_MW * (1.0 - ratio / 0.2)


def substring_score(facility_name, company) -> int:
    """Score W_SUBSTRING if facility_name contains company name as substring."""
    if pd.isna(facility_name) or not isinstance(facility_name, str):
        return 0
    if pd.isna(company) or not isinstance(company, str):
        return 0
    fn = facility_name.lower().strip()
    cn = company.lower().strip()
    if not fn or not cn:
        return 0
    return W_SUBSTRING if cn in fn else 0


# ── Match type classification ──

def classify(c_weighted, l_weighted, m_weighted, s_weighted) -> str:
    """Classify match type by which factors contributed meaningfully (>=50% weight)."""
    factors = []
    if c_weighted >= W_COMPANY * 0.5:
        factors.append("company")
    if l_weighted >= W_LOCATION:
        factors.append("location")
    if m_weighted >= W_MW * 0.5:
        factors.append("mw")
    if s_weighted >= W_SUBSTRING * 0.5:
        factors.append("substring")
    if not factors:
        return "unmatched"
    if len(factors) >= 2:
        return "+".join(factors)
    return factors[0] + "_only"


# ── Matching engine ──

def match_best_gdelt(ft_row, gdelt_df, threshold=MATCH_THRESHOLD):
    """Find best GDELT match for a single FracTracker row.

    Returns (gdelt_idx, score, match_type) or (None, best_score, "unmatched").
    """
    best_idx = None
    best_score = 0.0

    ft_op = ft_row.get("operator_name", "")
    ft_tenant = ft_row.get("tenant", "")
    ft_state = ft_row.get("state", "")
    ft_mw = ft_row.get("mw", "")
    ft_facility = ft_row.get("facility_name", "")

    for idx, gr in gdelt_df.iterrows():
        c_score_val = company_score(ft_op, ft_tenant, gr.get("company", ""))
        l_score_val = location_score(ft_state, gr.get("location_state", ""))
        m_score_val = mw_score(ft_mw, gr.get("mw_capacity", ""))
        s_score_val = substring_score(ft_facility, gr.get("company", ""))

        total = W_COMPANY * c_score_val + l_score_val + m_score_val + s_score_val
        if total > best_score:
            best_score = total
            best_idx = idx

    if best_score >= threshold:
        gr = gdelt_df.loc[best_idx]
        mt = classify(
            W_COMPANY * company_score(ft_op, ft_tenant, gr.get("company", "")),
            location_score(ft_state, gr.get("location_state", "")),
            mw_score(ft_mw, gr.get("mw_capacity", "")),
            substring_score(ft_facility, gr.get("company", "")),
        )
        return best_idx, round(best_score, 1), mt

    return None, round(best_score, 1), "unmatched"


# ── Summary ──

def print_summary(ft_count, gdelt_count, merged_df):
    """Print merge summary statistics."""
    matched = merged_df["is_matched"].sum()
    unmatched_gdelt = gdelt_count - merged_df["is_matched"].sum()

    log("")
    log("=" * 60)
    log("MERGE SUMMARY")
    log("=" * 60)
    log(f"  Total FracTracker sites:          {ft_count}")
    log(f"  Total GDELT events:               {gdelt_count}")
    log(f"  Matched:                          {matched}")
    log(f"  Unmatched FracTracker:             {ft_count - matched}")
    log(f"  Unmatched GDELT:                   {unmatched_gdelt}")

    log("")
    log("── Per-state match counts (top 15) ──")
    state_counts = (
        merged_df[merged_df["is_matched"]]
        .groupby("ft_state")
        .size()
        .sort_values(ascending=False)
        .head(15)
    )
    for state, cnt in state_counts.items():
        log(f"  {state if state else '(unknown)'}: {cnt}")

    log("")
    log("── Per-company match counts (top 15) ──")
    comps = (
        merged_df[merged_df["is_matched"]]["gdelt_company"]
        .value_counts()
        .head(15)
    )
    for comp, cnt in comps.items():
        log(f"  {comp}: {cnt}")

    log("")
    log("── Match type breakdown ──")
    for mt, cnt in merged_df["match_type"].value_counts().items():
        log(f"  {mt}: {cnt}")


# ── Main ──

def main():
    parser = argparse.ArgumentParser(
        description="Consolidate FracTracker datacenter sites with GDELT buildout events"
    )
    parser.add_argument(
        "--fractracker", type=str, default=FRACTRACKER_PATH,
        help=f"Path to FracTracker CSV (default: {FRACTRACKER_PATH})",
    )
    parser.add_argument(
        "--gdelt", type=str, default=GDELT_PATH,
        help=f"Path to GDELT CSV (default: {GDELT_PATH})",
    )
    parser.add_argument(
        "--output", type=str, default=OUTPUT_PATH,
        help=f"Output CSV path (default: {OUTPUT_PATH})",
    )
    parser.add_argument(
        "--threshold", type=float, default=MATCH_THRESHOLD,
        help=f"Match threshold 0-100 (default: {MATCH_THRESHOLD})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Load CSVs and validate schema only (no matching, no output)",
    )
    args = parser.parse_args()

    log("Consolidate FracTracker ↔ GDELT")

    if not os.path.exists(args.fractracker):
        log(f"ERROR: Input not found: {args.fractracker}")
        raise SystemExit(1)
    if not os.path.exists(args.gdelt):
        log(f"ERROR: Input not found: {args.gdelt}")
        raise SystemExit(1)

    ft_df = pd.read_csv(args.fractracker)
    gdelt_df = pd.read_csv(args.gdelt)

    ft_count = len(ft_df)
    gdelt_count = len(gdelt_df)
    log(f"Loaded {ft_count} FracTracker sites, {gdelt_count} GDELT events")

    req_ft = {"operator_name", "tenant", "state", "mw", "facility_name"}
    req_gdelt = {"company", "location_state", "mw_capacity"}
    missing_ft = req_ft - set(ft_df.columns)
    missing_gdelt = req_gdelt - set(gdelt_df.columns)
    if missing_ft:
        log(f"WARNING: FracTracker missing columns: {missing_ft}")
    if missing_gdelt:
        log(f"WARNING: GDELT missing columns: {missing_gdelt}")

    if args.dry_run:
        log("DRY RUN — validation passed, no matching performed")
        return

    log("Matching...")
    records = []
    matched_gdelt_indices = set()

    for ft_idx, ft_row in ft_df.iterrows():
        if ft_idx > 0 and ft_idx % 200 == 0:
            log(f"  Processed {ft_idx}/{ft_count}")

        best_idx, score, match_type = match_best_gdelt(ft_row, gdelt_df, threshold=args.threshold)

        rec = {f"ft_{col}": ft_row[col] for col in ft_df.columns}

        if best_idx is not None:
            matched_gdelt_indices.add(best_idx)
            gr = gdelt_df.loc[best_idx]
            rec.update({f"gdelt_{col}": gr[col] for col in gdelt_df.columns})
            rec["is_matched"] = True
        else:
            rec.update({f"gdelt_{col}": pd.NA for col in gdelt_df.columns})
            rec["is_matched"] = False

        rec["match_score"] = score
        rec["match_type"] = match_type
        records.append(rec)

    merged_df = pd.DataFrame(records)

    merged_df["is_matched"] = merged_df["is_matched"].astype(bool)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    merged_df.to_csv(args.output, index=False)
    log(f"Saved {len(merged_df)} rows to {args.output}")

    print_summary(ft_count, gdelt_count, merged_df)


if __name__ == "__main__":
    main()
