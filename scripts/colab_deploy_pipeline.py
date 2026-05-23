#!/usr/bin/env python3
"""
colab_deploy_pipeline.py — Runs ON colab VM.
Executes notebooks 12→13→14 sequentially via detached nohup to avoid
colab exec kernel timeout on long-running nbconvert subprocesses.
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
NOTEBOOKS = ["12-gdelt-domain-filter", "13-article-extraction", "14-gridstatus-labeling"]

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

def run_notebook_detached(nb_name, timeout=1800):
    """Run notebook via detached nohup, poll completion marker."""
    path = f"notebooks/{nb_name}.ipynb"
    out_path = f"notebooks/{nb_name}-exec.ipynb"
    marker = f"/tmp/nb_done_{nb_name}"
    logfile = f"/tmp/nb_{nb_name}.log"

    if not Path(path).exists():
        log(f"SKIP {nb_name}")
        return True

    Path(marker).unlink(missing_ok=True)

    script = f"""import sys, os, json, subprocess, time
sys.path.insert(0, "{REPO_DIR}")
os.chdir("{REPO_DIR}")
os.environ["GOOGLE_CLOUD_PROJECT"] = "project-21db66e7-39ca-4fda-b4e"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/content/gcp_adc.json"

cmd = ["jupyter", "nbconvert", "--to", "notebook", "--execute",
       "--ExecutePreprocessor.timeout={timeout}",
       "--output-dir", "notebooks",
       "--output", "{nb_name}-exec.ipynb",
       "{path}"]
result = subprocess.run(cmd, capture_output=True, text=True)
status = "OK" if result.returncode == 0 else "FAIL"
with open("{marker}", "w") as f:
    f.write(status + "\\n" + result.stdout[-500:] + "\\n" + result.stderr[-500:])
print(f"[nb_{nb_name}] {{status}}")
"""
    Path(f"/tmp/run_nb_{nb_name}.py").write_text(script)
    
    subprocess.run(
        f"nohup python3 /tmp/run_nb_{nb_name}.py > {logfile} 2>&1 &",
        shell=True, timeout=10)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if Path(marker).exists():
            result = Path(marker).read_text().strip()
            ok = result.startswith("OK")
            log(f"{'OK' if ok else 'FAIL'} {nb_name}")
            return ok
        time.sleep(10)

    log(f"TIMEOUT {nb_name} after {timeout}s")
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
    log("=== Pipeline: Remote Runner ===")
    write_env()
    clone_repo()
    install_deps()
    setup_dvc()
    if not verify_bq():
        sys.exit(1)
    results = {}
    for nb in NOTEBOOKS:
        results[nb] = run_notebook_detached(nb)
    dvc_push()
    log("\n=== SUMMARY ===")
    for nb, ok in results.items():
        log(f"  {'OK' if ok else 'FAIL'}: {nb}")
    if all(results.values()):
        log("ALL OK")
    else:
        log("SOME FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
