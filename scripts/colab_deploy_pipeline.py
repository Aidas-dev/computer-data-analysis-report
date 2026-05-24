#!/usr/bin/env python3
"""
colab_deploy_pipeline.py — Runs ON colab VM.
Executes pipeline scripts 12→13→14 via detached nohup python3 (no Jupyter kernel).
"""
import base64, os, subprocess, sys, time
from pathlib import Path

CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY")
FRED_API_KEY = os.environ.get("FRED_API_KEY")
OCI_ACCESS_KEY = os.environ.get("OCI_ACCESS_KEY")
OCI_SECRET_KEY = os.environ.get("OCI_SECRET_KEY")
GCP_ADC_B64 = os.environ.get("GCP_ADC_B64")

REQUIRED_ENV_VARS = ["CENSUS_API_KEY", "FRED_API_KEY", "OCI_ACCESS_KEY", "OCI_SECRET_KEY", "GCP_ADC_B64"]


def validate_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        print(f"[pipeline] FATAL: Missing required env vars: {', '.join(missing)}", flush=True)
        sys.exit(1)
    log("All required env vars found.")

REPO_URL = "https://github.com/Aidas-dev/computer-data-analysis-report.git"
REPO_DIR = "/content/computer-data-analysis-report"
SCRIPTS = ["pipeline_step12", "pipeline_step13", "pipeline_step14"]

os.chdir("/content")

def log(msg):
    print(f"[pipeline] {msg}", flush=True)

def run(cmd, timeout=300, check=True):
    log(f"$ {cmd[:120]}")
    r = subprocess.run(cmd, shell=True, timeout=timeout, capture_output=True, text=True)
    if check and r.returncode != 0:
        log(f"FAIL: {cmd[:80]}")
        raise RuntimeError(f"FAIL: {cmd[:80]}")
    return r

def write_env():
    Path("/content/.env").write_text(
        f"CENSUS_API_KEY={CENSUS_API_KEY}\nFRED_API_KEY={FRED_API_KEY}\n"
        f"OCI_ACCESS_KEY={OCI_ACCESS_KEY}\nOCI_SECRET_KEY={OCI_SECRET_KEY}\n")
    Path("/content/gcp_adc.json").write_bytes(base64.b64decode(GCP_ADC_B64))
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/content/gcp_adc.json"
    log("Secrets written.")

def clone_repo():
    if Path(REPO_DIR).exists():
        run(f"git -C {REPO_DIR} pull --ff-only", timeout=60)
    else:
        run(f"git clone --depth 1 {REPO_URL} {REPO_DIR}", timeout=120)
    os.chdir(REPO_DIR)

def install_deps():
    run("pip install uv -q", timeout=30)
    run("uv pip install --system -r requirements.txt -q", timeout=300)
    run("uv pip install --system newspaper3k lxml_html_clean trafilatura gridstatus -q", timeout=120)

def setup_dvc():
    run(f"dvc remote modify --local oracle_remote access_key_id '{OCI_ACCESS_KEY}'")
    run(f"dvc remote modify --local oracle_remote secret_access_key '{OCI_SECRET_KEY}'")
    run("dvc pull -q", timeout=300)

def verify_bq():
    try:
        os.environ["GOOGLE_CLOUD_PROJECT"] = "project-21db66e7-39ca-4fda-b4e"
        from google.cloud import bigquery
        client = bigquery.Client()
        ds = list(client.list_datasets())
        log(f"BQ OK: {len(ds)} datasets")
        return True
    except Exception as e:
        log(f"BQ FAIL: {e}")
        return False

def run_script(script_name, timeout=1800):
    script_path = f"scripts/{script_name}.py"
    marker = f"/tmp/done_{script_name}"
    logfile = f"/tmp/{script_name}.log"

    if not Path(script_path).exists():
        log(f"SKIP {script_name} (not found)")
        return True

    Path(marker).unlink(missing_ok=True)

    subprocess.run(
        f"cd {REPO_DIR} && nohup python3 {script_path} > {logfile} 2>&1 &",
        shell=True, timeout=10)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if Path(marker).exists():
            result = Path(marker).read_text().strip()
            ok = result.startswith("OK")
            log(f"{'OK' if ok else 'FAIL'} {script_name}")
            return ok
        time.sleep(10)

    log(f"TIMEOUT {script_name} after {timeout}s")
    return False

def dvc_push():
    for pattern in ["data/raw/buildout_candidates*.csv.dvc",
                    "data/processed/buildout_events*.csv.dvc",
                    "data/processed/buildout_promises_real*.csv.dvc"]:
        for f in Path(REPO_DIR).glob(pattern):
            try:
                run(f"dvc push {f}", timeout=120, check=False)
                log(f"DVC pushed: {f.name}")
            except:
                log(f"DVC push FAIL: {f.name}")

def main():
    validate_env()
    log("=== Pipeline: Remote Runner ===")
    write_env()
    clone_repo()
    install_deps()
    setup_dvc()
    if not verify_bq():
        sys.exit(1)
    results = {}
    for script in SCRIPTS:
        results[script] = run_script(script)
    dvc_push()
    log("\n=== SUMMARY ===")
    for script, ok in results.items():
        log(f"  {'OK' if ok else 'FAIL'}: {script}")
    if all(results.values()):
        log("ALL OK")
    else:
        log("SOME FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
