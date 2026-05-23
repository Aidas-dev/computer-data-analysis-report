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
TIMEOUT = 7200  # 2hr max for full pipeline

# ── Secrets (inlined for self-contained deploy) ────────────────────────
CENSUS_API_KEY = "e8afaf7cff13d0d152e32bf98c0ac244c63db787"
FRED_API_KEY = "4aeb77367579a1c44a91f61ed6b991fe"
OCI_ACCESS_KEY = "542d2f34b5d73eb0b89705355f1ec6f4a0f4b44e"
OCI_SECRET_KEY = "ps/7lxHnEmGMoPK4EwYtRmpVOXqPbTK7qOkJpY791/k="
GCP_ADC_B64 = "ewogICJhY2NvdW50IjogIiIsCiAgImNsaWVudF9pZCI6ICI3NjQwODYwNTE4NTAtNnFyNHA2Z3BpNmhuNTA2cHQ4ZWp1cTgzZGkzNDFodXIuYXBwcy5nb29nbGV1c2VyY29udGVudC5jb20iLAogICJjbGllbnRfc2VjcmV0IjogImQtRkw5NVExOXE3TVFtRnBkN2hIRDBUeSIsCiAgInF1b3RhX3Byb2plY3RfaWQiOiAicHJvamVjdC0yMWRiNjZlNy0zOWNhLTRmZGEtYjRlIiwKICAicmVmcmVzaF90b2tlbiI6ICIxLy8wY2pXa1c0SnZSSlhkQ2dZSUFSQUFHQXdTTndGLUw5SXIzSzY3Y054UkRXWTdxVnA2ODlqVFBtQVM3bHFEeXBuNHdSYzVNNFFieUhVcHFaa25yM0doWGJ4RDJLc3JxUmh5Vkp3IiwKICAidHlwZSI6ICJhdXRob3JpemVkX3VzZXIiLAogICJ1bml2ZXJzZV9kb21haW4iOiAiZ29vZ2xlYXBpcy5jb20iCn0="

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
        if line and line not in ("NONE",):
            return line
    return "NONE"

# ── Main ───────────────────────────────────────────────────────────────
def main():
    # 1. Kill any old session, create fresh
    log("=== Phase 1: Create colab session ===")
    sh(f"colab stop -s {SESSION} 2>/dev/null", timeout=10)
    time.sleep(2)
    sh(f"colab new -s {SESSION}", timeout=60)

    # 2. Build setup + launch script
    log("=== Phase 2: Write setup+launch script ===")
    launch_code = f"""#!/usr/bin/env python3
'''Run on colab VM. Sets up env, writes runner, launches pipeline in bg.'''
import base64, os, subprocess, sys, time
from pathlib import Path

os.chdir("/content")

# Write secrets
Path("/content/.env").write_text(
    "CENSUS_API_KEY={ck}\\nFRED_API_KEY={fk}\\nOCI_ACCESS_KEY={ok}\\nOCI_SECRET_KEY={sk}\\n"
)
Path("/content/gcp_adc.json").write_bytes(base64.b64decode("{gcp}"))
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/content/gcp_adc.json"
os.environ["GOOGLE_CLOUD_PROJECT"] = "project-21db66e7-39ca-4fda-b4e"

# Clone
r = subprocess.run(f"git clone --depth 1 https://github.com/Aidas-dev/computer-data-analysis-report.git {rdir}",
                   shell=True, timeout=120)
if r.returncode != 0:
    print("CLONE_FAILED", flush=True); sys.exit(1)
os.chdir("{rdir}")

# Install deps
subprocess.run("pip install uv -q", shell=True, timeout=30)
subprocess.run("uv pip install --system -r requirements.txt -q", shell=True, timeout=300)
subprocess.run("uv pip install --system newspaper3k lxml_html_clean trafilatura gridstatus -q",
               shell=True, timeout=120)

# DVC setup
subprocess.run("dvc remote modify --local oracle_remote access_key_id '{ok}'", shell=True)
subprocess.run("dvc remote modify --local oracle_remote secret_access_key '{sk}'", shell=True)
subprocess.run("dvc pull -q", shell=True, timeout=300)

# Write pipeline runner
runner_script = '''#!/usr/bin/env python3
import subprocess, os, sys
MARKER = "/tmp/pipeline_status"
LOG = "/tmp/pipeline_output.log"
RD = "{rdir}"

def run_step(num):
    with open(MARKER, "w") as f: f.write(f"step{{num}}_starting")
    print(f"=== STEP {{num}} ===", flush=True)
    with open(LOG, "a") as logf:
        r = subprocess.run(
            ["python3", "-u", f"scripts/pipeline_step{{num}}.py"],
            cwd=RD, timeout=1800,
            stdout=logf, stderr=subprocess.STDOUT
        )
    if r.returncode != 0:
        with open(MARKER, "w") as f: f.write(f"step{{num}}_FAILED")
        return False
    subprocess.run(["cp", f"{RD}/data/processed/buildout_promises_real.csv.dvc",
                    "/tmp/buildout_promises_real.csv.dvc"], capture_output=True)
    subprocess.run(["cp", f"{RD}/data/raw/buildout_candidates_gkg.csv.dvc",
                    "/tmp/buildout_candidates_gkg.csv.dvc"], capture_output=True)
    subprocess.run(["cp", f"{RD}/data/raw/buildout_events_raw.csv.dvc",
                    "/tmp/buildout_events_raw.csv.dvc"], capture_output=True)
    with open(MARKER, "w") as f: f.write(f"step{{num}}_done")
    return True

# Run steps sequentially
for s in [12, 13, 14]:
    if not run_step(s):
        with open(MARKER, "w") as f: f.write(f"FAILED_at_step{{s}}")
        sys.exit(1)

# DVC push all
with open(MARKER, "w") as f: f.write("pushing")
subprocess.run(["dvc", "push"], cwd=RD, timeout=600)
with open(MARKER, "w") as f: f.write("ALL_DONE")
print("=== PIPELINE COMPLETE ===", flush=True)
'''

Path("/tmp/run_pipeline.py").write_text(runner_script)
Path("/tmp/pipeline_output.log").write_text("")

# Launch pipeline in background via nohup (shell, not kernel)
subprocess.Popen(
    ["nohup", "python3", "-u", "/tmp/run_pipeline.py"],
    stdout=open("/tmp/nohup_stdout.log", "w"),
    stderr=subprocess.STDOUT,
    preexec_fn=os.setpgrp  # detach from process group
)

print("LAUNCHED", flush=True)
time.sleep(2)
print(open("/tmp/pipeline_status").read() if Path("/tmp/pipeline_status").exists() else "starting", flush=True)
"""

    launch_code = launch_code.format(
        ck=CENSUS_API_KEY, fk=FRED_API_KEY,
        ok=OCI_ACCESS_KEY, sk=OCI_SECRET_KEY,
        gcp=GCP_ADC_B64, rdir=REPO_DIR
    )

    launcher_path = "/tmp/_colab_launch.py"
    Path(launcher_path).write_text(launch_code)

    # 3. Execute launch script on colab (fast — just setup + Popen)
    log("=== Phase 3: Launch on colab ===")
    sh(f"colab exec -s {SESSION} -f {launcher_path}", timeout=180)

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
                if ln and ln not in ("N/A",):
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
