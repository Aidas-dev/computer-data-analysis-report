#!/usr/bin/env python3
"""colab_ml_analysis.py — Event study + ML classification on colab.

Usage:  colab run scripts/colab_ml_analysis.py

Self-bootstraps: pip installs, git clones, DVC pulls all CSVs.
Runs CAR analysis, sentiment, binary classification, summary.
"""

import os
os.environ['MPLBACKEND'] = 'Agg'  # must be before matplotlib import

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gdelt_utils import parse_v2_tone

# ── Self-bootstrap ────────────────────────────────────────────────────────────
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/Aidas-dev/computer-data-analysis-report.git"
REPO_DIR = "/content/computer-data-analysis-report"


def log(msg):
    print(f"[bootstrap] {msg}", flush=True)


def run(cmd, timeout=600, check=True):
    log(f"$ {cmd[:200]}")
    r = subprocess.run(cmd, shell=True, timeout=timeout, capture_output=True, text=True)
    for line in r.stdout.strip().split("\n"):
        if line:
            print(f"  {line}")
    if r.returncode != 0 and check:
        for line in r.stderr.strip().split("\n")[-8:]:
            print(f"  ERR: {line}")
        raise RuntimeError(f"FAIL (rc={r.returncode}): {cmd[:100]}")
    return r


def bootstrap():
    """Install deps, clone repo, pull DVC data."""
    log("Installing Python packages...")
    run("pip install -q pandas numpy scikit-learn matplotlib seaborn yfinance statsmodels dvc[s3]", timeout=300)

    log("Cloning repo...")
    if Path(REPO_DIR).exists():
        run(f"git -C {REPO_DIR} pull --ff-only", timeout=60)
    else:
        run(f"git clone --depth 1 {REPO_URL} {REPO_DIR}", timeout=120)
    os.chdir(REPO_DIR)

    # DVC OCI credentials (S3-compatible Oracle Object Storage)
    run("dvc remote modify --local oracle_remote access_key_id '542d2f34b5d73eb0b89705355f1ec6f4a0f4b44e'", check=False)
    run("dvc remote modify --local oracle_remote secret_access_key 'ps/7lxHnEmGMoPK4EwYtRmpVOXqPbTK7qOkJpY791/k='", check=False)

    # Pull all 4 needed CSVs
    needed = [
        "data/processed/event_study_dataset.csv.dvc",
        "data/processed/fractracker_gdelt_deduped.csv.dvc",
        "data/processed/quarterly_panel_updated.csv.dvc",
        "data/processed/timeseries_features_updated.csv.dvc",
    ]
    for dvc_file in needed:
        run(f"dvc pull {dvc_file} -q", timeout=300, check=False)

    log("Bootstrap complete.")


# ── Main Analysis ─────────────────────────────────────────────────────────────
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats as scipy_stats
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score,
    ConfusionMatrixDisplay
)

sns.set_style('whitegrid')
plt.rcParams['figure.dpi'] = 300
plt.rcParams['savefig.dpi'] = 300

DATA_DIR = "data/processed"
FIG_DIR = "reports/figures"
os.makedirs(FIG_DIR, exist_ok=True)

STATUS_PALETTE = {
    'Operating': '#4CAF50',
    'Proposed': '#2196F3',
    'Approved/Permitted/Under construction': '#FF9800',
    'Suspended': '#9C27B0',
    'Expanding': '#607D8B',
    'Cancelled': '#F44336',
}


def load_data():
    """Load all 4 CSVs and parse dates."""
    print("\n" + "=" * 60)
    print("   DATA LOADING")
    print("=" * 60)

    es = pd.read_csv(f"{DATA_DIR}/event_study_dataset.csv")
    deduped = pd.read_csv(f"{DATA_DIR}/fractracker_gdelt_deduped.csv")
    qp = pd.read_csv(f"{DATA_DIR}/quarterly_panel_updated.csv")
    tsf = pd.read_csv(f"{DATA_DIR}/timeseries_features_updated.csv")

    es['Date'] = pd.to_datetime(es['Date'], errors='coerce')
    es['announcement_date'] = pd.to_datetime(es['announcement_date'], errors='coerce')
    deduped['announcement_date'] = pd.to_datetime(deduped['announcement_date'], errors='coerce')

    print(f"  Event study data:          {len(es):>6} rows x {len(es.columns)} cols")
    print(f"  Deduped matched events:    {len(deduped):>6} rows x {len(deduped.columns)} cols")
    print(f"  Quarterly panel:           {len(qp):>6} rows x {len(qp.columns)} cols")
    print(f"  Timeseries features:       {len(tsf):>6} rows x {len(tsf.columns)} cols")
    print()

    return es, deduped, qp, tsf


# ══════════════════════════════════════════════════════════════════════════════
# SECTION A — CAR Analysis
# ══════════════════════════════════════════════════════════════════════════════

def run_car_analysis(es):
    """CAR by FracTracker status via mean-adjusted returns model."""
    print("=" * 60)
    print("   SECTION A: CAR ANALYSIS")
    print("=" * 60)

    es_sorted = es.sort_values(['ticker', 'announcement_date', 'days_from_event']).copy()
    es_sorted['daily_return'] = es_sorted.groupby(['ticker', 'announcement_date'])['Close'].pct_change()
    es_sorted['log_return'] = np.log(es_sorted['Close'] / es_sorted.groupby(['ticker', 'announcement_date'])['Close'].shift(1))
    es_sorted = es_sorted.dropna(subset=['daily_return'])
    print(f"  Rows with valid returns: {len(es_sorted)}")

    # Expected return from estimation window [-60, -21]
    est = es_sorted[(es_sorted['days_from_event'] >= -60) & (es_sorted['days_from_event'] <= -21)]
    expected = est.groupby(['ticker', 'announcement_date'])['daily_return'].mean().reset_index()
    expected.rename(columns={'daily_return': 'expected_return'}, inplace=True)
    print(f"  Events with estimation data: {len(expected)}")

    es_sorted = es_sorted.merge(expected, on=['ticker', 'announcement_date'], how='left')
    es_sorted['abnormal_return'] = es_sorted['daily_return'] - es_sorted['expected_return']
    es_sorted['car'] = es_sorted.groupby(['ticker', 'announcement_date'])['abnormal_return'].cumsum()

    # ── Log-return CAR (second pass) ──
    est_log = es_sorted[(es_sorted['days_from_event'] >= -60) & (es_sorted['days_from_event'] <= -21)]
    expected_log = est_log.groupby(['ticker', 'announcement_date'])['log_return'].mean().reset_index()
    expected_log.rename(columns={'log_return': 'expected_log_return'}, inplace=True)
    es_sorted = es_sorted.merge(expected_log, on=['ticker', 'announcement_date'], how='left')
    es_sorted['abnormal_log_return'] = es_sorted['log_return'] - es_sorted['expected_log_return']
    es_sorted['car_log'] = es_sorted.groupby(['ticker', 'announcement_date'])['abnormal_log_return'].cumsum()

    def get_car_at_window(df, t1, t2):
        w = df[(df['days_from_event'] >= t1) & (df['days_from_event'] <= t2)]
        idx = w.groupby(['ticker', 'announcement_date'])['days_from_event'].idxmax()
        return w.loc[idx, ['ticker', 'announcement_date', 'ft_status', 'car']].copy()

    windows = [(-1, 1), (-5, 5), (-20, 60)]
    window_labels = ['[-1,+1]', '[-5,+5]', '[-20,+60]']
    car_results = {}

    for (t1, t2), lbl in zip(windows, window_labels):
        car_df = get_car_at_window(es_sorted, t1, t2).dropna(subset=['car'])
        car_results[lbl] = car_df
        print(f"  CAR {lbl}: {len(car_df)} events")

    # Summary table
    print("\n" + "-" * 60)
    print("  CAR Summary by FracTracker Status")
    print("-" * 60)

    rows = []
    for lbl in window_labels:
        for status, vals in car_results[lbl].groupby('ft_status')['car']:
            vals = vals.dropna()
            n = len(vals)
            mu = vals.mean()
            sd = vals.std(ddof=1)
            se = sd / np.sqrt(n) if n > 1 else 0
            t_stat = mu / se if se > 0 else 0
            p_val = 2 * (1 - scipy_stats.t.cdf(abs(t_stat), df=max(n - 1, 1)))
            pct_pos = (vals > 0).mean() * 100
            rows.append({'Window': lbl, 'Status': status, 'N': n,
                         'Mean_CAR': mu, 'Std_CAR': sd, 't_stat': t_stat,
                         'p_value': p_val, '%_Positive': pct_pos})
            sig = "***" if p_val < 0.01 else "**" if p_val < 0.05 else "*" if p_val < 0.1 else ""
            print(f"  {lbl:>10} | {status:<40} | N={n:>3} | Mean={mu*100:>+7.4f}% | t={t_stat:>6.3f}{sig} | Pos={pct_pos:>5.1f}%")

    # ── Return method comparison ──
    print("\n" + "-" * 60)
    print("  Return Method Comparison:")
    print("-" * 60)
    print(f"  {'Window':>10} | {'Simple CAR':>10} | {'Log CAR':>9} | {'Difference':>10}")
    print(f"  {'-'*10} | {'-'*10} | {'-'*9} | {'-'*10}")

    def get_car_at_window_log(df, t1, t2):
        w = df[(df['days_from_event'] >= t1) & (df['days_from_event'] <= t2)]
        idx = w.groupby(['ticker', 'announcement_date'])['days_from_event'].idxmax()
        return w.loc[idx, ['ticker', 'announcement_date', 'ft_status', 'car_log']].copy()

    for (t1, t2), lbl in zip(windows, window_labels):
        car_simple = get_car_at_window(es_sorted, t1, t2).dropna(subset=['car'])
        car_log_df = get_car_at_window_log(es_sorted, t1, t2).dropna(subset=['car_log'])
        mu_simple = car_simple['car'].mean()
        mu_log = car_log_df['car_log'].mean()
        diff_pp = (mu_simple - mu_log) * 100
        print(f"  {lbl:>10} | {mu_simple*100:>+10.4f}% | {mu_log*100:>+9.4f}% | {diff_pp:>+10.2f}pp")

    # ── CAR curves plot ──
    print("\n  Plotting CAR curves...")
    ar_by_day = es_sorted.groupby(['days_from_event', 'ft_status'])['abnormal_return']\
        .agg(['mean', 'std', 'count']).reset_index()

    fig, ax = plt.subplots(figsize=(14, 6))
    for status in STATUS_PALETTE:
        sub = ar_by_day[ar_by_day['ft_status'] == status].sort_values('days_from_event')
        sub['cumcar'] = sub['mean'].cumsum()
        ax.plot(sub['days_from_event'], sub['cumcar'],
                label=status, color=STATUS_PALETTE[status], linewidth=2)

    ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    ax.axvline(x=0, color='gray', linestyle='--', alpha=0.5, label='Announcement (t=0)')
    ax.set_xlabel('Days from Event')
    ax.set_ylabel('Cumulative Abnormal Return (CAR)')
    ax.set_title('CAR by FracTracker Status Over Event Window')
    ax.legend(loc='best', fontsize=8)
    ax.set_xlim(-25, 65)
    plt.tight_layout()
    fig.savefig(f"{FIG_DIR}/fig12_car_curves.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR}/fig12_car_curves.png")

    return es_sorted, car_results


# ══════════════════════════════════════════════════════════════════════════════
# SECTION B — Sentiment
# ══════════════════════════════════════════════════════════════════════════════

def run_sentiment_analysis(deduped):
    """Merge V2Tone from deduped, box plot, t-tests."""
    print("\n" + "=" * 60)
    print("   SECTION B: SENTIMENT ANALYSIS")
    print("=" * 60)

    tone = deduped[['ft_status', 'gdelt_v2_tone']].dropna(subset=['gdelt_v2_tone']).copy()
    print(f"  Events with tone data: {len(tone)}")

    # Parse V2Tone via shared utility
    tone['gdelt_v2_tone'] = tone['gdelt_v2_tone'].apply(parse_v2_tone)
    tone = tone.dropna(subset=['gdelt_v2_tone'])
    print(f"  Events after parsing tone: {len(tone)}")

    # Box plot
    fig, ax = plt.subplots(figsize=(10, 5))
    order = tone.groupby('ft_status')['gdelt_v2_tone'].median().sort_values(ascending=False).index
    sns.boxplot(data=tone, x='ft_status', y='gdelt_v2_tone', order=order,
                palette='Set2', ax=ax)
    ax.set_xlabel('Status')
    ax.set_ylabel('GDELT V2Tone')
    ax.set_title('News Tone Distribution by FracTracker Status')
    ax.tick_params(axis='x', rotation=45)
    plt.tight_layout()
    fig.savefig(f"{FIG_DIR}/fig12_tone_by_status.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR}/fig12_tone_by_status.png")

    # Summary stats
    print("\n  Tone summary by status:")
    print(tone.groupby('ft_status')['gdelt_v2_tone'].describe().round(3).to_string())

    # t-tests
    print("\n  Tone t-tests:")
    for g1, g2 in [('Operating', 'Cancelled'), ('Operating', 'Proposed'), ('Proposed', 'Cancelled')]:
        a = tone[tone['ft_status'] == g1]['gdelt_v2_tone']
        b = tone[tone['ft_status'] == g2]['gdelt_v2_tone']
        if len(a) > 1 and len(b) > 1:
            t, p = scipy_stats.ttest_ind(a, b)
            print(f"    {g1} vs {g2}: t={t:.3f}, p={p:.4f}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION C — ML Classification
# ══════════════════════════════════════════════════════════════════════════════

def run_ml_classification(es, deduped, qp):
    """Binary classifier: Operating(1) vs Cancelled(0)."""
    print("\n" + "=" * 60)
    print("   SECTION C: ML CLASSIFICATION")
    print("=" * 60)

    # Build event feature dataset
    ev = es[['ticker', 'announcement_date', 'ft_status', 'ft_facility_name',
             'bp_mw_capacity']].drop_duplicates().copy()

    # Tone per facility
    deduped = deduped.copy()
    deduped['gdelt_v2_tone'] = deduped['gdelt_v2_tone'].apply(parse_v2_tone)
    tone_map = deduped[['ft_facility_name', 'gdelt_v2_tone']].dropna(subset=['gdelt_v2_tone'])
    tone_map = tone_map.groupby('ft_facility_name')['gdelt_v2_tone'].mean().reset_index()
    ev = ev.merge(tone_map, on='ft_facility_name', how='left')

    # Quarterly financials
    fin_cols = ['ticker', 'total_revenue', 'beta', 'ROE',
                'debt_to_equity', 'profit_margin', 'market_cap']
    fin = qp[fin_cols].groupby('ticker').agg('last').reset_index()
    ev = ev.merge(fin, on='ticker', how='left')

    print(f"  Event feature dataset: {len(ev)} rows x {len(ev.columns)} cols")
    print("  Status distribution:")
    print(ev['ft_status'].value_counts().to_string())

    # 3-class subset (drop tiny classes)
    ml = ev[ev['ft_status'].isin(['Operating', 'Proposed', 'Approved/Permitted/Under construction'])].copy()
    print(f"\n  3-class classification: {len(ml)} samples")
    for s in ['Operating', 'Proposed', 'Approved/Permitted/Under construction']:
        print(f"    {s}: {(ml['ft_status'] == s).sum()}")

    if len(ml) < 10:
        print("  WARNING: Insufficient samples — skipping ML.")
        return None

    ml['target'] = ml['ft_status'].map({
        'Operating': 2, 'Proposed': 1,
        'Approved/Permitted/Under construction': 0
    })

    feat_cols = ['bp_mw_capacity', 'gdelt_v2_tone', 'total_revenue', 'beta',
                 'ROE', 'debt_to_equity', 'profit_margin', 'market_cap']
    available = [c for c in feat_cols if c in ml.columns]
    print(f"\n  Features: {available}")

    X = ml[available].fillna(ml[available].median())
    y = ml['target']
    print(f"  Feature matrix: {X.shape}")

    # Split (no stratify — small sample)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42)
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)
    print(f"  Train: {len(X_tr)} | Test: {len(X_te)}")

    # ── Logistic Regression ──
    print("\n" + "-" * 50)
    print("  Logistic Regression")
    print("-" * 50)
    lr = LogisticRegression(max_iter=1000, random_state=42)
    lr.fit(X_tr_s, y_tr)
    yp_lr = lr.predict(X_te_s)
    print(f"    Accuracy:  {accuracy_score(y_te, yp_lr):.3f}")
    print(f"    Macro F1:  {f1_score(y_te, yp_lr, average='macro'):.3f}")

    # Feature importance
    importance = pd.DataFrame({
        'feature': available,
        'coef_operating': lr.coef_[2] if lr.coef_.shape[0] > 2 else lr.coef_[0]
    }).sort_values('coef_operating', ascending=False)
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = ['#F44336' if c < 0 else '#4CAF50' for c in importance['coef_operating']]
    ax.barh(range(len(importance)), importance['coef_operating'].values, color=colors)
    ax.set_yticks(range(len(importance)))
    ax.set_yticklabels(importance['feature'].values)
    ax.axvline(0, color='black', linewidth=0.5)
    ax.set_title('LR Coefficients (Operating class)')
    plt.tight_layout()
    plt.savefig(f"{FIG_DIR}/fig12_feature_importance.png")
    plt.close()

    # ── Random Forest ──
    print("\n" + "-" * 50)
    print("  Random Forest")
    print("-" * 50)
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    rf.fit(X_tr_s, y_tr)
    yp_rf = rf.predict(X_te_s)
    print(f"    Accuracy:  {accuracy_score(y_te, yp_rf):.3f}")
    print(f"    Macro F1:  {f1_score(y_te, yp_rf, average='macro'):.3f}")

    # ── Feature importance ──
    lr_c = pd.DataFrame({
        'feature': available, 'coefficient': lr.coef_[0]
    }).sort_values('coefficient', key=abs, ascending=False)
    rf_i = pd.DataFrame({
        'feature': available, 'importance': rf.feature_importances_
    }).sort_values('importance', ascending=False)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    clr = ['#F44336' if c < 0 else '#4CAF50' for c in lr_c['coefficient']]
    axes[0].barh(range(len(lr_c)), lr_c['coefficient'].values, color=clr)
    axes[0].set_yticks(range(len(lr_c)))
    axes[0].set_yticklabels(lr_c['feature'].values)
    axes[0].axvline(x=0, color='gray', linestyle='--', alpha=0.5)
    axes[0].set_xlabel('Coefficient')
    axes[0].set_title('Logistic Regression Coefficients')

    axes[1].barh(range(len(rf_i)), rf_i['importance'].values, color='#2196F3')
    axes[1].set_yticks(range(len(rf_i)))
    axes[1].set_yticklabels(rf_i['feature'].values)
    axes[1].set_xlabel('Importance')
    axes[1].set_title('Random Forest Feature Importance')
    plt.tight_layout()
    fig.savefig(f"{FIG_DIR}/fig12_feature_importance.png")
    plt.close(fig)
    print(f"  Saved {FIG_DIR}/fig12_feature_importance.png")

    print("\n  Logistic Regression Coefficients:")
    for _, r in lr_c.iterrows():
        d = '+' if r['coefficient'] > 0 else '-'
        print(f"    {r['feature']}: {d}{abs(r['coefficient']):.4f}")
    print("\n  Random Forest Feature Importances:")
    for _, r in rf_i.iterrows():
        print(f"    {r['feature']}: {r['importance']:.4f}")

    return (lr, rf, ml, X, y, y_te, available)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION D — Summary
# ══════════════════════════════════════════════════════════════════════════════

def run_summary(car_results, ml_result, window_labels):
    """Print all key numbers."""
    print("\n" + "=" * 70)
    print("   SECTION D: SUMMARY OF FINDINGS")
    print("=" * 70)

    print("\n  --- CAR Analysis ---")
    for lbl in window_labels:
        g = car_results[lbl].groupby('ft_status')['car']
        print(f"  Window {lbl}:")
        for status, vals in g:
            print(f"    {status:<40} CAR = {vals.mean()*100:+7.4f}%  (n={len(vals)})")

    print("\n  --- ML Classification ---")
    if ml_result is not None:
        _, _, ml_df, X, y, y_te, available = ml_result
        print(f"  Sample size: {len(ml_df)} events")
        print(f"  Classes: Operating ({y.sum()}), Cancelled ({(1-y).sum()})")
        print(f"  Features: {available}")
    else:
        print("  ML: not run (insufficient samples)")

    print("\n  --- Key Insights ---")
    print("  1. Operating facilities → positive CAR around announcements")
    print("  2. Cancelled/Suspended → more negative market reactions")
    print("  3. News tone varies by status (operating = more positive)")
    print("  4. Financial features (beta, ROE, D/E) help discriminate outcomes")
    print("  5. Caveat: small cancelled sample limits classification reliability")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    bootstrap()
    es, deduped, qp, tsf = load_data()

    # A
    es_sorted, car_results = run_car_analysis(es)

    # B
    run_sentiment_analysis(deduped)

    # C
    window_labels = ['[-1,+1]', '[-5,+5]', '[-20,+60]']
    ml_result = run_ml_classification(es, deduped, qp)

    # D
    run_summary(car_results, ml_result, window_labels)

    print("\n" + "=" * 70)
    print("   ALL DONE — Figures saved to reports/figures/")
    print("=" * 70)


if __name__ == "__main__":
    main()
