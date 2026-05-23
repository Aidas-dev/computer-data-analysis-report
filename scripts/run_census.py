#!/usr/bin/env python3
import subprocess, os

os.chdir("/content/computer-data-analysis-report")
log = open("/content/notebook_results.txt", "w")
log.write("census: STARTING\n")
log.flush()

r = subprocess.run(
    ["jupyter", "nbconvert", "--to", "notebook", "--execute",
     "--ExecutePreprocessor.timeout=1200",
     "--output-dir", "notebooks",
     "--output", "08-census-data-exec.ipynb",
     "notebooks/08-census-data.ipynb"],
    capture_output=True, text=True, timeout=1300)

ok = r.returncode == 0
status = "OK" if ok else "FAIL"
log.write(f"census: {status}\n")
if not ok:
    log.write(f"stderr: {r.stderr[-1000:]}\n")
log.flush()
log.close()
print(f"census: {status}", flush=True)
