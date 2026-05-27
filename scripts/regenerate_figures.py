#!/usr/bin/env python3
"""
regenerate_figures.py — Regenerates all paper figures (fig1-fig8) and LaTeX tables
using the enriched FracTracker-GDELT dataset.

Usage:
    /home/aidas/miniforge3/envs/data-analysis-env/bin/python3 scripts/regenerate_figures.py 2>&1
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path
import sys
import io

# ── Paths ──────────────────────────────────────────────────────────────
DEDUPED_PATH = Path("data/processed/fractracker_gdelt_deduped.csv")
BUILDOUT_PATH = Path("data/processed/buildout_promises_real.csv")
FIGURES_DIR = Path("reports/figures")

FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ── Plot style ─────────────────────────────────────────────────────────
plt.style.use('seaborn-v0_8-whitegrid')
COLORS = {
    'Operating': '#2ecc71',
    'Proposed': '#3498db',
    'Approved': '#f39c12',
    'Other': '#e74c3c',
}

# ── Data loading and parsing ──────────────────────────────────────────
def load_data():
    """Load and parse both datasets."""
    deduped = pd.read_csv(DEDUPED_PATH)
    buildout = pd.read_csv(BUILDOUT_PATH)

    # ── Parse v2_tone (first component = avg tone) ──
    for df, col in [(deduped, 'gdelt_v2_tone'), (buildout, 'v2_tone')]:
        df['tone_avg'] = df[col].astype(str).str.split(',').str[0].astype(float)

    # ── Parse ft_mw ──
    deduped['ft_mw_num'] = pd.to_numeric(deduped['ft_mw'], errors='coerce')

    # ── Status mapping ──
    status_map = {
        'Approved/Permitted/Under construction': 'Approved',
    }
    other_cats = {'Cancelled', 'Suspended', 'Expanding'}
    deduped['status_group'] = deduped['ft_status'].map(status_map).fillna(deduped['ft_status'])
    deduped.loc[deduped['status_group'].isin(other_cats), 'status_group'] = 'Other'

    # ── Parse dates ──
    # Buildout date: integer YYYYMMDDHHMMSS
    buildout['date_str'] = buildout['date'].astype(str)
    buildout['date_parsed'] = pd.to_datetime(buildout['date_str'], format='%Y%m%d%H%M%S', errors='coerce')
    buildout['year'] = buildout['date_parsed'].dt.year

    # GDELT date in deduped: float YYYYMMDDHHMMSS
    deduped['gdelt_date_str'] = deduped['gdelt_date'].astype(str).str.split('.').str[0]
    deduped['gdelt_date_parsed'] = pd.to_datetime(deduped['gdelt_date_str'], format='%Y%m%d%H%M%S', errors='coerce')
    deduped['gdelt_year'] = deduped['gdelt_date_parsed'].dt.year

    # Announcement date in deduped
    deduped['announcement_date_parsed'] = pd.to_datetime(deduped['announcement_date'], errors='coerce')
    deduped['announcement_year'] = deduped['announcement_date_parsed'].dt.year

    return deduped, buildout


# ── Figure 1: Events by Year ──────────────────────────────────────────
def fig1_events_by_year(deduped, buildout):
    """GDELT announcements by year, with matched subset overlay by ft_status."""
    fig, ax = plt.subplots(figsize=(10, 6))

    # Total per year from buildout
    year_counts = buildout['year'].value_counts().sort_index()
    years = year_counts.index
    totals = year_counts.values

    # Bar for totals
    bars = ax.bar(years, totals, color='#bdc3c7', label='Total announcements', width=0.6, alpha=0.7)

    # Matched subset by status from deduped
    status_order = ['Operating', 'Proposed', 'Approved', 'Other']
    status_colors = [COLORS[s] for s in status_order]

    # Get year breakdown from deduped by announcement_year
    deduped_year_status = deduped.groupby(['announcement_year', 'status_group']).size().unstack(fill_value=0)
    # Align with years
    for s in status_order:
        if s not in deduped_year_status.columns:
            deduped_year_status[s] = 0

    # Plot stacked bars for matched subset
    bottom = np.zeros(len(years))
    for s in status_order:
        vals = deduped_year_status[s].reindex(years, fill_value=0).values
        ax.bar(years, vals, bottom=bottom, color=COLORS[s], label=f'Matched — {s}', width=0.6, alpha=0.85)
        bottom += vals

    ax.set_xlabel('Year', fontsize=12)
    ax.set_ylabel('Number of Announcements', fontsize=12)
    ax.set_title('GDELT Buildout Announcements by Year', fontsize=14, fontweight='bold')
    ax.legend(fontsize=9, loc='upper left')
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / 'fig1_events_by_year.png', dpi=300, bbox_inches='tight')
    plt.close(fig)
    print("[OK] fig1_events_by_year.png")


# ── Figure 2: Top Companies ───────────────────────────────────────────
def fig2_top_companies(deduped, buildout):
    """Top 10 companies by GDELT count with keep rate overlay."""
    # Top 10 by count
    top10 = buildout['company'].value_counts().head(10)
    companies = top10.index.tolist()

    # Calculate keep rate: fraction of matched records with Operating status
    # Normalize company names for matching
    deduped['company_norm'] = deduped['gdelt_company'].str.lower().str.strip()
    buildout['company_norm'] = buildout['company'].str.lower().str.strip()

    keep_rates = []
    for c in companies:
        c_norm = c.lower().strip()
        matched = deduped[deduped['company_norm'] == c_norm]
        if len(matched) > 0:
            keep_rate = (matched['status_group'] == 'Operating').mean()
        else:
            keep_rate = 0.0
        keep_rates.append(keep_rate)

    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Horizontal bar
    y_pos = range(len(companies))
    ax1.barh(y_pos, top10.values, color='#3498db', alpha=0.7, label='GDELT Count')
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(companies, fontsize=10)
    ax1.set_xlabel('Number of Announcements', fontsize=12)
    ax1.set_title('Top 10 Companies by Announcement Count with Keep Rate', fontsize=14, fontweight='bold')

    # Overlay keep rate as colored dots/line
    ax2 = ax1.twiny()
    ax2.scatter(keep_rates, y_pos, color='#e74c3c', s=80, zorder=5, label='Keep Rate (matched)')
    ax2.set_xlabel('Keep Rate (matched subset)', fontsize=12, color='#e74c3c')
    ax2.tick_params(axis='x', colors='#e74c3c')
    ax2.set_xlim(0, 1)

    # Add value labels
    for i, (count, kr) in enumerate(zip(top10.values, keep_rates)):
        ax1.text(count + 15, i, str(count), va='center', fontsize=9)
        ax2.text(kr + 0.02, i, f'{kr:.0%}', va='center', fontsize=9, color='#e74c3c')

    fig.legend(loc='lower right', fontsize=9)
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / 'fig2_top_companies.png', dpi=300, bbox_inches='tight')
    plt.close(fig)
    print("[OK] fig2_top_companies.png")


# ── Figure 5: MW Analysis ─────────────────────────────────────────────
def fig5_mw_analysis(deduped):
    """Box plot of ft_mw by ft_status (Operating/Proposed/Approved)."""
    fig, ax = plt.subplots(figsize=(10, 6))

    # Filter to main status groups, exclude Other
    plot_data = deduped[deduped['status_group'].isin(['Operating', 'Proposed', 'Approved'])].copy()
    plot_data = plot_data.dropna(subset=['ft_mw_num'])

    status_order = ['Operating', 'Proposed', 'Approved']
    box_data = [plot_data[plot_data['status_group'] == s]['ft_mw_num'].values for s in status_order]

    bp = ax.boxplot(box_data, tick_labels=status_order, patch_artist=True, widths=0.5)

    for patch, color in zip(bp['boxes'], [COLORS[s] for s in status_order]):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    # Add individual points
    for i, (s, data) in enumerate(zip(status_order, box_data)):
        jitter = np.random.normal(0, 0.04, len(data))
        ax.scatter(np.full_like(data, i + 1) + jitter, data, alpha=0.4, s=20, color=COLORS[s], zorder=3)

    ax.set_ylabel('MW Capacity', fontsize=12)
    ax.set_title('MW Capacity Distribution by Facility Status (FracTracker)', fontsize=14, fontweight='bold')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / 'fig5_mw_analysis.png', dpi=300, bbox_inches='tight')
    plt.close(fig)
    print("[OK] fig5_mw_analysis.png")


# ── Figure 6: State Distribution ──────────────────────────────────────
def fig6_state_distribution(deduped):
    """Stacked horizontal bar: top 10 states colored by ft_status."""
    # Top 10 states from deduped
    state_counts = deduped['gdelt_location_state'].value_counts().head(10)
    states = state_counts.index.tolist()[::-1]  # reverse for horizontal bar

    fig, ax = plt.subplots(figsize=(10, 7))

    status_order = ['Operating', 'Proposed', 'Approved', 'Other']

    # Build stacked data
    state_status = deduped.groupby(['gdelt_location_state', 'status_group']).size().unstack(fill_value=0)
    for s in status_order:
        if s not in state_status.columns:
            state_status[s] = 0

    y_pos = range(len(states))
    bottom = np.zeros(len(states))
    for s in status_order:
        vals = state_status[s].reindex(states, fill_value=0).values
        ax.barh(y_pos, vals, left=bottom, color=COLORS[s], label=s, height=0.6)
        bottom += vals

    ax.set_yticks(y_pos)
    ax.set_yticklabels(states, fontsize=11)
    ax.set_xlabel('Number of Facilities', fontsize=12)
    ax.set_title('Top 10 States by Facility Count (FracTracker Matches)', fontsize=14, fontweight='bold')
    ax.legend(fontsize=10, loc='lower right')
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    # Add count labels
    for i, s in enumerate(states):
        total = int(state_status.loc[s, status_order].sum())
        ax.text(total + 0.3, i, str(total), va='center', fontsize=9)

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / 'fig6_state_distribution.png', dpi=300, bbox_inches='tight')
    plt.close(fig)
    print("[OK] fig6_state_distribution.png")


# ── Figure 7: Confidence Sources ──────────────────────────────────────
def fig7_confidence_sources(deduped, buildout):
    """Pie chart of GDELT confidence levels + bar of top source domains."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Pie chart of confidence levels from buildout
    conf_counts = buildout['confidence'].value_counts()
    colors_pie = ['#2ecc71', '#f39c12', '#e74c3c']
    explode = (0.02, 0.02, 0.02)
    wedges, texts, autotexts = ax1.pie(
        conf_counts.values, labels=conf_counts.index,
        autopct='%1.1f%%', colors=colors_pie, explode=explode,
        startangle=90, textprops={'fontsize': 11}
    )
    for t in autotexts:
        t.set_fontweight('bold')
    ax1.set_title('GDELT Confidence Levels', fontsize=13, fontweight='bold')

    # Bar of top source domains from buildout
    domain_counts = buildout['source_domain'].value_counts().head(10)
    domains = domain_counts.index.tolist()
    # Shorten domain names for display
    short_domains = [d.replace('datacenterdynamics.com', 'datacenterdynamics')
                      .replace('datacenterknowledge.com', 'datacenterknowledge')
                      .replace('siliconangle.com', 'siliconangle') for d in domains]

    bars = ax2.barh(range(len(domains)), domain_counts.values, color='#3498db', alpha=0.7)
    ax2.set_yticks(range(len(domains)))
    ax2.set_yticklabels(short_domains, fontsize=10)
    ax2.set_xlabel('Number of Announcements', fontsize=12)
    ax2.set_title('Top Source Domains', fontsize=13, fontweight='bold')

    for i, (bar, val) in enumerate(zip(bars, domain_counts.values)):
        ax2.text(val + 20, bar.get_y() + bar.get_height() / 2, str(val),
                 va='center', fontsize=9)

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / 'fig7_confidence_sources.png', dpi=300, bbox_inches='tight')
    plt.close(fig)
    print("[OK] fig7_confidence_sources.png")


# ── Figure 8: Tone Correlation ────────────────────────────────────────
def fig8_tone_correlation(deduped):
    """Box/violin plot of gdelt_v2_tone by ft_status from deduped data."""
    fig, ax = plt.subplots(figsize=(10, 6))

    plot_data = deduped.dropna(subset=['tone_avg'])
    status_order = ['Operating', 'Proposed', 'Approved', 'Other']

    # Violin plot with inner box
    violin_data = [plot_data[plot_data['status_group'] == s]['tone_avg'].values for s in status_order]

    # Filter empty datasets
    valid_indices = [i for i, d in enumerate(violin_data) if len(d) > 0]
    valid_statuses = [status_order[i] for i in valid_indices]
    valid_data = [violin_data[i] for i in valid_indices]
    valid_colors = [COLORS[s] for s in valid_statuses]

    vp = ax.violinplot(valid_data, positions=range(len(valid_statuses)), showmeans=True,
                        showmedians=True, widths=0.6)

    for i, body in enumerate(vp['bodies']):
        body.set_facecolor(valid_colors[i])
        body.set_alpha(0.5)
    vp['cmeans'].set_color('darkred')
    vp['cmedians'].set_color('darkblue')

    # Add individual points
    for i, (s, data) in enumerate(zip(valid_statuses, valid_data)):
        jitter = np.random.normal(0, 0.04, len(data))
        ax.scatter(np.full_like(data, i) + jitter, data, alpha=0.3, s=15, color=COLORS[s], zorder=3)

    ax.set_xticks(range(len(valid_statuses)))
    ax.set_xticklabels(valid_statuses, fontsize=11)
    ax.set_ylabel('Average Tone (GDELT V2Tone)', fontsize=12)
    ax.set_title('Announcement Tone by Facility Status', fontsize=14, fontweight='bold')
    ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)

    # Add sample sizes
    for i, s in enumerate(valid_statuses):
        n = len(valid_data[i])
        ax.text(i, ax.get_ylim()[1] * 0.95, f'n={n}', ha='center', fontsize=9,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / 'fig8_tone_correlation.png', dpi=300, bbox_inches='tight')
    plt.close(fig)
    print("[OK] fig8_tone_correlation.png")


# ══════════════════════════════════════════════════════════════════════
# LaTeX Tables
# ══════════════════════════════════════════════════════════════════════

def table_geographic(deduped):
    """Geographic distribution: top 10 states by count, breakdown by status."""
    status_order = ['Operating', 'Proposed', 'Approved', 'Other']

    state_status = deduped.groupby(['gdelt_location_state', 'status_group']).size().unstack(fill_value=0)
    for s in status_order:
        if s not in state_status.columns:
            state_status[s] = 0
    state_status['Total'] = state_status[status_order].sum(axis=1)
    state_status = state_status.sort_values('Total', ascending=False).head(10)

    print(r"\begin{table*}[t]")
    print(r"\centering")
    print(r"\caption{Geographic Distribution of FracTracker-Validated Facilities (Top 10 States)}")
    print(r"\label{tab:geo_distribution}")
    print(r"\footnotesize")
    print(r"\begin{tabular}{l" + "".join(["r"] * (len(status_order) + 1)) + r"}")
    print(r"\toprule")
    header = r"\textbf{State}" + "".join([f" & \\textbf{{{s}}}" for s in status_order]) + r" & \textbf{Total} \\"
    print(header)
    print(r"\midrule")

    total_all = [0] * (len(status_order) + 1)
    for state, row in state_status.iterrows():
        vals = [int(row[s]) for s in status_order] + [int(row['Total'])]
        total_all = [total_all[i] + vals[i] for i in range(len(vals))]
        line = f"{state} & " + " & ".join([str(v) for v in vals]) + r" \\"
        print(line)

    print(r"\midrule")
    line = r"\textbf{Total} & " + " & ".join([str(v) for v in total_all]) + r" \\"
    print(line)
    print(r"\bottomrule")
    print(r"\end{tabular}")
    print(r"\footnotesize \textit{Note:} Only states with matched FracTracker records shown.")
    print(r"\end{table*}")
    print()
    print("[OK] Table: Geographic Distribution")


def table_label_distribution(deduped):
    """Label distribution: by company, total vs Operating/Proposed/Approved/Other."""
    status_order = ['Operating', 'Proposed', 'Approved', 'Other']

    # Group by company (gdelt_company)
    company_status = deduped.groupby(['gdelt_company', 'status_group']).size().unstack(fill_value=0)
    for s in status_order:
        if s not in company_status.columns:
            company_status[s] = 0
    company_status['Total'] = company_status[status_order].sum(axis=1)
    company_status = company_status.sort_values('Total', ascending=False)

    print(r"\begin{table*}[t]")
    print(r"\centering")
    print(r"\caption{Facility Status Distribution by Company (FracTracker Matches)}")
    print(r"\label{tab:label_distribution}")
    print(r"\footnotesize")
    print(r"\begin{tabular}{l" + "".join(["r"] * (len(status_order) + 1)) + r"}")
    print(r"\toprule")
    header = r"\textbf{Company}" + "".join([f" & \\textbf{{{s}}}" for s in status_order]) + r" & \textbf{Total} \\"
    print(header)
    print(r"\midrule")

    total_all = [0] * (len(status_order) + 1)
    for company, row in company_status.iterrows():
        vals = [int(row[s]) for s in status_order] + [int(row['Total'])]
        total_all = [total_all[i] + vals[i] for i in range(len(vals))]
        line = f"{company} & " + " & ".join([str(v) for v in vals]) + r" \\"
        print(line)

    print(r"\midrule")
    line = r"\textbf{Total} & " + " & ".join([str(v) for v in total_all]) + r" \\"
    print(line)
    print(r"\bottomrule")
    print(r"\end{tabular}")
    print(r"\footnotesize \textit{Note:} Matched records only (N = " + str(len(deduped)) + ").")
    print(r"\end{table*}")
    print()
    print("[OK] Table: Label Distribution")


def table_characteristics(deduped):
    """Characteristics by outcome: MW (mean, median), tone (mean, std) by ft_status."""
    status_order = ['Operating', 'Proposed', 'Approved', 'Other']

    print(r"\begin{table*}[t]")
    print(r"\centering")
    print(r"\caption{Characteristics by Facility Status}")
    print(r"\label{tab:characteristics}")
    print(r"\footnotesize")
    print(r"\begin{tabular}{lrrrrr}")
    print(r"\toprule")
    print(r"\textbf{Characteristic} & \textbf{Operating} & \textbf{Proposed} & \textbf{Approved} & \textbf{Other} & \textbf{All} \\")
    print(r"\midrule")

    # MW Capacity
    print(r"\multicolumn{6}{l}{\textit{MW Capacity}} \\")
    for stat_name, func in [('N', lambda x: len(x.dropna())),
                             ('Mean', lambda x: f'{x.mean():.2f}'),
                             ('Median', lambda x: f'{x.median():.2f}'),
                             ('Std Dev', lambda x: f'{x.std():.2f}')]:
        vals = []
        all_vals = deduped['ft_mw_num'].dropna()
        for s in status_order:
            subset = deduped[deduped['status_group'] == s]['ft_mw_num']
            vals.append(str(func(subset)))
        vals.append(str(func(all_vals)))
        line = f"    {stat_name} & " + " & ".join(vals) + r" \\"
        print(line)

    print(r"\midrule")

    # Tone
    print(r"\multicolumn{6}{l}{\textit{Tone (gdelt\_v2\_tone)}} \\")
    for stat_name, func in [('N', lambda x: len(x.dropna())),
                             ('Mean', lambda x: f'{x.mean():.2f}'),
                             ('Median', lambda x: f'{x.median():.2f}'),
                             ('Std Dev', lambda x: f'{x.std():.2f}')]:
        vals = []
        all_vals = deduped['tone_avg'].dropna()
        for s in status_order:
            subset = deduped[deduped['status_group'] == s]['tone_avg']
            vals.append(str(func(subset)))
        vals.append(str(func(all_vals)))
        line = f"    {stat_name} & " + " & ".join(vals) + r" \\"
        print(line)

    print(r"\bottomrule")
    print(r"\end{tabular}")
    print(r"\footnotesize \textit{Note:} N = " + str(len(deduped)) + " matched records.")
    print(r"\end{table*}")
    print()
    print("[OK] Table: Characteristics")


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Regenerating figures and tables")
    print("=" * 60)
    print()

    deduped, buildout = load_data()

    print(f"Deduped dataset: {len(deduped)} rows")
    print(f"Buildout dataset: {len(buildout)} rows")
    print()

    # ── Generate figures ──
    print("── Figures ──")
    fig1_events_by_year(deduped, buildout)
    fig2_top_companies(deduped, buildout)
    fig5_mw_analysis(deduped)
    fig6_state_distribution(deduped)
    fig7_confidence_sources(deduped, buildout)
    fig8_tone_correlation(deduped)
    print()

    # ── Generate LaTeX tables ──
    print("── LaTeX Tables ──")
    print()
    table_geographic(deduped)
    table_label_distribution(deduped)
    table_characteristics(deduped)

    print()
    print("=" * 60)
    print("Done.")
    print("=" * 60)


if __name__ == '__main__':
    main()
