# Data Refinement — Learnings

## 2026-05-24

### Pilot Result: URL Fetch Blocked
- datacenterdynamics.com and datacenterknowledge.com paywall/block trafilatura
- Only 25% of URLs return >500 chars of article text
- GDELT GKG 200-char snippets are the only reliable text source for these domains
- Pipeline's Phase 0 correctly detected failure and aborted

### Dedup: MiniLM-L6 on colab
- Threshold 0.85 → 6.1% reduction (5,295 → 4,973 clusters)
- GKG 200-char snippets are too unique for aggressive dedup
- Each snippet is a different headline/summary of distinct datacenter news
- Real reduction likely higher if full article text were available
- DVC pushed successfully with botocore fix locally

### Colab T4 GPU Pipeline
- `colab run` KeepAlive fails with 403 on this GCP project (colab.pa.googleapis.com not enabled)
- Session stays alive for a while but no persistent KeepAlive
- Workaround: use `colab exec` for interactive commands on existing session
- 3.3MB parquet file transfer via base64 stdout works fine

### DVC Oracle S3 Remote
- Content-Length header error on colab (botocore version issue)
- Fixed locally with `botocore<1.36.0` pin
- Not fixable on colab due to aiobotocore conflict
- Workaround: download files and DVC push locally
