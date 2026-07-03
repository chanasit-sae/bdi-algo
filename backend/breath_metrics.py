"""Derived per-breath metrics beyond the core segmentation table.

`breath_segment.py` emits the basic table (timing, tidal volume, peak/mean
pressure, PEEP, rate). This module takes those breath rows plus the capture
waveform and derives the *secondary* quantities a single breath still contains:
split inspiratory/expiratory flow & volume, leak, and the pressure-derived
respiratory mechanics (plateau, driving pressure, compliance, resistance).

Units on this dataset: flow L/min, pressure cmH2O, volume mL, 25 Hz.
Pure numpy; reuses `SAMPLE_RATE_HZ` / `load_waveform` from parser.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from parser import SAMPLE_RATE_HZ, load_waveform

# End-inspiratory pause detection: flow within +-PAUSE_FLOW_LPM of zero counts
# as "no flow"; a trailing no-flow run of at least PAUSE_MIN_SEC at the end of
# inspiration is treated as a plateau (used for static compliance / resistance).
PAUSE_FLOW_LPM = 5.0
PAUSE_MIN_SEC = 0.08  # >= 2 samples at 25 Hz

METRIC_COLUMNS = [
    "cycle_time_sec", "duty_cycle",
    "mean_insp_flow", "peak_insp_flow", "peak_exp_flow",
    "time_to_peak_flow_sec", "end_exp_flow", "flow_shape_ratio",
    "vti_ml", "vte_ml", "leak_ml",
    "pip_cmh2o", "plateau_pressure_cmh2o", "driving_pressure_cmh2o",
    "static_compliance_ml_cmh2o", "dynamic_compliance_ml_cmh2o",
    "resistance_cmh2o_l_s",
]


def _r(v, d=2):
    """Round, passing None/NaN through unchanged."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return round(float(v), d)


def _plateau_pressure(pressure: np.ndarray, flow: np.ndarray,
                      i0: int, i1: int) -> float | None:
    """Mean pressure over an end-inspiratory pause, or None if there is none.

    Looks for a trailing run of near-zero flow (|flow| < PAUSE_FLOW_LPM) ending
    at the inspiration→expiration boundary. The single boundary sample is always
    near zero, so the PAUSE_MIN_SEC floor keeps a plain crossing from counting.
    """
    if i1 <= i0:
        return None
    still = np.abs(flow[i0:i1 + 1]) < PAUSE_FLOW_LPM
    run = 0
    k = len(still) - 1
    while k >= 0 and still[k]:
        run += 1
        k -= 1
    if run / SAMPLE_RATE_HZ < PAUSE_MIN_SEC:
        return None
    seg = slice(i0 + len(still) - run, i1 + 1)
    return float(np.nanmean(pressure[seg]))


def breath_metrics(row: dict, flow: np.ndarray, pressure: np.ndarray,
                   volume: np.ndarray) -> dict:
    """Derived metrics for one breath given the capture's waveform arrays.

    `row` is a breath record from `segment_capture` (needs the *_idx columns;
    reuses `tidal_volume_ml` / `peep` when present).
    """
    i0 = int(row["insp_start_idx"])
    i1 = int(row["insp_end_idx"])
    i2 = int(row["exp_end_idx"])
    fi = flow[i0:i1 + 1]
    fe = flow[i1:i2 + 1]

    period = (i2 - i0) / SAMPLE_RATE_HZ
    ti = (i1 - i0) / SAMPLE_RATE_HZ

    # --- flow ---
    peak_insp = float(np.nanmax(fi)) if fi.size else None
    peak_exp = float(-np.nanmin(fe)) if fe.size else None  # magnitude of trough
    mean_insp = float(np.nanmean(fi)) if fi.size else None
    ttp = float(np.nanargmax(fi)) / SAMPLE_RATE_HZ if fi.size else None
    end_exp_flow = float(flow[i2])
    shape = (peak_insp / mean_insp) if (mean_insp and mean_insp > 0) else None

    # --- volume (mL) from the volume channel's own excursion ---
    # It rises to a peak at end-inspiration then falls on expiration. Splitting
    # at the volume peak (not the flow crossing) keeps vti/vte consistent with
    # tidal_volume_ml (= max-min); leak = inspired - returned expired.
    vb = volume[i0:i2 + 1]
    pk = int(np.nanargmax(vb))
    vti = float(vb[pk] - np.nanmin(vb[:pk + 1]))      # rise into the lungs
    vte = float(vb[pk] - np.nanmin(vb[pk:]))          # fall back out
    leak = vti - vte
    vt = row.get("tidal_volume_ml")
    vt = vti if vt is None else float(vt)

    # --- pressure mechanics (cmH2O) ---
    pip = float(np.nanmax(pressure[i0:i1 + 1])) if fi.size else None
    peep = row.get("peep")
    peep = float(np.nanmin(pressure[i0:i2 + 1])) if peep is None else float(peep)
    plat = _plateau_pressure(pressure, flow, i0, i1)
    driving = (plat - peep) if plat is not None else None
    cstat = (vt / driving) if (driving is not None and driving > 0) else None
    cdyn = (vt / (pip - peep)) if (pip is not None and pip - peep > 0) else None
    # resistance = (PIP - Pplat) / peak inspiratory flow; L/min -> L/s
    res = None
    if plat is not None and peak_insp and peak_insp > 0:
        res = (pip - plat) / (peak_insp / 60.0)

    return {
        "cycle_time_sec": _r(period, 3),
        "duty_cycle": _r(ti / period, 3) if period > 0 else None,
        "mean_insp_flow": _r(mean_insp),
        "peak_insp_flow": _r(peak_insp),
        "peak_exp_flow": _r(peak_exp),
        "time_to_peak_flow_sec": _r(ttp, 3),
        "end_exp_flow": _r(end_exp_flow),
        "flow_shape_ratio": _r(shape),
        "vti_ml": _r(vti, 1),
        "vte_ml": _r(vte, 1),
        "leak_ml": _r(leak, 1),
        "pip_cmh2o": _r(pip),
        "plateau_pressure_cmh2o": _r(plat),
        "driving_pressure_cmh2o": _r(driving),
        "static_compliance_ml_cmh2o": _r(cstat),
        "dynamic_compliance_ml_cmh2o": _r(cdyn),
        "resistance_cmh2o_l_s": _r(res),
    }


def add_metrics(breaths: pd.DataFrame, wf: pd.DataFrame) -> pd.DataFrame:
    """Append the derived-metric columns to a breath table for ONE capture."""
    if breaths.empty:
        for c in METRIC_COLUMNS:
            breaths[c] = pd.Series(dtype="float64")
        return breaths
    flow = wf["flow"].to_numpy()
    pressure = wf["pressure"].to_numpy()
    volume = wf["volume"].to_numpy()
    recs = [breath_metrics(r, flow, pressure, volume)
            for r in breaths.to_dict("records")]
    m = pd.DataFrame(recs, index=breaths.index, columns=METRIC_COLUMNS)
    return pd.concat([breaths, m], axis=1)


def add_metrics_dataset(breaths: pd.DataFrame, data_dir: str | Path) -> pd.DataFrame:
    """Append derived metrics to a multi-capture breath table.

    Loads each referenced capture's waveform once (grouped by raw_data).
    """
    data_dir = Path(data_dir)
    if breaths.empty:
        return add_metrics(breaths, pd.DataFrame(columns=["flow", "pressure", "volume"]))
    parts = []
    for fname, grp in breaths.groupby("raw_data", sort=False):
        wf = load_waveform(data_dir / fname)
        parts.append(add_metrics(grp.copy(), wf))
    return pd.concat(parts).sort_index()


if __name__ == "__main__":
    import argparse

    from breath_segment import segment_dataset, save_breaths

    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(
        description="Segment waveforms and append derived per-breath metrics.")
    ap.add_argument("data_dir", nargs="?", default=root / "smart_icu_data", type=Path)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent / "output" / "breaths_metrics.csv")
    ap.add_argument("--baseline", default="zero")
    ap.add_argument("--hysteresis", type=float, default=0.0)
    args = ap.parse_args()

    baseline = args.baseline
    if baseline not in ("zero", "auto", "patient", "slope"):
        baseline = float(baseline)
    breaths = segment_dataset(args.data_dir, baseline=baseline,
                              hysteresis=args.hysteresis)
    enriched = add_metrics_dataset(breaths, args.data_dir)
    path = save_breaths(enriched, args.out)
    print(f"{len(enriched)} breaths x {enriched.shape[1]} cols -> {path}")
