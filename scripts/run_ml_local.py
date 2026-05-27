#!/usr/bin/env python3
import os, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

os.environ["MPLBACKEND"] = "Agg"
os.chdir(str(REPO_ROOT))
import matplotlib
matplotlib.use("Agg")

from colab_ml_analysis import (
    run_car_analysis,
    run_sentiment_analysis,
    run_ml_classification,
    run_summary,
    load_data,
    DATA_DIR,
    FIG_DIR,
)

def main():
    print("=" * 60)
    print("   LOCAL ML ANALYSIS RUNNER")
    print(f"   DATA_DIR: {DATA_DIR}")
    print(f"   FIG_DIR:  {FIG_DIR}")
    print("=" * 60)

    es, deduped, qp, tsf = load_data()
    es_sorted, car_results = run_car_analysis(es)
    run_sentiment_analysis(deduped)
    window_labels = ["[-1,+1]", "[-5,+5]", "[-20,+60]"]
    ml_result = run_ml_classification(es, deduped, qp)
    run_summary(car_results, ml_result, window_labels)

    print("\n" + "=" * 70)
    print("   ALL DONE — Figures saved to reports/figures/")
    print("=" * 70)

if __name__ == "__main__":
    main()
