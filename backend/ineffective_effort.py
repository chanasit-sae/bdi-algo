"""Ineffective-effort (ineffective triggering) asynchrony detection.

Ineffective effort: the patient's inspiratory muscles contract, but the
ventilator's trigger threshold is never cleared, so no breath is delivered.
Unlike double-triggering, this can *never* appear as a row in the breath
table (by definition it didn't trigger) — it has to be found as a
sub-threshold deflection inside an already-recorded EXPIRATORY window.

There is no single agreed closed-form formula for this the way there is for
double-triggering (Thille's Te < 0.5*Ti). The gold-standard reference signal
is esophageal pressure, which this dataset doesn't have; with only
Flow/Pressure/Volume, detection has to work off a surrogate signature on
those waveforms. The approach here — require a concordant deflection in BOTH
Flow and Pressure — is a deliberately conservative heuristic (fewer false
positives at the cost of maybe missing effort that only shows clearly on one
signal), matching how automated-asynchrony-detection literature (e.g. Younes
et al.; Chen et al.'s review of automated methods) frames flow/pressure-only
detection when esophageal pressure is unavailable. Treat the three
thresholds below as a tunable starting point, not a validated clinical cutoff.

Signature used, per breath's own expiratory window (insp_end_idx -> exp_end_idx,
i.e. up to the next trigger onset — no cross-breath comparison needed):

  Flow:     expiratory flow normally decays smoothly toward baseline. An
            effort creates a transient "bump" — a local rise before the decay
            resumes — that never clears the real trigger band (if it did, it
            would already be a separate breath). Flagged if the bump's
            prominence (rise from the nearest preceding local minimum, looking
            back at most `bump_lookback_sec`) clears `flow_prominence` (L/min)
            but stays below `flow_prominence_max`: a bump as large as a real
            trigger peak (the app's own slope-mode PeakMin default, ~60 L/min)
            almost certainly means segmentation missed an actual breath (e.g.
            refractory suppression), not a genuinely failed effort, so it's
            excluded rather than flagged.
  Pressure: concurrently, the patient tugging against the circuit produces a
            small negative deflection ("dip") in airway pressure. Flagged if
            its prominence (fall from the nearest preceding local maximum,
            same bounded lookback) clears `pressure_prominence` (cmH2O) AND
            its trough sits within `concurrent_tol_sec` of the flow bump's peak.

Only pairs where BOTH signals independently clear their threshold AND occur
close together in time are flagged — the "combined flow + pressure"
requirement.

`bump_lookback_sec` matters more than it looks: prominence must be measured
against a *recent* reference point, not "the lowest/highest value anywhere
earlier in this multi-second expiratory window" — otherwise a late, tiny wiggle
gets credited with the window's entire earlier decay as its "rise", and
prominence values become wildly inflated and nearly meaningless. An earlier
version of this detector used an unbounded lookback (the whole window) and, on
this dataset, that meant ~98% of all flow candidates and ~43% of all pressure
candidates cleared the (unbounded-lookback) default thresholds — i.e. the
detector was firing on ordinary decay curve noise, not effort. Bounding the
lookback to ~0.4s (a plausible timescale for an effort's own rise/fall) and
recalibrating thresholds against the corrected distribution fixed this; see
docs/asynchrony.md for the measured before/after percentiles.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from parser import SAMPLE_RATE_HZ

IE_COLUMNS = [
    "patient_id", "raw_data", "breath_idx_a", "breath_idx_b",
    "t_start", "t_end", "t_flow_peak", "t_pressure_trough",
    "flow_prominence", "pressure_prominence", "dt_sec",
]


def _smooth(x: np.ndarray, w: int) -> np.ndarray:
    if w <= 1:
        return x
    k = np.ones(w) / w
    return np.convolve(x, k, mode="same")


def _local_maxima(x: np.ndarray) -> np.ndarray:
    """Indices of strict local maxima (sign change of the discrete derivative)."""
    if len(x) < 3:
        return np.array([], dtype=int)
    d = np.diff(x)
    idx = [i for i in range(1, len(d)) if d[i - 1] > 0 and d[i] <= 0]
    return np.array(idx, dtype=int)


def _local_minima(x: np.ndarray) -> np.ndarray:
    return _local_maxima(-x)


def _best_bump(x: np.ndarray, candidates: np.ndarray, min_prominence: float, lookback: int):
    """Highest-prominence candidate (value minus the min in the last `lookback`
    samples), or None. Bounding the lookback keeps prominence a *local*
    measure — otherwise a peak late in the window gets credited with the
    window's entire earlier decay as its "rise" (see module docstring)."""
    best = None
    for p in candidates:
        lo = max(0, p - lookback)
        prom = float(x[p] - x[lo : p + 1].min())
        if prom >= min_prominence and (best is None or prom > best[1]):
            best = (p, prom)
    return best


def _best_dip(x: np.ndarray, candidates: np.ndarray, min_prominence: float, lookback: int):
    """Highest-prominence dip (max in the last `lookback` samples minus the
    value), or None. See `_best_bump` for why the lookback is bounded."""
    best = None
    for p in candidates:
        lo = max(0, p - lookback)
        prom = float(x[lo : p + 1].max() - x[p])
        if prom >= min_prominence and (best is None or prom > best[1]):
            best = (p, prom)
    return best


def detect_ineffective_efforts(
    breaths: pd.DataFrame,
    flow: np.ndarray,
    pressure: np.ndarray,
    flow_prominence: float = 25.0,
    flow_prominence_max: float = 60.0,
    pressure_prominence: float = 1.5,
    concurrent_tol_sec: float = 0.3,
    bump_lookback_sec: float = 0.4,
    smooth_window: int = 3,
    edge_margin_sec: float = 0.12,
) -> pd.DataFrame:
    """Flag one ineffective effort per breath's expiratory window, at most.

    `breaths` is one capture's breath table from `breath_segment.segment_capture`
    (needs `insp_end_idx`, `exp_end_idx`, `breath_idx`, `is_complete`).
    `edge_margin_sec` excludes a small buffer at each window edge so the tail
    of a normal breath transition isn't mistaken for a bump/dip. `bump_lookback_sec`
    bounds how far back prominence is measured (see module docstring — this is
    what keeps the detector from firing on ordinary decay-curve noise).
    """
    margin = max(1, int(round(edge_margin_sec * SAMPLE_RATE_HZ)))
    lookback = max(1, int(round(bump_lookback_sec * SAMPLE_RATE_HZ)))
    rows = []

    for _, b in breaths.iterrows():
        i0 = int(b["insp_end_idx"]) + margin
        i1 = int(b["exp_end_idx"]) - margin
        if i1 - i0 < 3:
            continue

        fwin = _smooth(flow[i0 : i1 + 1], smooth_window)
        pwin = _smooth(pressure[i0 : i1 + 1], smooth_window)

        flow_hit = _best_bump(fwin, _local_maxima(fwin), flow_prominence, lookback)
        if flow_hit is None:
            continue
        fp_idx, fp_prom = flow_hit
        if fp_prom > flow_prominence_max:
            continue  # as big as a real trigger peak -> likely a missed breath, not a failed effort

        press_candidates = _local_minima(pwin)
        best_press = None
        for m in press_candidates:
            lo = max(0, m - lookback)
            prom = float(pwin[lo : m + 1].max() - pwin[m])
            if prom < pressure_prominence:
                continue
            dt = abs(m - fp_idx) / SAMPLE_RATE_HZ
            if dt > concurrent_tol_sec:
                continue
            if best_press is None or prom > best_press[1]:
                best_press = (m, prom, dt)
        if best_press is None:
            continue
        pp_idx, pp_prom, dt_sec = best_press

        t_flow_peak = (i0 + fp_idx) / SAMPLE_RATE_HZ
        t_pressure_trough = (i0 + pp_idx) / SAMPLE_RATE_HZ
        t_start = min(t_flow_peak, t_pressure_trough) - 0.15
        t_end = max(t_flow_peak, t_pressure_trough) + 0.15

        rows.append({
            "patient_id": b["patient_id"] if "patient_id" in b else "",
            "raw_data": b["raw_data"] if "raw_data" in b else "",
            "breath_idx_a": int(b["breath_idx"]),
            "breath_idx_b": int(b["breath_idx"]) + 1 if b["is_complete"] else None,
            "t_start": round(max(t_start, i0 / SAMPLE_RATE_HZ), 3),
            "t_end": round(t_end, 3),
            "t_flow_peak": round(t_flow_peak, 3),
            "t_pressure_trough": round(t_pressure_trough, 3),
            "flow_prominence": round(fp_prom, 1),
            "pressure_prominence": round(pp_prom, 2),
            "dt_sec": round(dt_sec, 3),
        })

    return pd.DataFrame(rows, columns=IE_COLUMNS)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from breath_segment import segment_dataset
    from parser import load_waveform

    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Detect ineffective-effort asynchrony from segmented breaths.")
    ap.add_argument("data_dir", nargs="?", default=root / "smart_icu_data", type=Path)
    ap.add_argument("--baseline", default="slope")
    ap.add_argument("--hysteresis", type=float, default=0.0)
    ap.add_argument("--flow-prominence", type=float, default=25.0)
    ap.add_argument("--pressure-prominence", type=float, default=1.5)
    ap.add_argument("--concurrent-tol-sec", type=float, default=0.3)
    ap.add_argument("--bump-lookback-sec", type=float, default=0.4)
    args = ap.parse_args()

    baseline = args.baseline
    if baseline not in ("zero", "auto", "patient", "slope"):
        baseline = float(baseline)
    breaths = segment_dataset(args.data_dir, baseline=baseline, hysteresis=args.hysteresis)

    parts = []
    for fname, grp in breaths.groupby("raw_data", sort=False):
        wf = load_waveform(args.data_dir / fname)
        parts.append(detect_ineffective_efforts(
            grp, wf["flow"].to_numpy(), wf["pressure"].to_numpy(),
            flow_prominence=args.flow_prominence,
            pressure_prominence=args.pressure_prominence,
            concurrent_tol_sec=args.concurrent_tol_sec,
            bump_lookback_sec=args.bump_lookback_sec,
        ))
    events = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=IE_COLUMNS)

    n_caps = events["raw_data"].nunique() if len(events) else 0
    print(f"{len(events)} ineffective efforts across {n_caps} captures "
          f"(flow>={args.flow_prominence} L/min, pressure>={args.pressure_prominence} cmH2O, "
          f"tol={args.concurrent_tol_sec}s)")
    if len(events):
        print(events.to_string(index=False))
