"""
gdelt_utils.py — Shared GDELT utility functions.

parse_v2_tone: Parse GDELT V2Tone format (comma-separated, first = avg tone).
"""

import pandas as pd


def parse_v2_tone(tone_str):
    """Parse GDELT V2Tone: comma-separated, first element is avg tone.

    Parameters
    ----------
    tone_str : str or NaN
        GDELT v2_tone string like "1.23,0.45,0.67,..."

    Returns
    -------
    float
        Average tone value, or NaN if unparseable.
    """
    try:
        return float(str(tone_str).split(',')[0])
    except (ValueError, TypeError, IndexError):
        return float('nan')
