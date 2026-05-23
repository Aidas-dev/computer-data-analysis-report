#!/usr/bin/env python3
"""
pipeline_step12.py — GDELT Domain-Filtered Buildout Mining.
Extracted from notebooks/12-gdelt-domain-filter.ipynb.
Runs BQ query against GDELT v2 GKG, domain-filtered, writes candidates CSV.
"""
import os, sys, json, warnings, subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

warnings.filterwarnings('ignore')

MARKER = "/tmp/done_pipeline_step12"
OUTPUT_PATH = "data/raw/buildout_candidates_gkg.csv"

COMPANY_KEYWORDS = [
    'Microsoft', 'Google', 'Alphabet', 'Amazon', 'AWS',
    'Meta', 'Facebook', 'NVIDIA', 'Nvidia', 'Apple',
    'Oracle', 'Crusoe', 'Equinix', 'Digital Realty',
    'American Tower', 'Prologis', 'Simon Property',
    'Public Storage', 'Outfront', 'Sabra',
    'Hudson Pacific', 'Rexford', 'First Industrial', 'SITC',
]


def log(msg):
    print(f"[step12] {msg}", flush=True)


def authenticate_bq():
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        for cred_path in ["/content/gcp_adc.json", "docs/gcp_adc.json"]:
            if os.path.exists(cred_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
                log(f"Credentials: {cred_path}")
                break
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS not set")
    if not project:
        try:
            with open(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]) as f:
                creds = json.load(f)
                project = creds.get("project_id", "")
        except Exception as e:
            raise RuntimeError("Could not read credentials: %s" % e)
    if not project:
        raise RuntimeError("Could not determine GCP project ID")
    client = bigquery.Client(project=project)
    datasets = list(client.list_datasets())
    log(f"BQ OK: {len(datasets)} datasets, project={project}")
    return client


def build_sql():
    start_date = '2020-01-01'
    end_date = datetime.now().strftime('%Y-%m-%d')
    org_conditions = ' OR '.join(
        f"V2Organizations LIKE '%{kw}%'" for kw in COMPANY_KEYWORDS
    )
    sql = f"""
    SELECT
      DATE, SourceCommonName, DocumentIdentifier,
      V2Organizations, V2Locations, V2Tone
    FROM `gdelt-bq.gdeltv2.gkg_partitioned`
    WHERE _PARTITIONTIME >= TIMESTAMP("{start_date}")
      AND SourceCommonName IN (
        'datacenterdynamics.com',
        'datacenterknowledge.com',
        'siliconangle.com'
      )
      AND ({org_conditions})
    ORDER BY DATE DESC
    """
    log(f"Date range: {start_date} to {end_date}")
    log(f"SQL defined ({len(sql.split())} words)")
    return sql


def dry_run(client, sql, max_gb=600):
    log("Dry run...")
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry_run_job = client.query(sql, job_config=job_config)
    bytes_processed = dry_run_job.total_bytes_processed
    gb_processed = bytes_processed / 1e9
    cost_usd = gb_processed / 1000 * 5  # $5/TB
    log(f"Would process: {bytes_processed:,} bytes ({gb_processed:.2f} GB, ~${cost_usd:.2f})")
    if gb_processed > max_gb:
        raise RuntimeError("%.2f GB exceeds %d GB limit!" % (gb_processed, max_gb))
    log("Dry run OK — within budget")
    return gb_processed


def execute_query(client, sql):
    log("Executing query...")
    query_job = client.query(sql)
    df = query_job.to_dataframe()
    bytes_billed = int(query_job.total_bytes_billed or 0)
    log(f"Query returned {len(df)} rows, {bytes_billed/1e9:.2f} GB billed")
    if df.empty:
        raise RuntimeError("No results returned")
    return df


def compute_summary(df):
    log("\n--- Per-domain count ---")
    for domain, count in df['SourceCommonName'].value_counts().items():
        log(f"  {domain}: {count}")

    def find_matching_companies(org_str):
        found = []
        for kw in COMPANY_KEYWORDS:
            if kw.lower() in str(org_str).lower():
                found.append(kw)
        return found if found else ['unknown']

    df['matched_companies'] = df['V2Organizations'].apply(find_matching_companies)
    df_exploded = df.explode('matched_companies')
    log("--- Per-company mentions ---")
    for company, count in df_exploded['matched_companies'].value_counts().items():
        log(f"  {company}: {count}")

    df['year'] = df['DATE'].astype(str).str[:4]
    log("--- Per-year count ---")
    for year, count in df['year'].value_counts().sort_index().items():
        log(f"  {year}: {count}")
    log(f"Total candidates: {len(df)}")


def save_output(df):
    os.makedirs("data/raw", exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    log(f"Saved {len(df)} rows to {OUTPUT_PATH}")

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


def main():
    dry = "--dry-run" in sys.argv
    log("Step 12: GDELT Domain-Filtered Buildout Mining")
    try:
        client = authenticate_bq()
    except Exception as e:
        if dry:
            log("DRY RUN — BQ auth skipped (%s)" % e)
            Path(MARKER).write_text("OK\ndry-run")
            return
        raise
    sql = build_sql()

    try:
        gb = dry_run(client, sql)
    except Exception as e:
        if dry:
            log("DRY RUN — BQ dry run failed (%s)" % e)
            Path(MARKER).write_text("OK\ndry-run")
            return
        raise

    if dry:
        log("DRY RUN — stopping (would process %.2f GB)" % gb)
        Path(MARKER).write_text("OK\ndry-run")
        return

    df = execute_query(client, sql)
    compute_summary(df)
    save_output(df)

    Path(MARKER).write_text("OK\n")
    log("Step 12 complete.")


if __name__ == "__main__":
    main()
