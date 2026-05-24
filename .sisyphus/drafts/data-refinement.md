# Draft: Data Refinement Plan

## Requirements
- Hybrid approach: dedup + re-fetch + HF model extraction on colab
- Everything done on colab (T4 16GB GPU)
- Output: cleaned dataset with full article text + dedup groups + structured fields
- Later: ML pipeline + paper

## Current Data State
- 5,295 events, ALL with 200-char GDELT snippets (step13 fetched 0%)
- MW: 31% populated (1,638)
- Location: 42% populated
- Promise label: 3.2% populated (171 labeled)
- Source domains: datacenterdynamics.com (3,523), datacenterknowledge.com (1,772)

## Best HF Models for Colab T4 (16GB)

| Task | Model | Params | VRAM | Rationale |
|------|-------|--------|------|-----------|
| Dedup clustering | sentence-transformers/all-MiniLM-L6-v2 | 80M | 0.3GB | Fast, 384-dim embeddings, clusters similar articles |
| Text classification | facebook/bart-large-mnli | 400M | 1.6GB | Zero-shot, no training needed, classifies kept/failed/pending |
| NER (MW extraction) | dslim/bert-base-NER | 110M | 0.4GB | Extracts numerical entities, can fine-tune for MW |
| Structured extraction | Qwen/Qwen2.5-7B-Instruct (Q4) | 7B | ~6GB | Prompt-based: one pass extracts all fields |

## Approach
- Use sentence-transformers for dedup (fast, all 5,295)
- Use BART-large-mnli for zero-shot promise classification on re-fetched articles
- Use Qwen 7B Q4 for location/MW extraction on high-signal subset

## Scope Boundaries
- IN: Dedup, re-fetch, HF extraction, dataset merge, DVC push
- OUT: Full ML pipeline, paper updates, event study refresh
