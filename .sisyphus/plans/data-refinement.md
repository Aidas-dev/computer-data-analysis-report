# Data Refinement Plan — HF Model Extraction on Colab

## TL;DR
> **Core**: Re-fetch full article text for 1,638 high-signal buildout events (have MW), run HuggingFace models on colab T4 16GB to extract structured fields (dedup→fetch→extract→merge).
>
> **Deliverables**:
> - Dedup cluster mapping (5,295 → ~1,000 unique announcements)
> - Full article text for ≥70% of 1,638 MW events
> - Qwen Q4 + BART extracted fields (MW, location, promise label)
> - Updated `dataset_for_ml.csv` with enriched columns → DVC push
>
> **Estimated Effort**: Medium (4-8 hours colab runtime total)
> **Parallel Execution**: YES — 2 waves
> **Critical Path**: Pilot (T0) → Dedup (T1) → Fetch (T3) → Qwen (T4) → Merge (T6)

---

## Context

### Original Request
Clean and enrich buildout event data using HuggingFace models on colab GPU. Current data: 5,295 events but all have only 200-char GDELT GKG snippets (step13 fetched 0% article text). Need full article text + structured extraction for high-value events.

### Interview Summary
**Key Decisions**:
- Refine data first, ML pipeline later
- Only process subset with MW populated (~1,638 events) — highest signal
- Use HF models on colab T4 16GB (no training, inference only)
- DVC push enriched dataset, commit changes
- `hf` CLI installed, authenticated as `Aidas-dev`

**Research Findings**:
- `sentence-transformers/all-MiniLM-L6-v2` (80M, 0.3GB) for dedup
- `facebook/bart-large-mnli` (400M, 1.6GB) for zero-shot promise labeling
- `Qwen/Qwen2.5-7B-Instruct` Q4 (7B, ~6GB) for structured extraction
- T4 16GB can hold models sequentially (load→run→unload), not simultaneously

### Metis Review
**Critical Directives**:
- MUST start with 50-URL pilot to validate URL health + fetch rate BEFORE full pipeline
- MUST have VRAM budget table — sequential model loading
- MUST include intermediate checkpoint saves after each phase
- MUST define conflict resolution: Qwen extraction vs GDELT metadata
- MUST NOT train/fine-tune any model — inference only
- MUST NOT process 3,657 non-MW events (scope boundary)

---

## Work Objectives

### Core Objective
Scale from 200-char GDELT snippets to full-article structured extraction for 1,638 high-signal buildout events using HF models on colab T4.

### Concrete Deliverables
- `notebooks/17-data-refinement.ipynb` — complete colab notebook
- `data/processed/buildout_promises_real_enriched.csv` — with full text + dedup + extracted fields
- `data/processed/dataset_for_ml_v2.csv` — rebuilt from enriched data
- Updated DVC cache + remote

### Definition of Done
- [ ] ≥70% of 1,638 URLs return >500 chars article text
- [ ] ≥80% of fetched articles have correct MW extracted (50-article holdout)
- [ ] Dedup reduces event count by ≥20%
- [ ] Promise label coverage increases from 3.2% to ≥15%
- [ ] Full pipeline completes within 12h colab session
- [ ] All datasets DVC pushed, git committed

### Must Have
- 50-URL pilot validates approach BEFORE full pipeline code
- VRAM budget plan — sequential model loading
- Checkpoint saves after each phase
- Conflict resolution: prefer GDELT metadata for MW/location, use Qwen as supplement

### Must NOT Have (Guardrails)
- No model training or fine-tuning
- No processing non-MW events (3,657 excluded)
- No UI/labeling tools (gradio, streamlit)
- No extraction beyond MW, location, company, promise label
- No manual validation of every extraction (spot-check only)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### QA Policy
- **Pilot (T0)**: Manual agent inspection of 20 random fetched articles
- **Dedup (T1)**: Agent inspects 10 nearest-neighbor pairs for sanity
- **Fetch (T3)**: Auto-count of fetch success %, article length stats
- **Extraction (T4)**: Auto-validate against 50-article holdout
- **Final (T6)**: DVC verify + git diff review

---

## Execution Strategy

### Parallel Waves

```
Wave 1 (Pilot + Setup, sequential, 1-2h):
├── T0: 50-URL pilot — validate URL health + trafilatura + Qwen quality
├── T1: Dedup — embed all 5,295 → cluster → collapse
├── T2: Create colab GPU notebook (17-data-refinement.ipynb)
└── T3: Fetch full article text for 1,638 MW events (parallel trafilatura)

Wave 2 (Extraction + Merge, sequential after fetch, 3-6h):
├── T4: Qwen Q4 structured extraction (MW, location, company)
├── T5: BART zero-shot promise classification
├── T6: Merge enriched fields → dataset_for_ml_v2.csv → DVC push
└── T7: Verify & commit

Critical Path: T0 → T1 → T2 → T3 → T4 → T5 → T6 → T7
Parallel Speedup: ~30% (fetch parallel, rest sequential)
```

### VRAM Budget (T4 16GB)

| Phase | Model | VRAM | Strategy |
|-------|-------|------|----------|
| T1 | MiniLM-L6 | ~1GB | Load → embed → unload |
| T4 | Qwen 7B Q4 | ~6GB | Load → extract → unload |
| T5 | BART-large | ~2GB | Load → classify → unload |
| — | OS + Python + data | ~3GB | Constant overhead |
| **Peak** | Qwen + OS | **~9GB** | Well within 14GB buffer |

---

## TODOs

- [x] 0. **50-URL Pilot — Validate Fetch + Extraction Quality** (integrated into scripts/refinement_pipeline.py)

  **What to do**:
  - Select 20 random URLs from each domain (datacenterdynamics, datacenterknowledge, siliconangle) — total 50 from the 1,638 MW-populated events
  - Run HEAD requests to check status codes (200/403/404/500)
  - Run trafilatura with 30s timeout per URL
  - Measure: fetch success rate, avg article length, content quality
  - If ≥70% fetch success: proceed. If <70%: investigate (blocked? paywalls? timeouts?) and adjust strategy
  - Run Qwen Q4 extraction on 5 successfully fetched articles → judge extraction quality
  - Write results to `.sisyphus/evidence/pilot-results.md`

  **Must NOT do**:
  - Do NOT skip pilot — Metis HIGH directive
  - Do NOT write full pipeline code before pilot passes

  **Agent Profile**:
  - Category: `quick`
  - Skills: `hf-cli` for model access

  **Acceptance Criteria**:
  - [ ] 50 URLs tested with HEAD and trafilatura
  - [ ] Fetch success rate documented (≥70% threshold)
  - [ ] Qwen extraction tested on 5 successful articles
  - [ ] Go/no-go decision documented

  **Evidence**: `.sisyphus/evidence/pilot-results.md`

  **Commit**: NO (pre-phase)

---

- [x] 1. **Dedup — Embed & Cluster 5,295 Buildout Events**

  **What to do**:
  - Load `data/processed/buildout_promises_real.csv` (5,295 rows)
  - Embed article text using `sentence-transformers/all-MiniLM-L6-v2`
  - Use 384-dim embeddings + cosine similarity
  - Cluster with simple threshold-based (cosine > 0.85 = same event)
  - Create `cluster_id` column — same ID = same announcement
  - Validate 10 random cluster pairs manually via agent inspection
  - **Result: 5,295 → 4,973 clusters (6.1% reduction). GKG 200-char snippets too unique for high dedup rate.**
  - Save: `data/interim/buildout_deduped.parquet` with `cluster_id` for each original row

  **Must NOT do**:
  - Do NOT tune threshold beyond 1-2 trials — pick 0.85, document, move on
  - Do NOT drop any rows — each original event keeps its cluster_id

  **References**: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2

---

- [x] 2. **Create Colab GPU Notebook — 17-data-refinement.ipynb** [CANCELLED — fetch blocked]

  **What to do**:
  - Create `notebooks/17-data-refinement.ipynb` following 06-panel-ml style
  - Sequential sections matching task order: setup → dedup → fetch → Qwen → BART → merge
  - Universal first cell (env detection, pip install: `torch transformers accelerate sentence-transformers bitsandbytes trafilatura`)
  - Colab-specific: detect T4 GPU, check VRAM, set `device_map="auto"` for Qwen
  - Each section starts with "unload model" if loaded (free memory)
  - Include HF login cell (`from huggingface_hub import login; login(token=...)` using HF_TOKEN env var)
  - Save intermediate checkpoints to `/content/drive/MyDrive/` or `/content/checkpoints/`
  - Include progress bars for all loops
  - Dry-run mode: `MAX_ARTICLES=50` env var support for testing

  **Must NOT do**:
  - Do NOT hardcode tokens — use environment variables
  - Do NOT use interactive cells (no `input()`, no widgets)
  - Do NOT add gradio/streamlit

  **References**:
  - Existing pattern: `notebooks/06-panel-ml.ipynb` for style
  - Qwen: `https://huggingface.co/Qwen/Qwen2.5-7B-Instruct` — 4-bit via bitsandbytes

  **Acceptance Criteria**:
  - [ ] All cells execute in order without errors
  - [ ] Section 1: setup + VRAM check
  - [ ] Section 2: dedup with MiniLM
  - [ ] Section 3: article fetch with trafilatura (parallel, progress bar)
  - [ ] Section 4: Qwen batch extraction
  - [ ] Section 5: BART zero-shot
  - [ ] Section 6: merge + DVC push
  - [ ] Dry-run mode works

  **Commit**: YES

---

- [x] 3. **Fetch Full Article Text — 1,638 MW Events** [CANCELLED — fetch blocked]

  **What to do**:
  - Filter `buildout_promises_real.csv` to rows where `mw_capacity` is not NaN (~1,638)
  - Run trafilatura on each URL with 30s timeout
  - ThreadPoolExecutor(10) with domain Semaphore(3) — same pattern as step13
  - Save full article text to new column `article_text_full`
  - Track: fetch success (≥500 chars), partial (100-500 chars), failed (0-100 chars)
  - Save fetch errors to `data/raw/buildout_fetch_errors_v2.csv`
  - Checkpoint: save every 200 articles to `/content/checkpoints/fetched_{batch}.parquet`

  **Must NOT do**:
  - Do NOT re-fetch all 5,295 — only MW-populated subset
  - Do NOT retry failed URLs more than 1 time

  **Dependencies**: T2 notebook must exist, T0 pilot must have validated approach

  **Acceptance Criteria**:
  - [ ] ≥70% of 1,638 URLs return >500 chars (validated in notebook summary cell)
  - [ ] Mean article length ≥ 800 chars
  - [ ] Fetch errors tracked (≤30% error rate)
  - [ ] Checkpoint saved every 200 articles
  - [ ] Total fetch time ≤ 2 hours (parallel 10 workers)

  **Commit**: NO (notebook handles this)

---

- [x] 4. **Qwen Q4 Structured Extraction — MW, Location, Company** [CANCELLED — fetch blocked]

  **What to do**:
  - Load Qwen2.5-7B-Instruct in 4-bit via `bitsandbytes` on colab T4
  - Prompt template:
    ```
    Extract fields from this data center announcement text.
    
    Article: {article_text}
    
    Return JSON:
    {
      "mw_capacity": <number or null>,
      "location_city": "<string or null>",
      "location_state": "<string or null>",
      "company": "<string or null>",
      "status": "<completed|cancelled|announced|unclear>",
      "confidence": <0-1>
    }
    ```
  - Process articles in batches of 4 (max that fits T4 VRAM at Q4)
  - 3 attempts per article on JSON parse failure (temperature 0.1)
  - Conflict resolution: prefer GDELT `mw_capacity` if within 30% of Qwen output; use Qwen if GDELT is NaN
  - Save to `data/interim/qwen_extracted.parquet`
  - Track: extraction success rate, field coverage improvement

  **Must NOT do**:
  - Do NOT fine-tune — inference only
  - Do NOT extract additional fields beyond MW, location, company, status
  - Do NOT use batch_size > 4 (OOM risk)

  **References**: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
  - 4-bit loading: `model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-7B-Instruct", load_in_4bit=True, device_map="auto")`
  - bitsandbytes: `pip install bitsandbytes`

  **Acceptance Criteria**:
  - [ ] ≥80% of fetched articles produce valid JSON extraction
  - [ ] MW extracted for ≥20% of articles where GDELT had NaN (coverage increase)
  - [ ] Location extracted for ≥20% of articles where GDELT had NaN
  - [ ] Average inference time ≤ 30s per article
  - [ ] Batch size 4 fits T4 without OOM
  - [ ] Conflict resolution applied correctly (prefer GDELT when exists)

  **Commit**: NO (notebook handles this)

---

- [x] 5. **BART Zero-Shot Promise Classification** [CANCELLED — fetch blocked]

  **What to do**:
  - Load `facebook/bart-large-mnli` in fp16 on T4
  - Hypothesis templates:
    - "This article describes a data center that was completed and is operational."
    - "This article describes a data center project that was cancelled or failed."
    - "This article describes a data center that is planned or under construction."
  - Classify all 1,638 fetched articles
  - On conflict with existing `promise_kept` (1/0): use existing label (manual > zero-shot)
  - On NaN `promise_kept`: store zero-shot result as `promise_kept_zs`
  - Save to `data/interim/bart_labels.parquet`

  **Must NOT do**:
  - Do NOT merge into original `promise_kept` — use `promise_kept_zs` suffix

  **Dependencies**: T3 must be done

  **Acceptance Criteria**:
  - [ ] All 1,638 articles classified
  - [ ] Mean confidence ≥ 0.6
  - [ ] Existing 171 manual labels preserved
  - [ ] Label coverage increases from 3.2% to ≥15%

  **Commit**: NO (notebook handles this)

---

- [x] 6. **Merge Dedup Fields → DVC Push** (partial — Qwen/BART phases blocked by pilot failure)

  **What to do**:
  - Load original `buildout_promises_real.csv` + dedup clusters
  - Merge dedup `cluster_id` on index
  - New columns: `cluster_id`, `article_text_full`, `mw_qwen`, `location_city_qwen`, `location_state_qwen`, `company_qwen`, `promise_kept_zs`, `extraction_conflict`
  - Conflict resolution: prefer GDELT metadata when present, use Qwen as supplement
  - Save: `data/processed/buildout_promises_real_enriched.csv`
  - Rebuild ML dataset: update `scripts/build_ml_dataset.py` → read from enriched → `dataset_for_ml_v2.csv`
  - DVC add + push both files
  - Update `.dvc` hashes locally

  **Must NOT do**:
  - Do NOT drop any original columns
  - Do NOT modify original `promise_kept`

  **Dependencies**: T4 + T5 done

  **Acceptance Criteria**:
  - [ ] All 5,295 rows preserved (no data loss)
  - [ ] New columns populated
  - [ ] Conflict detection flagged
  - [ ] DVC add + push succeeds

  **Commit**: YES

---

- [x] 7. **Verify & Commit**

  **What to do**:
  - `dvc status` → up to date
  - `dvc status --remote oracle_remote` → in sync
  - Enriched CSV: 5,296 lines, ≥22 columns
  - No NaN in critical columns (url, company, date)
  - Commit: `feat: data refinement — dedup (6.1% reduction) + enriched dataset`

  **Must NOT do**:
  - No build artifacts committed
  - No model binaries

  **Acceptance Criteria**:
  - [x] DVC up to date
  - [x] Git clean (pushed)
  - [x] CSV validated (5,295 rows × 19 cols)

  **Commit**: b96bc3e

---

## Final Verification

- [x] F1: Enriched CSV — 5,296 lines ✓ (19 cols — blocked phases prevented additional columns)
- [x] F2: DVC push verified — remote in sync ✓
- [x] F3: BART coverage — N/A (blocked by fetch failure)
- [x] F4: Qwen coverage — N/A (blocked by fetch failure)

## Blocker: URL Fetch Not Viable

**Pilot (Phase 0) Result**: 25% fetch success from datacenterdynamics.com and datacenterknowledge.com — domains heavily block/paywall trafilatura.

**Blocked Tasks**:
- ~~T2: Colab GPU notebook~~ — no point without viable fetch
- ~~T3: Full article fetch~~ — 75% URLs unreachable
- ~~T4: Qwen Q4 extraction~~ — needs article text input
- ~~T5: BART zero-shot~~ — needs article text input

**What did complete**:
- T0: Pilot — documented results at `.sisyphus/evidence/pilot-results.md`
- T1: Dedup — 5,295 → 4,973 clusters (6.1% reduction), MiniLM-L6 on colab
- T6: Merge — `buildout_promises_real_enriched.csv` with `cluster_id` column → DVC pushed
- T7: Verify & commit (b96bc3e)

**Current data quality**: 31% MW, 42% location, 3.2% labels — no improvement possible without full article access.

## Commit Strategy
- **T2**: `feat: create 17-data-refinement colab GPU notebook`
- **T6**: `feat: enrich buildout events dataset with HF extraction`
- **T7**: `feat: finalize enriched dataset with DVC push`

## Success Criteria

```bash
wc -l data/processed/buildout_promises_real_enriched.csv  # 5296
dvc status                                                 # Up to date
dvc status --remote oracle_remote                          # In sync
git status --short                                         # Clean
```

- [ ] ≥70% fetch rate for 1,638 MW URLs
- [ ] ≥20% dedup reduction
- [ ] Promise label coverage ≥15%
- [ ] All 5,295 rows preserved
- [ ] DVC remote in sync
- [ ] Git committed

