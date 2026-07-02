"""Per-capture ventilator feature extraction.

Aggregates the per-breath breath table from `breath_segment` into one summary
row per capture: mean + std of the standard monitored parameters

    Ti, Te, RR, I:E, Vt, PIP, PEEP

By default only complete breaths feed the summary (the trailing partial breath
of a capture has unreliable RR/I:E). See docs/features.md.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from breath_segment import segment_dataset, save_breaths

# feature name -> source column in the breath table
FEATURES = {
    "ti": "ti_sec",             # inspiratory time (s)
    "te": "te_sec",             # expiratory time (s)
    "rr": "rr_bpm",             # respiratory rate (breaths/min)
    "ie": "ie_ratio",           # I:E as Ti/Te
    "vt": "tidal_volume_ml",    # tidal volume (mL)
    "pip": "peak_pressure",     # peak inspiratory pressure (cmH2O)
    "peep": "peep",             # end-expiratory pressure (cmH2O)
}

FEATURE_COLUMNS = (
    ["patient_id", "raw_data", "n_breaths"]
    + [f"{name}_{stat}" for name in FEATURES for stat in ("mean", "std")]
)


def extract_features(breaths: pd.DataFrame, complete_only: bool = True) -> pd.DataFrame:
    """Aggregate a per-breath table into one summary row per capture.

    complete_only: drop the trailing partial breath (is_complete=False) first.
    Emits mean and (population) std for each feature; std is 0 for a single breath.
    """
    df = breaths
    if complete_only and "is_complete" in df.columns:
        df = df[df["is_complete"]]
    if df.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    g = df.groupby(["patient_id", "raw_data"], sort=False)
    out = pd.DataFrame({"n_breaths": g.size()})
    for name, col in FEATURES.items():
        out[f"{name}_mean"] = g[col].mean().round(2)
        out[f"{name}_std"] = g[col].std(ddof=0).round(2)
    return out.reset_index()[FEATURE_COLUMNS]


def features_from_dataset(
    data_dir: str | Path, complete_only: bool = True, **seg_kwargs
) -> pd.DataFrame:
    """Segment every capture in a directory, then extract per-capture features.

    seg_kwargs (min_breath_sec, baseline, hysteresis) pass through to
    breath_segment.segment_dataset.
    """
    breaths = segment_dataset(data_dir, **seg_kwargs)
    return extract_features(breaths, complete_only=complete_only)


def save_features(df: pd.DataFrame, path: str | Path) -> Path:
    """Persist the feature table (Parquet or CSV by extension); returns the path."""
    return save_breaths(df, path)


if __name__ == "__main__":
    import argparse

    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Extract per-capture ventilator features.")
    ap.add_argument("data_dir", nargs="?", default=root / "smart_icu_data", type=Path)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "output" / "features.csv",
                    help="output file (.csv or .parquet); default backend/output/features.csv")
    ap.add_argument("--min-breath-sec", type=float, default=0.0)
    ap.add_argument("--baseline", default="zero",
                    help='"zero" (default), "auto", "patient", or a numeric offset')
    ap.add_argument("--hysteresis", type=float, default=0.0)
    ap.add_argument("--all-breaths", action="store_true",
                    help="include the trailing partial breath of each capture")
    args = ap.parse_args()

    baseline = args.baseline
    if baseline not in ("zero", "auto", "patient"):
        baseline = float(baseline)
    feats = features_from_dataset(
        args.data_dir, complete_only=not args.all_breaths,
        min_breath_sec=args.min_breath_sec, baseline=baseline, hysteresis=args.hysteresis,
    )
    print(f"extracted features for {len(feats)} captures")
    written = save_features(feats, args.out)
    print(f"saved -> {written}")
