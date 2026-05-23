"""
Phase 1: setup env + clone + deps + DVC
Phase 2: run census notebook in background
"""
import os, subprocess, sys, time

def log(m):
    print(f"[deploy] {m}", flush=True)

def run(cmd, timeout=600):
    log(f"$ {cmd[:120]}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        log(f"RC={r.returncode}: {r.stderr[-200:]}")
    return r

phase = sys.argv[1] if len(sys.argv) > 1 else "all"

# --- PHASE 1: Setup .env ---
if phase in ("all", "env"):
    log("Writing /content/.env with credentials...")
    open("/content/.env", "w").write("""AWS_ACCESS_KEY_ID=542d2f34b5d73eb0b89705355f1ec6f4a0f4b44e
AWS_SECRET_ACCESS_KEY=ps/7lxHnEmGMoPK4EwYtRmpVOXqPbTK7qOkJpY791/k=
CENSUS_API_KEY=e8afaf7cff13d0d152e32bf98c0ac244c63db787
FRED_API_KEY=4aeb77367579a1c44a91f61ed6b991fe
""")
    os.chdir("/content")
    log("env written OK")

# --- PHASE 2: Clone + deps + DVC ---
if phase in ("all", "setup"):
    r = run("git clone --depth 1 https://github.com/Aidas-dev/computer-data-analysis-report.git", 120)
    os.chdir("/content/computer-data-analysis-report")
    run("pip install uv -q", 30)
    run("uv pip install --system -r requirements.txt -q", 300)
    key_id = "542d2f34b5d73eb0b89705355f1ec6f4a0f4b44e"
    secret = "ps/7lxHnEmGMoPK4EwYtRmpVOXqPbTK7qOkJpY791/k="
    run(f'dvc remote modify --local oracle_remote access_key_id "{key_id}"')
    run(f'dvc remote modify --local oracle_remote secret_access_key "{secret}"')
    run("dvc pull -q", 300)
    log("SETUP COMPLETE")

# --- PHASE 3: Background runner for census ---
if phase in ("all", "census"):
    os.chdir("/content/computer-data-analysis-report")
    runner = """#!/usr/bin/env python3
import subprocess, os
os.chdir("/content/computer-data-analysis-report")
log = open("/content/notebook_results.txt", "w")
log.write("census: STARTING\\n")
log.flush()
r = subprocess.run([
    "jupyter", "nbconvert", "--to", "notebook", "--execute",
    "--ExecutePreprocessor.timeout=1200",
    "--output-dir", "notebooks",
    "--output", "08-census-data-exec.ipynb",
    "notebooks/08-census-data.ipynb"
], capture_output=True, text=True, timeout=1300)
ok = r.returncode == 0
log.write(f"census: {'OK' if ok else 'FAIL'}\\n")
if not ok:
    log.write(f"stderr: {r.stderr[-500:]}\\n")
log.flush()
log.close()
"""
    open("/content/run_census.py", "w").write(runner)
    import signal
    p = subprocess.Popen(["python3", "/content/run_census.py"],
        preexec_fn=lambda: os.setpgrp(),
        stdout=open("/content/census_out.log", "w"), stderr=subprocess.STDOUT)
    log(f"Census launched as background PID {p.pid}")
    print(f"CENSUS_PID={p.pid}")
