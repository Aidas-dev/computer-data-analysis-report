# Draft: colab run deployment

## Goal
Replace fragile nohup+nbconvert pipeline deploy with `colab run` approach.

## Changes in progress
1. **step13.py** → ThreadPoolExecutor(10) parallel fetch + URL pre-filtering (priority sorting). Target <30min for 18K URLs.
2. **deploy_to_colab.sh** → generates self-contained Python runner with inlined secrets (base64 JSON), calls `colab run -s pipeline-run`

## Secrets approach
- Generate runner script at deploy time with secrets embedded as base64 JSON
- Runner decodes at startup, sets env vars, clones repo, installs deps, runs steps
- This avoids colab run not supporting --env flags

## Queue
After deploy: step12→step13→step14 on colab
Then: DVC pull local, tasks 7-14 (merge pipeline, EDA, event study, paper)
