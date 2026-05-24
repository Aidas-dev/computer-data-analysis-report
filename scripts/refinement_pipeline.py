#!/usr/bin/env python3
"""Refinement pipeline for buildout events — colab run compatible."""

import os, sys, subprocess, json, time, re, gc, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore

import numpy as np
import pandas as pd
from tqdm import tqdm

warnings.filterwarnings('ignore')

if os.path.exists('/content'):
    repo_dir = '/content/computer-data-analysis-report'
    if not os.path.exists(repo_dir):
        gh_token = os.environ.get('GH_TOKEN', '')
        clone_url = f'https://Aidas-dev:{gh_token}@github.com/Aidas-dev/computer-data-analysis-report.git' if gh_token else 'https://github.com/Aidas-dev/computer-data-analysis-report.git'
        subprocess.run(['git', 'clone', clone_url, repo_dir], check=True)
    os.chdir(repo_dir)

    subprocess.run(['pip', 'install', '-q', 'torch', 'transformers', 'accelerate',
                    'sentence-transformers', 'bitsandbytes', 'trafilatura',
                    'pandas', 'numpy',                     'requests', 'tqdm', 'scikit-learn'], check=True)

    subprocess.run(['pip', 'install', '-q', 'dvc', 'dvc[s3]'], check=True)
    subprocess.run(['dvc', 'pull'], check=True)

import requests


def log(msg):
    print(f'[refine] {msg}', flush=True)


def pilot_phase(df_mw):
    log('=' * 60)
    log('PHASE 0: Pilot — validating fetch quality')
    log('=' * 60)

    domains = df_mw['source_domain'].unique()
    sample_urls = []
    for d in domains:
        pool = df_mw[df_mw['source_domain'] == d]['url'].dropna().unique()
        n = min(20, len(pool))
        if n > 0:
            sample_urls.extend(np.random.RandomState(42).choice(pool, n, replace=False))

    sample_urls = list(dict.fromkeys(sample_urls))
    if len(sample_urls) > 50:
        sample_urls = sample_urls[:50]

    log(f'Pilot: {len(sample_urls)} URLs selected')

    successes = 0
    results = []
    for url in tqdm(sample_urls, desc='Pilot'):
        try:
            r = requests.head(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            status = r.status_code
            text = ''
            if status == 200:
                import trafilatura
                downloaded = trafilatura.fetch_url(url)
                text = trafilatura.extract(downloaded) if downloaded else ''
                if text and len(text) > 500:
                    successes += 1
            results.append({'url': url, 'status': status, 'text_len': len(text or '')})
        except Exception:
            results.append({'url': url, 'status': 0, 'text_len': 0})

    rate = successes / len(sample_urls) * 100 if sample_urls else 0
    log(f'PILOT: {successes}/{len(sample_urls)} success ({rate:.1f}%)')
    if rate < 70:
        log(f'PILOT FAILED: {rate:.1f}% < 70% threshold — aborting')
        pd.DataFrame(results).to_csv('/tmp/pilot_results.csv', index=False)
        sys.exit(1)
    log(f'PILOT PASSED: {rate:.1f}%')
    pd.DataFrame(results).to_csv('/tmp/pilot_results.csv', index=False)


def dedup_phase(df):
    log('=' * 60)
    log('PHASE 1: Dedup — embedding text snippets with MiniLM')
    log('=' * 60)

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    log('MiniLM-L6-v2 loaded')

    texts = (df['extracted_text_snippet'].fillna('') + ' ' + df['company'].fillna('')).tolist()
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)
    log(f'Embeddings shape: {embeddings.shape}')

    del model
    gc.collect()

    from sklearn.metrics.pairwise import cosine_similarity
    sim = cosine_similarity(embeddings)

    threshold = 0.85
    clusters = []
    assigned = set()
    for i in range(len(df)):
        if i in assigned:
            continue
        cluster = [i]
        for j in range(i + 1, len(df)):
            if j not in assigned and sim[i, j] >= threshold:
                cluster.append(j)
                assigned.add(j)
        assigned.add(i)
        clusters.append(cluster)

    cluster_map = {}
    for cid, members in enumerate(clusters):
        for idx in members:
            cluster_map[idx] = cid

    df_result = df.copy()
    df_result['cluster_id'] = df.index.map(cluster_map)

    reduction = (1 - len(clusters) / len(df)) * 100 if len(df) > 0 else 0
    log(f'DEDUP: {len(df)} -> {len(clusters)} clusters ({reduction:.1f}% reduction)')

    del embeddings, sim
    gc.collect()

    return df_result


def fetch_phase(df_mw):
    log('=' * 60)
    log('PHASE 2: Fetch — full article text for MW events')
    log('=' * 60)

    import trafilatura

    domain_sem = {}
    results = {}
    fetch_start = time.time()

    def fetch_one(url):
        domain = url.split('/')[2] if '//' in url else ''
        sem = domain_sem.setdefault(domain, Semaphore(3))
        with sem:
            try:
                time.sleep(0.3)
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    text = trafilatura.extract(downloaded)
                    return url, (text if text and len(text) > 100 else '')
            except Exception:
                pass
            return url, ''

    urls = df_mw['url'].tolist()
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(fetch_one, u) for u in urls]
        for fut in tqdm(as_completed(futs), total=len(futs), desc='Fetch'):
            url, text = fut.result()
            results[url] = text

    fetch_elapsed = time.time() - fetch_start

    df_result = df_mw.copy()
    df_result['article_text_full'] = df_result['url'].map(results).fillna('')

    success = (df_result['article_text_full'].str.len() > 500).sum()
    mean_len = df_result['article_text_full'].str.len().mean()
    log(f'FETCH: {success}/{len(df_result)} success ({success / len(df_result) * 100:.1f}%), mean len {mean_len:.0f} chars')
    log(f'Time: {fetch_elapsed:.0f}s ({len(df_result) / max(1, fetch_elapsed):.1f} URLs/s)')

    return df_result


def qwen_phase(df_fetched):
    log('=' * 60)
    log('PHASE 3: Qwen — structured extraction (MW, location, company)')
    log('=' * 60)

    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    model_name = 'Qwen/Qwen2.5-7B-Instruct'
    log('Loading Qwen2.5-7B-Instruct in 4-bit...')
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name, load_in_4bit=True, device_map='auto',
        torch_dtype=torch.float16
    )
    log('Qwen loaded (4-bit)')

    prompt_template = """Extract fields from this data center announcement. Return ONLY valid JSON.

Article: {text}

{{"mw_capacity": <number or null>, "location_city": "<string or null>", "location_state": "<string or null>", "company": "<string or null>", "status": "<completed|cancelled|announced|unclear>", "confidence": <0-1>}}"""

    articles = df_fetched[df_fetched['article_text_full'].str.len() > 500].reset_index(drop=True)
    n = min(len(articles), int(os.environ.get('MAX_ARTICLES', '99999')))
    articles = articles.head(n)
    log(f'Articles to extract: {len(articles)}')

    fields = []
    qwen_start = time.time()

    for i in tqdm(range(0, len(articles), 4), desc='Qwen'):
        batch = articles.iloc[i:i + 4]
        for _, row in batch.iterrows():
            text = row['article_text_full'][:2000]
            prompt = prompt_template.format(text=text)
            messages = [{'role': 'user', 'content': prompt}]
            txt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = tokenizer(txt, return_tensors='pt').to(model.device)
            parsed = {}
            for attempt in range(3):
                try:
                    out = model.generate(**inputs, max_new_tokens=256, temperature=0.1, do_sample=True)
                    resp = tokenizer.decode(out[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
                    resp_clean = resp.strip().strip('```json').strip('```').strip()
                    if resp_clean.startswith('{'):
                        parsed = json.loads(resp_clean)
                    if not parsed:
                        m = re.search(r'\{.*\}', resp, re.DOTALL)
                        if m:
                            parsed = json.loads(m.group())
                    if parsed:
                        break
                except Exception:
                    if attempt == 2:
                        pass
                    time.sleep(0.5)
            fields.append({**parsed, 'url': row['url']})

        if (i + 4) % 100 == 0 and i + 4 > 0:
            pd.DataFrame(fields).to_parquet(f'/tmp/qwen_{i + 4}.parquet')

    qwen_elapsed = time.time() - qwen_start

    del model, tokenizer
    gc.collect()
    torch.cuda.empty_cache()

    df_extracted = pd.DataFrame(fields)
    df_extracted.to_parquet('/tmp/qwen_extracted.parquet')

    mw_coverage_before = df_fetched['mw_capacity'].notna().mean()
    mw_extracted = df_extracted['mw_capacity'].notna().mean()
    log(f'QWEN: {len(df_extracted)} articles, MW coverage before={mw_coverage_before:.1%}, extracted={mw_extracted:.1%}')
    log(f'Time: {qwen_elapsed:.0f}s ({qwen_elapsed / max(1, len(articles)):.1f}s/article)')

    return df_extracted


def bart_phase(df_fetched):
    log('=' * 60)
    log('PHASE 4: BART — zero-shot promise classification')
    log('=' * 60)

    from transformers import pipeline
    import torch

    log('Loading facebook/bart-large-mnli...')
    classifier = pipeline(
        'zero-shot-classification',
        model='facebook/bart-large-mnli',
        device=0 if torch.cuda.is_available() else -1,
        torch_dtype=torch.float16
    )
    log('BART loaded')

    candidate_labels = [
        'completed and operational',
        'cancelled or failed',
        'announced or planned'
    ]

    articles = df_fetched[df_fetched['article_text_full'].str.len() > 100].reset_index(drop=True)
    n = min(len(articles), int(os.environ.get('MAX_ARTICLES', '99999')))
    articles = articles.head(n)
    log(f'Articles to classify: {len(articles)}')

    results = []
    bart_start = time.time()

    for _, row in tqdm(articles.iterrows(), total=len(articles), desc='BART'):
        text = row['article_text_full'][:1000]
        if len(text) < 50:
            results.append({'url': row['url'], 'label': None, 'score': 0})
            continue
        try:
            out = classifier(text, candidate_labels)
            results.append({'url': row['url'], 'label': out['labels'][0], 'score': out['scores'][0]})
        except Exception:
            results.append({'url': row['url'], 'label': None, 'score': 0})

    bart_elapsed = time.time() - bart_start

    df_labels = pd.DataFrame(results)
    df_labels.to_parquet('/tmp/bart_labels.parquet')

    n_labeled = df_labels['label'].notna().sum()
    mean_conf = df_labels['score'].mean()
    log(f'BART: {n_labeled}/{len(df_labels)} labeled, mean conf={mean_conf:.3f}')
    log(f'Time: {bart_elapsed:.0f}s ({bart_elapsed / max(1, len(articles)):.1f}s/article)')

    del classifier
    gc.collect()
    torch.cuda.empty_cache()

    return df_labels


def merge_phase(df_orig, df_dedup, df_fetched, df_qwen, df_bart):
    log('=' * 60)
    log('PHASE 5: Merge — saving enriched dataset + DVC')
    log('=' * 60)

    df = df_orig.copy()
    df['cluster_id'] = df_dedup['cluster_id']

    fetch_cols = df_fetched[['url', 'article_text_full']]
    df = df.merge(fetch_cols, on='url', how='left')

    if df_qwen is not None and len(df_qwen):
        qwen_renamed = df_qwen.rename(columns={
            'mw_capacity': 'mw_qwen',
            'location_city': 'location_city_qwen',
            'location_state': 'location_state_qwen',
            'company': 'company_qwen'
        })
        keep = [c for c in ['url', 'mw_qwen', 'location_city_qwen', 'location_state_qwen', 'company_qwen', 'status']
                if c in qwen_renamed.columns]
        qwen_renamed = qwen_renamed[keep]
        df = df.merge(qwen_renamed, on='url', how='left')

        df['extraction_conflict'] = (
            df['mw_capacity'].notna() & df['mw_qwen'].notna() &
            (abs(df['mw_capacity'] - df['mw_qwen']) / df['mw_capacity'] > 0.3)
        )

    if df_bart is not None and len(df_bart):
        df = df.merge(
            df_bart[['url', 'label', 'score']].rename(
                columns={'label': 'promise_kept_zs', 'score': 'promise_zs_conf'}
            ),
            on='url', how='left'
        )

    df['article_text_full'] = df['article_text_full'].fillna('')

    out_path = 'data/processed/buildout_promises_real_enriched.csv'
    os.makedirs('data/processed', exist_ok=True)
    df.to_csv(out_path, index=False)
    log(f'SAVED: {out_path} — {len(df)} rows, {len(df.columns)} cols')

    log('Running DVC add...')
    try:
        result = subprocess.run(
            ['dvc', 'add', out_path],
            capture_output=True, text=True, check=True, timeout=120
        )
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                log(f'  {line.strip()}')
    except subprocess.TimeoutExpired:
        log('  DVC add timed out')
    except subprocess.CalledProcessError as e:
        log(f'  DVC add failed: {e.stderr[:200]}')
        log('  Continuing...')

    log('Running DVC push...')
    try:
        result = subprocess.run(
            ['dvc', 'push', out_path + '.dvc'],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            log('  DVC push OK')
        else:
            log(f'  DVC push issue: {result.stderr[:200]}')
    except subprocess.TimeoutExpired:
        log('  DVC push timed out')
    except Exception as e:
        log(f'  DVC push failed: {e}')

    log('MERGE: DVC add + push complete')

    return df


def main():
    print('=' * 60)
    print('REFINEMENT PIPELINE — Buildout Event Enrichment')
    print('=' * 60)

    df = pd.read_csv('data/processed/buildout_promises_real.csv', low_memory=False)
    df_mw = df[df['mw_capacity'].notna()].copy()
    print(f'Loaded {len(df)} events ({len(df_mw)} with MW)')
    print(f'Columns: {list(df.columns)}')
    print(f'MW populated: {df_mw.shape[0]}')
    print(f'Existing promise labels: {df["promise_kept"].notna().sum()}')

    pilot_phase(df_mw)
    df_dedup = dedup_phase(df)
    df_fetched = fetch_phase(df_mw)
    df_qwen = qwen_phase(df_fetched)
    df_bart = bart_phase(df_fetched)
    df_final = merge_phase(df, df_dedup, df_fetched, df_qwen, df_bart)

    print('\n' + '=' * 60)
    print('PIPELINE COMPLETE')
    print(f'Final rows: {len(df_final)}')
    print(f'Final columns: {len(df_final.columns)}')
    new_cols = [c for c in df_final.columns if c not in df.columns]
    print(f'New columns: {new_cols}')
    print('=' * 60)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Refinement pipeline for buildout events')
    parser.add_argument('--hf-token', help='HuggingFace token for model download')
    parser.add_argument('--aws-key', help='AWS access key for DVC S3 remote')
    parser.add_argument('--aws-secret', help='AWS secret key for DVC S3 remote')
    parser.add_argument('--max-articles', type=int, default=999999, help='Max articles to process (for testing)')
    args = parser.parse_args()
    
    if args.hf_token:
        os.environ['HF_TOKEN'] = args.hf_token
    if args.aws_key:
        os.environ['AWS_ACCESS_KEY_ID'] = args.aws_key
    if args.aws_secret:
        os.environ['AWS_SECRET_ACCESS_KEY'] = args.aws_secret
    if args.max_articles and args.max_articles < 999999:
        os.environ['MAX_ARTICLES'] = str(args.max_articles)
    
    main()
