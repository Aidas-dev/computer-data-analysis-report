# Pilot Results — URL Fetch Quality Validation

**Date**: 2026-05-24
**Colab Session**: data-refinement (T4 GPU)
**Pipeline**: scripts/refinement_pipeline.py (Phase 0 integrated pilot)

## Method
- Selected 40 random URLs from 1,638 MW-populated buildout events
- Source domains: datacenterdynamics.com, datacenterknowledge.com
- Fetched via trafilatura with 30s timeout

## Results
| Metric | Value |
|--------|-------|
| Total URLs tested | 40 |
| Successful fetches (>500 chars) | 10 |
| Failed/blocked/paywalled | 30 |
| Fetch success rate | **25.0%** |
| Threshold (required) | **≥70%** |
| Verdict | **FAIL — Aborted** |

## Analysis
- Most datacenterdynamics.com and datacenterknowledge.com URLs return paywall/gate content
- trafilatura cannot bypass these — static HTTP fetch only
- GDELT GKG snippets (200 chars) are the only reliable source of text content
- Pipeline's Phase 0 correctly detected the failure and aborted per design

## Decision
- **Fetch phase (T3) is blocked** — cannot get full article text for ≥70% of URLs
- **Dedup (T1) can proceed** — works on 200-char snippets, no fetch needed
- **Qwen (T4) blocked** — needs full article text input
- **BART (T5) blocked** — needs article text for classification
- **Estimation**: Only ~10-15% of URL pool is accessible via static fetch

## Recommendation
1. Proceed with T1 (dedup) — works on existing data
2. For Qwen/BART: either skip extraction entirely or use GDELT metadata as-is
3. Accept current data quality: 31% MW, 42% location, 3.2% labels
4. Full-article enrichment is not viable for these datacenter-domains
