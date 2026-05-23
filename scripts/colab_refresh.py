#!/usr/bin/env python3
"""
colab_refresh.py — Repeatable Colab environment setup + data pipeline runner.

Usage:
  colab new -s data-analysis
  colab auth -s data-analysis
  colab exec -s data-analysis -f scripts/colab_refresh.py

Environment variables (set on VM before run, or in .env):
  OCI_ACCESS_KEY, OCI_SECRET_KEY — Oracle S3-compat DVC remote
  CENSUS_API_KEY                 — US Census Bureau API
  FRED_API_KEY                   — FRED economic data API
"""

import os, subprocess, sys, time, json, shutil
from pathlib import Path

REPO = "https://github.com/Aidas-dev/computer-data-analysis-report.git"
REPO_DIR = "/content/computer-data-analysis-report"
DOTENV = "/content/.env"

def log(msg):
    print(f"[colab-refresh] {msg}", flush=True)

def run(cmd, *, check=True, timeout=300, capture=False, env=None):
    log(f"$ {cmd[:120]}")
    kwargs = {"capture_output": capture, "text": True}
    if env:
        kwargs["env"] = {**os.environ, **env}
    r = subprocess.run(cmd, shell=True, timeout=timeout, **kwargs)
    if check and r.returncode != 0:
        log(f"FAIL (rc={r.returncode}): {cmd[:100]}")
        if capture:
            log(f"stderr: {r.stderr[-300:]}")
        raise RuntimeError(f"Command failed: {cmd[:100]}")
    return r

def load_dotenv():
    """Load .env file if present."""
    env_file = Path(DOTENV)
    if env_file.exists():
        log(f"Loading {DOTENV}")
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

def setup_repo():
    """Clone or pull the repo."""
    if not Path(REPO_DIR).exists():
        log("Cloning repo...")
        run(f"git clone --depth 1 {REPO} {REPO_DIR}", timeout=120)
    else:
        log("Pulling latest...")
        run(f"git -C {REPO_DIR} pull --ff-only", timeout=60)
    os.chdir(REPO_DIR)

def install_deps():
    """Install Python dependencies via uv."""
    log("Installing uv...")
    run("pip install uv -q", timeout=30)
    log("Installing deps...")
    run("uv pip install --system -r requirements.txt -q", timeout=300)
    log("Deps installed.")

def setup_dvc():
    """Configure DVC remote and pull data."""
    key_id = os.environ.get("OCI_ACCESS_KEY", "")
    secret = os.environ.get("OCI_SECRET_KEY", "")
    if not key_id or not secret:
        log("WARN: OCI_ACCESS_KEY / OCI_SECRET_KEY not set. Skipping DVC.")
        return False
    log("Configuring DVC remote...")
    run(f"dvc remote modify --local oracle_remote access_key_id '{key_id}'")
    run(f"dvc remote modify --local oracle_remote secret_access_key '{secret}'")
    log("Pulling DVC data...")
    run("dvc pull -q", timeout=300)
    log("DVC pull complete.")
    return True

def run_notebook(nb_name, timeout=600):
    """Execute a notebook via nbconvert, return True if OK."""
    path = f"notebooks/{nb_name}.ipynb"
    outname = f"{nb_name}-exec.ipynb"
    if not Path(path).exists():
        log(f"SKIP {nb_name}: notebook not found")
        return False
    log(f"RUN {nb_name}...")
    try:
        r = run(
            f"jupyter nbconvert --to notebook --execute "
            f"--ExecutePreprocessor.timeout={timeout} "
            f"--output-dir notebooks --output {outname} {path}",
            timeout=timeout + 30, capture=True
        )
        ok = r.returncode == 0
        log(f"{'OK' if ok else 'FAIL'} {nb_name}")
        return ok
    except Exception as e:
        log(f"EXCEPTION {nb_name}: {e}")
        return False

def main():
    load_dotenv()

    step = sys.argv[1] if len(sys.argv) > 1 else "all"

    if step in ("all", "setup"):
        setup_repo()
        install_deps()
        setup_dvc()

    if step in ("all", "census"):
        log("=== Running 08-census-data ===")
        ok = run_notebook("08-census-data", timeout=900)
        if ok:
            log("Census notebook OK. DVC pushing...")
            run("dvc push data/raw/census_demographics.csv.dvc", timeout=120)
            run("dvc push data/raw/census_counties.csv.dvc", timeout=120)
            log("Census data pushed to DVC.")
        else:
            log("WARN: census notebook failed. Check logs.")

    if step in ("all", "financial"):
        log("=== Running 01-data-extraction ===")
        run_notebook("01-data-extraction", timeout=900)
        run("dvc push", timeout=300)

    if step in ("all", "features"):
        for nb in ("03-data-merging", "04-quarterly-panel", "05-timeseries-features"):
            run_notebook(nb, timeout=600)
        run("dvc push", timeout=300)

    log("DONE.")

if __name__ == "__main__":
    main()
