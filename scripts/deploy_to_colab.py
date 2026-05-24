#!/usr/bin/env python3
"""deploy_to_colab.py — Run on LOCAL machine. Orchestrates pipeline on colab.

Strategy:
  colab exec — fast setup (clone, install, DVC pull, write runner)
  colab console — launch pipeline in background via nohup
  colab exec — poll for completion (marker file, fast)
  colab stop — cleanup

This avoids Jupyter kernel timeouts by running the pipeline via shell (console),
not through the kernel (exec).
"""

import base64, os, subprocess, sys, time
from pathlib import Path

SESSION = "buildout-pipeline"
REPO_DIR = "/content/computer-data-analysis-report"
TIMEOUT = 14400

# ── Secrets (read from env vars) ───────────────────────────────────────
CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY")
FRED_API_KEY = os.environ.get("FRED_API_KEY")
OCI_ACCESS_KEY = os.environ.get("OCI_ACCESS_KEY")
OCI_SECRET_KEY = os.environ.get("OCI_SECRET_KEY")
GCP_ADC_B64 = os.environ.get("GCP_ADC_B64")

REQUIRED_ENV_VARS = ["CENSUS_API_KEY", "FRED_API_KEY", "OCI_ACCESS_KEY", "OCI_SECRET_KEY", "GCP_ADC_B64"]


def validate_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        print(f"[deploy] FATAL: Missing required env vars: {', '.join(missing)}", flush=True)
        print(f"[deploy] Set them before running, e.g.:", flush=True)
        print(f"[deploy]   export CENSUS_API_KEY=... FRED_API_KEY=... OCI_ACCESS_KEY=... OCI_SECRET_KEY=... GCP_ADC_B64=...", flush=True)
        sys.exit(1)
    log("All required env vars found.")

# ── Helpers ────────────────────────────────────────────────────────────
def log(msg):
    print(f"[deploy] {msg}", flush=True)

def sh(cmd, timeout=300, capture=True):
    log(f"$ {cmd}")
    kwargs = dict(shell=True, timeout=timeout)
    if capture:
        kwargs.update(capture_output=True, text=True)
    r = subprocess.run(cmd, **kwargs)
    if capture:
        for line in r.stdout.strip().split("\n")[-15:]:
            if line.strip():
                print(f"  {line}")
        if r.returncode != 0:
            for line in r.stderr.strip().split("\n")[-5:]:
                if line.strip():
                    print(f"  ERR: {line}")
            raise RuntimeError(f"FAIL (rc={r.returncode})")
    return r

def poll_status():
    """Quick colab exec to check marker file."""
    code = "import os; p='/tmp/pipeline_status'; print(open(p).read().strip() if os.path.exists(p) else 'NONE')"
    r = subprocess.run(
        ["colab", "exec", "-s", SESSION, "-e", code],
        capture_output=True, text=True, timeout=30
    )
    for line in r.stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("[colab]"):
            continue
        if line == "NONE":
            return "NONE"
        return line
    return "NONE"

# ── Main ───────────────────────────────────────────────────────────────
def main():
    validate_env()

    # 1. Kill any old session, create fresh
    log("=== Phase 1: Create colab session ===")
    sh(f"colab stop -s {SESSION} 2>/dev/null", timeout=10)
    time.sleep(2)
    sh(f"colab new -s {SESSION}", timeout=60)

    # 2. Build setup + launch script
    log("=== Phase 2: Write setup+launch script ===")
    # ── Runner script: does ALL work via nohup (no kernel timeout) ────
    runner_script = """#!/usr/bin/env python3
'''Runs on colab via nohup. Setup → pipeline → DVC push. No kernel dependency.'''
import base64, os, subprocess, sys, time
from pathlib import Path

MARKER = "/tmp/pipeline_status"
LOG = "/tmp/pipeline_output.log"
RD = "/content/computer-data-analysis-report"

def write_marker(msg):
    with open(MARKER, "w") as f: f.write(msg)

def log(msg):
    with open(LOG, "a") as f: f.write(f"[{{time.time():.0f}}] {msg}\\n")

# ── Phase A: Setup ──
os.chdir("/content")

# Secrets
Path("/content/.env").write_text(
    f"CENSUS_API_KEY={os.environ.get('CENSUS_API_KEY', '')}\\n"
    f"FRED_API_KEY={os.environ.get('FRED_API_KEY', '')}\\n"
    f"OCI_ACCESS_KEY={os.environ.get('OCI_ACCESS_KEY', '')}\\n"
    f"OCI_SECRET_KEY={os.environ.get('OCI_SECRET_KEY', '')}\\n"
)
gcp_b64 = os.environ.get("GCP_ADC_B64", "")
Path("/content/gcp_adc.json").write_bytes(base64.b64decode(gcp_b64))

# Clone
if not Path(RD).exists():
    r = subprocess.run(
        ["git", "clone", "--depth", "1",
         "https://github.com/Aidas-dev/computer-data-analysis-report.git", RD],
        capture_output=True, text=True, timeout=120
    )
    if r.returncode != 0:
        write_marker("SETUP_FAILED:clone")
        log(f"Clone failed: {{r.stderr[:200]}}")
        sys.exit(1)
    log("Clone OK")

# Install deps (first run only)
os.chdir(RD)
subprocess.run("pip install uv -q", shell=True, timeout=30)
log("uv installed")
subprocess.run("uv pip install --system -r requirements.txt -q", shell=True, timeout=300)
subprocess.run("uv pip install --system newspaper3k lxml_html_clean trafilatura gridstatus -q",
               shell=True, timeout=120)
log("Deps installed")

# DVC pull
os.environ["AWS_ACCESS_KEY_ID"] = os.environ.get("OCI_ACCESS_KEY", "")
os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ.get("OCI_SECRET_KEY", "")
subprocess.run(["dvc", "remote", "modify", "--local", "oracle_remote",
                "access_key_id", os.environ["AWS_ACCESS_KEY_ID"]], capture_output=True)
subprocess.run(["dvc", "remote", "modify", "--local", "oracle_remote",
                "secret_access_key", os.environ["AWS_SECRET_ACCESS_KEY"]], capture_output=True)
subprocess.run("dvc pull -q", shell=True, timeout=300)
log("DVC pull OK")

# ── Phase B: Pipeline steps ──
def run_step(num):
    write_marker(f"step{num}_starting")
    log(f"Step {num} starting")
    with open(LOG, "a") as logf:
        r = subprocess.run(
            ["python3", "-u", f"scripts/pipeline_step{num}.py"],
            cwd=RD, timeout=3600,
            stdout=logf, stderr=subprocess.STDOUT
        )
    if r.returncode != 0:
        write_marker(f"step{num}_FAILED")
        log(f"Step {num} FAILED rc={{r.returncode}}")
        return False
    write_marker(f"step{num}_done")
    log(f"Step {num} OK")
    return True

for s in [12, 13, 14]:
    if not run_step(s):
        write_marker(f"FAILED_at_step{s}")
        sys.exit(1)

# ── Phase C: DVC push ──
write_marker("pushing")
subprocess.run(["dvc", "push"], cwd=RD, timeout=600)
write_marker("ALL_DONE")
log("Pipeline complete!")
"""

    # Encode runner as base64 for inline embedding in launch script
    runner_b64 = base64.b64encode(runner_script.encode()).decode()

    log("=== Phase 3: Upload + launch runner (via colab exec -f) ===")
    launch_code = f"""#!/usr/bin/env python3
import base64, os, subprocess, sys, time
RD = "{REPO_DIR}"

# Clone
r = subprocess.run(["git", "clone", "--depth", "1",
    "https://github.com/Aidas-dev/computer-data-analysis-report.git", RD],
    capture_output=True, text=True, timeout=120)
if r.returncode != 0:
    print(f"CLONE_FAIL:{{r.stderr[:200]}}", flush=True); sys.exit(1)
print("CLONE_OK", flush=True)

# Set env vars for runner (values injected from deploy-time env vars)
os.environ["CENSUS_API_KEY"] = "{CENSUS_API_KEY}"
os.environ["FRED_API_KEY"] = "{FRED_API_KEY}"
os.environ["OCI_ACCESS_KEY"] = "{OCI_ACCESS_KEY}"
os.environ["OCI_SECRET_KEY"] = "{OCI_SECRET_KEY}"
os.environ["GCP_ADC_B64"] = "{GCP_ADC_B64}"

# Decode and write runner
runner_py = base64.b64decode("{runner_b64}").decode()
Path(RD).mkdir(parents=True, exist_ok=True)
open("/tmp/run_pipeline.py", "w").write(runner_py)

# Launch via nohup
subprocess.Popen(["nohup", "python3", "-u", "/tmp/run_pipeline.py"],
    stdout=open("/tmp/nohup_stdout.log", "w"),
    stderr=subprocess.STDOUT,
    preexec_fn=os.setpgrp)
print("LAUNCHED", flush=True)
"""
    launcher_path = "/tmp/_colab_launch.py"
    Path(launcher_path).write_text(launch_code)
    sh(f"colab exec -s {SESSION} -f {launcher_path}", timeout=120)

    # 4. Poll for completion
    log("=== Phase 4: Poll for completion ===")
    start = time.time()
    last_status = ""
    while time.time() - start < TIMEOUT:
        status = poll_status()
        if status != last_status:
            log(f"Status: {status}")
            last_status = status
            # Also show log tail
            r = subprocess.run(
                ["colab", "exec", "-s", SESSION, "-e",
                 "import os; p='/tmp/pipeline_output.log'; print(open(p).read()[-1000:] if os.path.exists(p) else 'N/A')"],
                capture_output=True, text=True, timeout=30
            )
            for ln in r.stdout.strip().split("\n"):
                ln = ln.strip()
                if not ln or ln.startswith("[colab]") or ln == "N/A":
                    continue
                print(f"  {ln[:200]}")
        if status in ("ALL_DONE",):
            log("Pipeline complete!")
            break
        if status.startswith("FAILED"):
            log(f"Pipeline FAILED: {status}")
            break
        time.sleep(15)

    elapsed = time.time() - start
    log(f"Elapsed: {elapsed:.0f}s")

    log("=== Phase 5: Sync .dvc files ===")
    dvc_files = [
        "data/raw/buildout_candidates_gkg.csv.dvc",
        "data/raw/buildout_events_raw.csv.dvc",
        "data/processed/buildout_promises_real.csv.dvc",
    ]
    repo_root = Path(__file__).resolve().parent.parent
    for f in dvc_files:
        r = subprocess.run(
            ["colab", "exec", "-s", SESSION, "-e",
             f"import os; p='{REPO_DIR}/{f}'; print(open(p).read() if os.path.exists(p) else 'MISSING')"],
            capture_output=True, text=True, timeout=30
        )
        lines = [ln.strip() for ln in r.stdout.strip().split("\n") if ln.strip() and ln.strip() != "MISSING"]
        if lines:
            (repo_root / f).write_text("\n".join(lines) + "\n")
            log(f"  Synced {f}")

    log("=== Phase 6: Stop session ===")
    sh(f"colab stop -s {SESSION}", timeout=10)

    log("=== Final status ===")
    status = "N/A"
    log(f"Final status: {status}")

    if last_status != "ALL_DONE":
        log("Pipeline did not complete successfully")
        sys.exit(1)

    log("=== DEPLOY COMPLETE ===")


if __name__ == "__main__":
    main()
