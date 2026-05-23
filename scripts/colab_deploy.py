#!/usr/bin/env -S colab run --session buildout-pipeline
"""colab_deploy.py — Run full pipeline on fresh colab VM.
Usage: colab run scripts/colab_deploy.py
"""

import base64, os, subprocess, sys, time
from pathlib import Path

CENSUS_API_KEY = "e8afaf7cff13d0d152e32bf98c0ac244c63db787"
FRED_API_KEY = "4aeb77367579a1c44a91f61ed6b991fe"
OCI_ACCESS_KEY = "542d2f34b5d73eb0b89705355f1ec6f4a0f4b44e"
OCI_SECRET_KEY = "ps/7lxHnEmGMoPK4EwYtRmpVOXqPbTK7qOkJpY791/k="
GCP_ADC_B64 = "ewogICJhY2NvdW50IjogIiIsCiAgImNsaWVudF9pZCI6ICI3NjQwODYwNTE4NTAtNnFyNHA2Z3BpNmhuNTA2cHQ4ZWp1cTgzZGkzNDFodXIuYXBwcy5nb29nbGV1c2VyY29udGVudC5jb20iLAogICJjbGllbnRfc2VjcmV0IjogImQtRkw5NVExOXE3TVFtRnBkN2hIRDBUeSIsCiAgInF1b3RhX3Byb2plY3RfaWQiOiAicHJvamVjdC0yMWRiNjZlNy0zOWNhLTRmZGEtYjRlIiwKICAicmVmcmVzaF90b2tlbiI6ICIxLy8wY2pXa1c0SnZSSlhkQ2dZSUFSQUFHQXdTTndGLUw5SXIzSzY3Y054UkRXWTdxVnA2ODlqVFBtQVM3bHFEeXBuNHdSYzVNNFFieUhVcHFaa25yM0doWGJ4RDJLc3JxUmh5Vkp3IiwKICAidHlwZSI6ICJhdXRob3JpemVkX3VzZXIiLAogICJ1bml2ZXJzZV9kb21haW4iOiAiZ29vZ2xlYXBpcy5jb20iCn0="

REPO_URL = "https://github.com/Aidas-dev/computer-data-analysis-report.git"
REPO_DIR = "/content/computer-data-analysis-report"
FORCE_RERUN = os.environ.get("FORCE_RERUN", "0") == "1"

os.chdir("/content")


def log(msg):
    print(f"[deploy] {msg}", flush=True)


def run(cmd, timeout=600):
    log(f"$ {cmd[:150]}")
    r = subprocess.run(cmd, shell=True, timeout=timeout, capture_output=True, text=True)
    for line in r.stdout.strip().split("\n"):
        print(f"  {line}")
    if r.returncode != 0:
        for line in r.stderr.strip().split("\n")[-5:]:
            print(f"  ERR: {line}")
        raise RuntimeError(f"FAIL (rc={r.returncode}): {cmd[:80]}")
    return r


def write_env():
    Path("/content/.env").write_text(
        f"CENSUS_API_KEY={CENSUS_API_KEY}\nFRED_API_KEY={FRED_API_KEY}\n"
        f"OCI_ACCESS_KEY={OCI_ACCESS_KEY}\nOCI_SECRET_KEY={OCI_SECRET_KEY}\n"
    )
    Path("/content/gcp_adc.json").write_bytes(base64.b64decode(GCP_ADC_B64))
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/content/gcp_adc.json"
    os.environ["GOOGLE_CLOUD_PROJECT"] = "project-21db66e7-39ca-4fda-b4e"
    log("Secrets written.")


def clone_repo():
    if Path(REPO_DIR).exists():
        log("Repo exists. Pulling.")
        run(f"git -C {REPO_DIR} pull --ff-only", timeout=60)
    else:
        log("Cloning repo.")
        run(f"git clone --depth 1 {REPO_URL} {REPO_DIR}", timeout=120)
    os.chdir(REPO_DIR)


def install_deps():
    run("pip install uv -q", timeout=30)
    run("uv pip install --system -r requirements.txt -q", timeout=300)
    run("uv pip install --system newspaper3k lxml_html_clean trafilatura gridstatus -q", timeout=120)
    log("Deps installed.")


def setup_dvc():
    run(f"dvc remote modify --local oracle_remote access_key_id '{OCI_ACCESS_KEY}'")
    run(f"dvc remote modify --local oracle_remote secret_access_key '{OCI_SECRET_KEY}'")
    run("dvc pull -q", timeout=300)
    log("DVC setup done.")


def verify_bq():
    try:
        from google.cloud import bigquery
        client = bigquery.Client()
        ds = list(client.list_datasets())
        log(f"BQ OK: {len(ds)} datasets")
        return True
    except Exception as e:
        log(f"BQ FAIL: {e}")
        return False


def run_pipeline_step(num):
    script = f"scripts/pipeline_step{num}.py"
    marker = f"/tmp/done_pipeline_step{num}"
    logfile = f"/tmp/pipeline_step{num}.log"

    if not FORCE_RERUN and Path(marker).exists():
        result = Path(marker).read_text().strip()
        log(f"SKIP step{num} (already done: {result})")
        return result.startswith("OK")

    Path(marker).unlink(missing_ok=True)

    log(f"=== Step {num}: {script} ===")
    try:
        r = run(f"cd {REPO_DIR} && python3 {script}", timeout=3600)
        Path(marker).write_text(f"OK (rc=0)")
        log(f"OK step{num}")
        return True
    except Exception as e:
        log(f"FAIL step{num}: {e}")
        Path(marker).write_text(f"FAIL: {e}")
        return False


def dvc_push():
    log("=== DVC Push ===")
    for pattern in ["data/raw/buildout_candidates*.csv.dvc",
                    "data/processed/buildout_events*.csv.dvc",
                    "data/processed/buildout_promises_real*.csv.dvc"]:
        for f in Path(REPO_DIR).glob(pattern):
            try:
                run(f"dvc push {f}", timeout=120)
                log(f"Pushed: {f.name}")
            except Exception as e:
                log(f"DVC push FAIL: {f.name}: {e}")


def main():
    steps = os.environ.get("STEPS", "12,13,14")
    step_nums = [int(s.strip()) for s in steps.split(",")]

    log(f"=== Pipeline Deploy (steps {step_nums}) ===")
    write_env()

    if 12 in step_nums:
        clone_repo()
        install_deps()
        setup_dvc()
        if not verify_bq():
            log("BQ auth failed — can't proceed with step 12")
            sys.exit(1)

    ok = True
    for num in step_nums:
        if not run_pipeline_step(num):
            log(f"Step {num} FAILED — continuing to next")
            ok = False

    dvc_push()

    if ok:
        log("=== ALL OK ===")
    else:
        log("=== SOME FAILED ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
