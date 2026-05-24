#!/bin/bash
set -e

# =============================================================================
# deploy_wayback.sh
#
# Deploys and runs the Wayback Machine article fetch pipeline on Google Colab.
# Uses colab CLI to create an ephemeral session, clone repo, install deps,
# DVC-pull input data, and launch pipeline_step15_wayback.py via nohup.
#
# Usage:
#   ./deploy_wayback.sh
#
# Prerequisites:
#   - colab CLI installed (pip install colab-cli)
#   - DVC remote credentials configured locally
#     (dvc remote modify --local oracle_remote access_key_id/secret_access_key)
# =============================================================================

echo "=== Deploy Wayback Pipeline to Colab ==="

step_good=0
step_fail=0

run_step() {
  local desc="$1"
  shift
  echo ""
  echo "--- $desc ---"
  if "$@" 2>&1; then
    echo "[OK] $desc"
    step_good=$((step_good + 1))
  else
    echo "[FAIL] $desc (continuing)"
    step_fail=$((step_fail + 1))
  fi
}

# 1. Create colab session
run_step "Creating colab session: wayback-fetch" \
  colab new -s wayback-fetch

# 2. Clone repo
run_step "Cloning repository" \
  bash -c 'echo "cd /content && git clone https://github.com/Aidas-dev/computer-data-analysis-report.git repo 2>&1 | tail -5" | colab console -s wayback-fetch'

# 3. Install Python deps
run_step "Installing Python dependencies" \
  bash -c 'echo "cd /content/repo && pip install -q trafilatura lxml requests tqdm pandas '\''dvc[s3]'\''" | colab console -s wayback-fetch'

# 4. DVC pull input data
run_step "DVC pulling input data" \
  bash -c 'echo "cd /content/repo && dvc pull data/processed/buildout_promises_real.csv.dvc 2>&1" | colab console -s wayback-fetch'

# 5. Write runner.py and launch via nohup
echo ""
echo "--- Writing runner.py and launching pipeline ---"
runner_cmd=$(cat << 'RUNNER_SCRIPT'
cat > /content/repo/runner.py << 'PYEOF'
import subprocess, sys, os, time
start = time.time()
result = subprocess.run([sys.executable, 'scripts/pipeline_step15_wayback.py'], capture_output=True, text=True, cwd='/content/repo')
elapsed = time.time() - start
with open('/tmp/pipeline_done', 'w') as f:
    f.write(f'rc={result.returncode}\nstdout={result.stdout[-500:]}\nstderr={result.stderr[-500:]}\nelapsed={elapsed:.0f}s')
print('DONE', result.returncode, f'{elapsed:.0f}s')
PYEOF
RUNNER_SCRIPT
)
if echo "$runner_cmd" | colab console -s wayback-fetch 2>&1; then
  echo "[OK] runner.py written"
  step_good=$((step_good + 1))
else
  echo "[FAIL] runner.py write (continuing)"
  step_fail=$((step_fail + 1))
fi

launch_cmd="cd /content/repo && nohup python3 runner.py > /tmp/pipeline.log 2>&1 & echo 'PID: '\$!"
if echo "$launch_cmd" | colab console -s wayback-fetch 2>&1; then
  echo "[OK] Pipeline launched in background"
  step_good=$((step_good + 1))
else
  echo "[FAIL] Pipeline launch (continuing)"
  step_fail=$((step_fail + 1))
fi

# 6. Verify it's running
run_step "Verifying pipeline is running" \
  bash -c 'echo "ps aux | grep runner" | colab console -s wayback-fetch'

# 7. Print monitoring instructions
echo ""
echo "============================================"
echo " Deploy complete: $step_good OK, $step_fail fail(s)"
echo "============================================"
echo ""
echo "--- Monitoring Instructions ---"
echo ""
echo "Check checkpoint count:"
echo '  echo "ls /tmp/wayback_ckpt_*.csv 2>/dev/null | wc -l" | colab console -s wayback-fetch'
echo ""
echo "Check done marker:"
echo '  echo "cat /tmp/pipeline_done 2>/dev/null || echo '\''Still running'\''" | colab console -s wayback-fetch'
echo ""
echo "Check log tail:"
echo '  echo "tail -20 /tmp/pipeline.log 2>/dev/null" | colab console -s wayback-fetch'
echo ""
echo "Stream logs live:"
echo '  echo "tail -f /tmp/pipeline.log" | colab console -s wayback-fetch &'
echo ""
