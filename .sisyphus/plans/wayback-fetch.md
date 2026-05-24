# Wayback Machine Article Fetch — Full Text Extraction

## TL;DR
> **Core**: Fetch full article text for 5,295 buildout events via Wayback Machine archive, extract with trafilatura, save as enriched CSV, DVC push.
>
> **Deliverables**:
> - `scripts/pipeline_step15_wayback.py` — parallel CDX check + trafilatura extraction
> - `data/processed/buildout_promises_real_enriched_v2.csv` — with `article_text_full` column
> - DVC pushed, git committed
>
> **Estimated Effort**: ~2-6 hours colab runtime (CPU only)
> **Critical Path**: Script → Deploy → Run → DVC → Commit

---

## Context
Direct article fetch blocked — datacenterdynamics.com/knowledge.com block trafilatura. Wayback Machine has snapshots for all tested URLs (3/3). CDX API slow (~13s/URL sequential, ~3-5s parallel with 10 workers). Storage negligible (~13 MB extracted text for 5,295 articles).

**Key Findings**:
- CDX API: `http://web.archive.org/cdx/search/cdx?url={url}&limit=1&output=json&fl=timestamp,statuscode`
- Fetch URL: `https://web.archive.org/web/{timestamp}/{original_url}`
- Trafilatura extracts ~2,500 chars per article from archived pages
- 30s CDX timeout, 60s fetch timeout needed

---

## Blocker: Wayback Machine Blocked from Network

**All approaches tested:**
- `http://web.archive.org/cdx/` → `Connection refused` (port 80 blocked)
- `https://web.archive.org/cdx/` → Works for CDX queries (55% snapshots found)
- `https://web.archive.org/web/{ts}/{url}` → `Connection refused` (port 443 blocked for content)
- Colab VM → Same `Connection refused` on both ports
- Availability API (`archive.org/wayback/available`) → Returns "no snapshots" (broken endpoint)

**Result**: Wayback content delivery IP range is blocked from this network. Script and CDX API work correctly, but archived content cannot be fetched. 5,295 events remain at 200-char GDELT snippet quality.

## Plan

- [x] 1. **Create `scripts/pipeline_step15_wayback.py`**

  **What to do**:
  - Read `data/processed/buildout_promises_real.csv`
  - For each URL: query CDX API for earliest `200` snapshot timestamp
  - Fetch archived page via `https://web.archive.org/web/{ts}/{url}`
  - Extract text with `trafilatura.extract()`
  - Add `article_text_full` column
  - Save checkpoint every 500 articles to `/tmp/wayback_checkpoint_{n}.csv`
  - Final output: `data/processed/buildout_promises_real_enriched_v2.csv`
  - DVC add + push

  **Parallelism**: ThreadPoolExecutor(10). CDX query first (parallel), then fetch+extract (parallel per batch of 500).
  
  **Timeouts**: CDX 30s, fetch 60s, trafilatura 30s.

  **Error handling**: Failed URLs get empty string in `article_text_full`. Track success rate. Continue on error.

  **No secrets needed** — Wayback API is public.

  **Acceptance Criteria**:
  - Script runs without hardcoded secrets
  - ≥70% of URLs have archived text
  - Mean extracted text length ≥ 500 chars
  - Checkpoints saved every 500
  - DVC add + push succeeds

  **Commit**: YES

- [x] 2. **Deploy on colab + execute** [CANCELLED — Wayback blocked from colab network]

  **What to do**:
  - Create fresh colab session
  - Clone repo, install deps (trafilatura, lxml)
  - DVC pull existing data
  - Run `python3 scripts/pipeline_step15_wayback.py`
  - Monitor progress via colab exec -e for checkpoint files

  **Run time**: estimated 2-6 hours for 5,295 URLs

  **Commit**: NO (script handles this)

- [x] 3. **DVC pull + verify + commit** [CANCELLED — no data to pull, Wayback blocked]

  **What to do**:
  - DVC pull enriched CSV from colab remote
  - Verify: 5,296 lines, `article_text_full` column populated
  - Commit DVC hash + updated script

  **Acceptance Criteria**:
  - [ ] 5,296 lines (header + 5,295 data)
  - [ ] `article_text_full` populated for ≥70% of rows
  - [ ] Mean text length ≥ 500 chars
  - [ ] DVC remote in sync
  - [ ] Git committed

  **Commit**: `feat: full article text extraction via Wayback Machine`
