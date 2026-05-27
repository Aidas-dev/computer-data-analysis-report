#!/usr/bin/env python3
"""Refresh yfinance data for deduped FracTracker-GDELT matched events.

Produces:
  - data/processed/quarterly_panel_updated.csv
  - data/processed/timeseries_features_updated.csv
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# === CONFIG ===
INPUT_CSV = 'data/processed/fractracker_gdelt_deduped.csv'
OUTPUT_QUARTERLY = 'data/processed/quarterly_panel_updated.csv'
OUTPUT_TIMESERIES = 'data/processed/timeseries_features_updated.csv'
MACRO_CSV = 'data/raw/macro_economic_indicators.csv'
EVENT_WINDOW = 60  # days before/after announcement

# Crusoe Energy is private → skip
PRIVATE_TICKERS = {'CRUS'}

# FracTracker ft_status → binary promise_label
STATUS_LABEL_MAP = {
    'Operating': 1,
    'Cancelled': 0,
}

INCOME_METRICS = [
    'Total Revenue', 'Net Income', 'EBITDA', 'Operating Income',
]
BALANCE_METRICS = [
    'Total Assets', 'Total Debt', 'Stockholders Equity',
    'Current Assets', 'Current Liabilities', 'Cash And Cash Equivalents',
]


def get_fiscal_quarter_end(dt):
    """Calendar quarter-end date (Mar 31 / Jun 30 / Sep 30 / Dec 31)."""
    qm = ((dt.month - 1) // 3) * 3 + 3
    return pd.Timestamp(year=dt.year, month=qm, day=1) + pd.offsets.MonthEnd(0)


def safe_get(series, key):
    try:
        val = series.get(key, np.nan)
        return val if val is not None else np.nan
    except Exception:
        return np.nan


# ============================================================
# STEP 1 — Read input
# ============================================================
print("=" * 60)
print("STEP 1: Reading input")
print("=" * 60)
df = pd.read_csv(INPUT_CSV)
df['announcement_date'] = pd.to_datetime(df['announcement_date'])
tickers = sorted(set(df['ticker'].dropna().unique()) - PRIVATE_TICKERS)
n_events = len(df)

min_date = df['announcement_date'].min() - timedelta(days=EVENT_WINDOW + 60)
max_date = df['announcement_date'].max() + timedelta(days=EVENT_WINDOW)
today = pd.Timestamp.now()
if max_date > today:
    max_date = today

print(f"  Events loaded: {n_events}")
print(f"  Tickers to download ({len(tickers)}): {tickers}")
print(f"  Skipped (private): {PRIVATE_TICKERS}")
print(f"  yfinance date range: {min_date.date()} → {max_date.date()}")

# ============================================================
# STEP 2 — Download yfinance data
# ============================================================
print("\n" + "=" * 60)
print("STEP 2: Downloading yfinance data")
print("=" * 60)

# --- Daily prices ---
print("\n  Daily prices …")
daily = yf.download(
    tickers=list(tickers),
    start=min_date,
    end=max_date,
    group_by='ticker',
    auto_adjust=True,
    progress=True,
)

# Handle MultiIndex (multiple tickers) vs flat (single ticker)
if isinstance(daily.columns, pd.MultiIndex):
    # MultiIndex with levels ['Ticker', 'Price']
    closes = daily.xs('Close', level='Price', axis=1)
    volumes = daily.xs('Volume', level='Price', axis=1)
else:
    t = tickers[0]
    closes = pd.DataFrame({t: daily['Close']})
    volumes = pd.DataFrame({t: daily['Volume']})

print(f"  Close prices: {closes.shape[0]} days × {len(closes.columns)} tickers")
print(f"  Volumes:      {volumes.shape[0]} days × {len(volumes.columns)} tickers")

# --- Quarterly financials ---
print("\n  Quarterly financials …")
fin_data = {}
for t in tickers:
    try:
        stock = yf.Ticker(t)
        fin = {}
        fin['income'] = stock.quarterly_income_stmt
        fin['balance'] = stock.quarterly_balance_sheet
        fin['cashflow'] = stock.quarterly_cashflow
        fin_data[t] = fin
        hi = fin['income'] is not None and not fin['income'].empty
        hb = fin['balance'] is not None and not fin['balance'].empty
        print(f"    {t}: income_stmt={'✓' if hi else '✗'}, balance_sheet={'✓' if hb else '✗'}")
    except Exception as e:
        print(f"    {t}: error — {e}")
        fin_data[t] = None

# --- Ticker info ---
print("\n  Ticker info (market cap, beta, EV) …")
info_data = {}
for t in tickers:
    try:
        info_data[t] = yf.Ticker(t).info
        mc = info_data[t].get('marketCap', 'N/A')
        print(f"    {t}: marketCap={mc}")
    except Exception as e:
        print(f"    {t}: error — {e}")
        info_data[t] = {}

# ============================================================
# STEP 3 — Quarterly panel
# ============================================================
print("\n" + "=" * 60)
print("STEP 3: Building quarterly panel")
print("=" * 60)

qrows = []
for _, ev in df.iterrows():
    ev_date = ev['announcement_date']
    t = ev['ticker']
    qend = get_fiscal_quarter_end(ev_date)

    row = {
        'ft_OBJECTID': ev['ft_OBJECTID'],
        'ticker': t,
        'announcement_date': ev_date,
        'fiscal_quarter_end': qend,
    }

    # -- Financial statement data --
    if t in fin_data and fin_data[t] is not None:
        fin = fin_data[t]

        # Income statement
        if fin['income'] is not None and not fin['income'].empty:
            inc = fin['income']
            cols = inc.columns
            if qend in cols:
                qdata = inc[qend]
            else:
                nearest = min(cols, key=lambda c: abs((c - qend).days))
                qdata = inc[nearest]
            for m in INCOME_METRICS:
                row[m.lower().replace(' ', '_')] = safe_get(qdata, m)

        # Balance sheet
        if fin['balance'] is not None and not fin['balance'].empty:
            bal = fin['balance']
            cols = bal.columns
            if qend in cols:
                qdata = bal[qend]
            else:
                nearest = min(cols, key=lambda c: abs((c - qend).days))
                qdata = bal[nearest]
            for m in BALANCE_METRICS:
                row[m.lower().replace(' ', '_')] = safe_get(qdata, m)

    # -- Info-based fields (current values — best available) --
    if t in info_data:
        inf = info_data[t]
        row['market_cap'] = inf.get('marketCap', np.nan)
        row['enterprise_value'] = inf.get('enterpriseValue', np.nan)
        row['beta'] = inf.get('beta', np.nan)

    # -- Derived ratios --
    rev = row.get('total_revenue', np.nan)
    ni = row.get('net_income', np.nan)
    oi = row.get('operating_income', np.nan)
    ta = row.get('total_assets', np.nan)
    td = row.get('total_debt', np.nan)
    se = row.get('stockholders_equity', np.nan)
    ca = row.get('current_assets', np.nan)
    cl = row.get('current_liabilities', np.nan)

    row['profit_margin'] = ni / rev if pd.notna(ni) and pd.notna(rev) and rev != 0 else np.nan
    row['operating_margin'] = oi / rev if pd.notna(oi) and pd.notna(rev) and rev != 0 else np.nan
    row['ROA'] = ni / ta if pd.notna(ni) and pd.notna(ta) and ta != 0 else np.nan
    row['ROE'] = ni / se if pd.notna(ni) and pd.notna(se) and se != 0 else np.nan
    row['debt_to_equity'] = td / se if pd.notna(td) and pd.notna(se) and se != 0 else np.nan
    row['current_ratio'] = ca / cl if pd.notna(ca) and pd.notna(cl) and cl != 0 else np.nan

    qrows.append(row)

qpanel = pd.DataFrame(qrows)
qpanel.to_csv(OUTPUT_QUARTERLY, index=False)
print(f"  Saved → {OUTPUT_QUARTERLY}")
print(f"  Shape: {qpanel.shape[0]} rows × {qpanel.shape[1]} cols")

# ============================================================
# STEP 4 — Timeseries features
# ============================================================
print("\n" + "=" * 60)
print("STEP 4: Building timeseries features")
print("=" * 60)

# Load & prep macro data
macro = pd.read_csv(MACRO_CSV)
macro['date'] = pd.to_datetime(macro['date'])
macro = macro.set_index('date')
macro_ffill = macro[['Fed Funds Rate', 'Unemployment Rate']].ffill()

trows = []
events_skipped = 0

for idx, ev in df.iterrows():
    eid = ev['ft_OBJECTID']
    t = ev['ticker']
    ev_date = ev['announcement_date']
    fs = ev['ft_status']
    label = STATUS_LABEL_MAP.get(fs, np.nan)

    if t in PRIVATE_TICKERS or t not in closes.columns:
        events_skipped += 1
        continue

    c = closes[t].dropna()
    v = volumes[t].dropna()
    if c.empty:
        events_skipped += 1
        continue

    # Date windows
    wstart = ev_date - timedelta(days=EVENT_WINDOW)
    wend = ev_date + timedelta(days=EVENT_WINDOW)
    estart = ev_date - timedelta(days=EVENT_WINDOW + 60)  # extra lookback for rolling

    wmask = (c.index >= wstart) & (c.index <= wend)
    emask = (c.index >= estart) & (c.index <= wend)

    ec = c[emask]  # extended series for rolling calcs
    wc = c[wmask]  # window-only series
    wv = v.reindex(wc.index)

    if len(wc) < 5:
        events_skipped += 1
        continue

    # Rolling computations (on extended series for lookback integrity)
    sma20 = ec.rolling(20).mean()
    sma60 = ec.rolling(60).mean()
    dr = ec.pct_change()
    vol20 = dr.rolling(20).std()
    mom20 = ec.pct_change(20)

    ev_idx = ec.index  # full extended index for rolling calcs
    ev_reindexed = v.reindex(ev_idx)
    vma20 = ev_reindexed.rolling(20).mean()
    vmratio = ev_reindexed / vma20

    # RSI-14
    delta = ec.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs_ = gain / loss
    rsi = 100 - (100 / (1 + rs_))

    for day in wc.index:
        entry = {
            'ft_OBJECTID': eid,
            'ticker': t,
            'event_date': ev_date,
            'date': day,
            'day_relative': (day - ev_date).days,
            'close': float(wc[day]),
            'volume': float(wv[day]) if day in wv.index and pd.notna(wv[day]) else np.nan,
            'sma_20': float(sma20[day]) if day in sma20.index and pd.notna(sma20[day]) else np.nan,
            'sma_60': float(sma60[day]) if day in sma60.index and pd.notna(sma60[day]) else np.nan,
            'volatility_20d': float(vol20[day]) if day in vol20.index and pd.notna(vol20[day]) else np.nan,
            'momentum_20d': float(mom20[day]) if day in mom20.index and pd.notna(mom20[day]) else np.nan,
            'rsi_14': float(rsi[day]) if day in rsi.index and pd.notna(rsi[day]) else np.nan,
            'volume_ma_ratio': float(vmratio[day]) if day in vmratio.index and pd.notna(vmratio[day]) else np.nan,
            'promise_label': label,
        }

        # Macro: forward-fill up to this date
        mm = macro_ffill.loc[:day]
        if not mm.empty:
            last = mm.iloc[-1]
            entry['fed_funds_rate'] = float(last['Fed Funds Rate']) if pd.notna(last['Fed Funds Rate']) else np.nan
            entry['unemployment_rate'] = float(last['Unemployment Rate']) if pd.notna(last['Unemployment Rate']) else np.nan
        else:
            entry['fed_funds_rate'] = np.nan
            entry['unemployment_rate'] = np.nan

        trows.append(entry)

    if (idx + 1) % 25 == 0:
        print(f"    Processed {idx + 1}/{n_events} events …")

tseries = pd.DataFrame(trows)
tseries.to_csv(OUTPUT_TIMESERIES, index=False)
print(f"  Saved → {OUTPUT_TIMESERIES}")
print(f"  Shape: {tseries.shape[0]} rows × {tseries.shape[1]} cols")
if events_skipped:
    print(f"  Events skipped (private / no data): {events_skipped}")

# ============================================================
# STEP 5 — Summary
# ============================================================
print("\n" + "=" * 60)
print("FINAL SUMMARY")
print("=" * 60)
print(f"  Tickers downloaded:      {len(tickers)} → {tickers}")
print(f"  Date range:              {min_date.date()} → {max_date.date()}")
print(f"  Quarterly panel:         {qpanel.shape[0]} rows × {qpanel.shape[1]} cols")
print(f"  Timeseries features:     {tseries.shape[0]} rows × {tseries.shape[1]} cols")
print(f"  Events skipped (yfinance): {events_skipped}")
print()
print("  Events per status:")
status_counts = df['ft_status'].value_counts()
for s, c in status_counts.items():
    print(f"    {s}: {c}")
print()
print("  Events per ticker:")
ticker_counts = df['ticker'].value_counts()
for t, c in ticker_counts.items():
    print(f"    {t}: {c}")
print()
print("Done.")
