"""Breath segmentation via zero-crossing of the Flow signal.

Convention: Flow > 0 = inspiration, Flow < 0 = expiration. A breath runs from
one inspiration onset (Flow crosses 0 upward) to the next. The expiration onset
is the Flow downward zero-crossing in between.

    insp_start ──inspiration──> insp_end(=exp_start) ──expiration──> exp_end(next insp_start)

Produces one row per breath. See docs/breath-segment.md for the schema.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from parser import SAMPLE_RATE_HZ, load_waveform, load_dataset, metadata_frame

BREATH_COLUMNS = [
    "patient_id", "raw_data", "breath_idx",
    "insp_start_idx", "insp_end_idx", "exp_end_idx",
    "t_insp_start", "t_insp_end", "t_exp_end",
    "ti_sec", "te_sec", "ie_ratio",
    "tidal_volume_ml", "peak_flow", "peak_pressure", "mean_pressure", "peep",
    "rr_bpm", "is_complete",
]


def estimate_baseline(flow: np.ndarray, q: float = 5.0) -> float:
    """Estimate the end-expiratory flow baseline (DC offset) as a low percentile.

    The true baseline is the end-expiratory point, the *low* end of the flow
    range. On this dataset inspiration dominates (~90% of samples), so a
    histogram mode / mean / median lands on the inspiratory plateau, not the
    baseline. The q-th percentile (default 5th) tracks the expiratory trough
    even when the whole signal is offset positive and never crosses zero.

    Pair with a `hysteresis` band: the offset alone over-segments noisy/flat
    captures, but a band wider than their noise amplitude zeroes them back out.
    """
    return float(np.percentile(flow, q))


def _detect_crossings(
    flow: np.ndarray, baseline: float = 0.0, hysteresis: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """Return (rising, falling) sample indices via a hysteresis state machine.

    Inspiration is entered when flow rises above `baseline + hysteresis`;
    expiration when it drops below `baseline - hysteresis`. The band rejects
    noise-driven false crossings near the baseline. A crossing index i is the
    first sample of the new phase.

    With baseline=0 and hysteresis=0 this reproduces pure zero-crossing.
    """
    upper = baseline + hysteresis
    lower = baseline - hysteresis
    rising: list[int] = []
    falling: list[int] = []
    state = "insp" if flow[0] > baseline else "exp"
    for i in range(1, len(flow)):
        if state == "exp" and flow[i] > upper:
            rising.append(i)
            state = "insp"
        elif state == "insp" and flow[i] <= lower:
            falling.append(i)
            state = "exp"
    return np.array(rising, dtype=int), np.array(falling, dtype=int)


def segment_capture(
    wf: pd.DataFrame,
    patient_id: str = "",
    raw_data: str = "",
    min_breath_sec: float = 0.0,
    baseline: str | float = "zero",
    hysteresis: float = 0.0,
) -> pd.DataFrame:
    """Segment one waveform DataFrame (from load_waveform) into breaths.

    min_breath_sec: drop breaths shorter than this (0 = no filter).
    baseline: "zero" (literal 0), "auto" (low-percentile offset), or a numeric offset.
    hysteresis: dead-band (L/min) around the baseline to reject noise crossings.
    """
    flow = wf["flow"].to_numpy()
    if baseline in ("auto", "patient"):
        # "patient" is resolved to a number by segment_dataset; if it reaches here
        # (single-capture call) it degrades to per-capture auto.
        base = estimate_baseline(flow)
    elif baseline == "zero":
        base = 0.0
    else:
        base = float(baseline)
    pressure = wf["pressure"].to_numpy()
    volume = wf["volume"].to_numpy()
    n = len(flow)

    rising, falling = _detect_crossings(flow, base, hysteresis)
    rows = []
    min_len = int(round(min_breath_sec * SAMPLE_RATE_HZ))

    for b, insp_start in enumerate(rising):
        # exp_end is the next inspiration onset; last breath runs to end of capture
        is_complete = b + 1 < len(rising)
        exp_end = rising[b + 1] if is_complete else n - 1

        # inspiration ends at the first falling crossing within this breath
        fall = falling[(falling > insp_start) & (falling <= exp_end)]
        insp_end = int(fall[0]) if len(fall) else exp_end

        if (exp_end - insp_start) < min_len:
            continue

        t_is = insp_start / SAMPLE_RATE_HZ
        t_ie = insp_end / SAMPLE_RATE_HZ
        t_ee = exp_end / SAMPLE_RATE_HZ
        ti = t_ie - t_is
        te = t_ee - t_ie
        period = t_ee - t_is
        seg = slice(insp_start, exp_end + 1)

        rows.append({
            "patient_id": patient_id,
            "raw_data": raw_data,
            "breath_idx": b,
            "insp_start_idx": int(insp_start),
            "insp_end_idx": int(insp_end),
            "exp_end_idx": int(exp_end),
            "t_insp_start": round(t_is, 3),
            "t_insp_end": round(t_ie, 3),
            "t_exp_end": round(t_ee, 3),
            "ti_sec": round(ti, 3),
            "te_sec": round(te, 3),
            "ie_ratio": round(ti / te, 3) if te > 0 else None,
            "tidal_volume_ml": round(float(np.nanmax(volume[seg]) - np.nanmin(volume[seg])), 2),
            "peak_flow": round(float(np.nanmax(flow[seg])), 2),
            "peak_pressure": round(float(np.nanmax(pressure[seg])), 2),
            "mean_pressure": round(float(np.nanmean(pressure[seg])), 2),
            "peep": round(float(np.nanmin(pressure[seg])), 2),
            "rr_bpm": round(60.0 / period, 1) if period > 0 else None,
            "is_complete": is_complete,
        })

    return pd.DataFrame(rows, columns=BREATH_COLUMNS)


def segment_dataset(
    data_dir: str | Path,
    min_breath_sec: float = 0.0,
    baseline: str | float = "zero",
    hysteresis: float = 0.0,
) -> pd.DataFrame:
    """Segment every capture referenced in a data directory into one breath table.

    baseline="patient" estimates one baseline per patient by pooling all of that
    patient's captures (vs "auto", which is per capture).
    """
    data_dir = Path(data_dir)
    meta = metadata_frame(load_dataset(data_dir))
    captures = meta.dropna(subset=["raw_data"])[["patient_id", "raw_data"]].drop_duplicates()

    # load each waveform once
    loaded = [(row["patient_id"], row["raw_data"], load_waveform(data_dir / row["raw_data"]))
              for _, row in captures.iterrows()]

    # per-patient baseline: pool all of a patient's flow, estimate one value
    patient_base: dict[str, float] = {}
    if baseline == "patient":
        pooled: dict[str, list] = {}
        for pid, _, wf in loaded:
            pooled.setdefault(pid, []).append(wf["flow"].to_numpy())
        patient_base = {pid: estimate_baseline(np.concatenate(fs)) for pid, fs in pooled.items()}

    frames = []
    for pid, raw, wf in loaded:
        base = patient_base[pid] if baseline == "patient" else baseline
        frames.append(segment_capture(wf, pid, raw, min_breath_sec, base, hysteresis))
    if not frames:
        return pd.DataFrame(columns=BREATH_COLUMNS)
    out = pd.concat(frames, ignore_index=True)
    out["is_complete"] = out["is_complete"].astype(bool)
    return out


def save_breaths(df: pd.DataFrame, path: str | Path) -> Path:
    """Save the breath table. Uses Parquet if the extension is .parquet and an
    engine is available, otherwise CSV. Returns the actual path written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        try:
            df.to_parquet(path, index=False)
            return path
        except (ImportError, ValueError):
            path = path.with_suffix(".csv")
            print(f"no parquet engine; falling back to CSV -> {path}")
    df.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    import argparse

    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Segment ventilator waveforms into breaths.")
    ap.add_argument("data_dir", nargs="?", default=root / "smart_icu_data", type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "output" / "breaths.csv",
                    help="output file (.csv or .parquet); default backend/output/breaths.csv")
    ap.add_argument("--min-breath-sec", type=float, default=0.0)
    ap.add_argument("--baseline", default="zero",
                    help='"zero" (default), "auto" (per-capture low percentile), '
                         '"patient" (per-patient low percentile), or a numeric offset; '
                         'pair auto/patient with --hysteresis')
    ap.add_argument("--hysteresis", type=float, default=0.0,
                    help="dead-band (L/min) around baseline to reject noise crossings")
    args = ap.parse_args()

    baseline = args.baseline
    if baseline not in ("zero", "auto", "patient"):
        baseline = float(baseline)
    breaths = segment_dataset(args.data_dir, min_breath_sec=args.min_breath_sec,
                              baseline=baseline, hysteresis=args.hysteresis)
    n_partial = int((~breaths["is_complete"]).sum())
    print(f"segmented {breaths['raw_data'].nunique()} captures "
          f"into {len(breaths)} breaths "
          f"({n_partial} partial edge breaths)")

    written = save_breaths(breaths, args.out)
    print(f"saved {len(breaths)} breaths -> {written}")
