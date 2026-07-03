"""Flow starvation asynchrony detection.

Flow starvation: in volume-controlled ventilation with constant (square-wave)
flow, the machine delivers a fixed flow rate regardless of patient demand. If
the patient's own inspiratory drive exceeds that fixed flow, they keep pulling
against the circuit -- and since flow *can't* respond (it's locked by the
ventilator setting), the mismatch shows up on PRESSURE instead: the
pressure-time curve, which should rise in a smooth, convex arc toward peak,
gets pulled down mid-rise into a concave dip -- a "scoop" or "scalloped"
notch -- before continuing up to peak inspiratory pressure. That scooped
shape is the classic bedside sign of flow starvation.

Unlike double-triggering, there is no single agreed closed-form formula for
this (it's usually described qualitatively in the literature -- "scalloped /
concave pressure waveform" -- not as a specific threshold algorithm). This is
a heuristic starting point, calibrated against this dataset's own inspiratory
pressure noise floor (see the module-level percentile check in __main__)
rather than an arbitrary guess -- the same lesson learned from
ineffective_effort.py's first version, which fired on noise because its
prominence was measured against the wrong (unbounded) reference.

This looks at the INSPIRATORY phase (unlike double-triggering and ineffective
effort, which both key off the expiratory side), and is scored for every
breath, including the trailing partial one -- insp_start_idx/insp_end_idx are
always well-defined regardless of whether the capture cuts off before the
next breath.

Signature, per breath's inspiratory window (insp_start_idx -> insp_end_idx):
  A rise-dip-recovery "notch" in pressure: a local minimum with a real rise
  before it AND a real rise after it, both measured with a *bounded* lookback
  (at most `lookback_sec` in either direction) so prominence is a local
  measure, not "the highest/lowest point anywhere else in the window" (see
  ineffective_effort.py's docstring for exactly why that matters). Flagged if
  both the preceding rise and the following rise clear `dip_prominence`
  (cmH2O).

Optional secondary gate `require_constant_flow`: this signature specifically
means something in *constant-flow* delivery (volume control). If enabled,
also requires the inspiratory flow trace's own range to stay below
`flow_range_max` (L/min) -- filtering out cases where flow itself is
naturally varying (e.g. pressure-support's decelerating flow), where a
pressure dip doesn't carry the same "starvation" meaning. Off by default, the
same "mix is optional, primary signal stands alone" pattern as auto-PEEP's
`require_pressure`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from parser import SAMPLE_RATE_HZ

FLOW_STARVATION_COLUMNS = [
    "patient_id", "raw_data", "breath_idx_a", "t_start", "t_end", "t_dip",
    "dip_pressure", "prominence_before", "prominence_after", "flow_range",
]


def _smooth(x: np.ndarray, w: int) -> np.ndarray:
    if w <= 1:
        return x
    k = np.ones(w) / w
    return np.convolve(x, k, mode="same")


def _local_minima(x: np.ndarray) -> np.ndarray:
    """Indices of strict local minima (sign change of the discrete derivative)."""
    if len(x) < 3:
        return np.array([], dtype=int)
    d = np.diff(x)
    idx = [i for i in range(1, len(d)) if d[i - 1] < 0 and d[i] >= 0]
    return np.array(idx, dtype=int)


def _notch_prominence(x: np.ndarray, m: int, lookback: int) -> tuple[float, float]:
    """(prominence_before, prominence_after) for a candidate dip at index m:
    the rise from the local minimum up to the nearest peak on each side,
    bounded to `lookback` samples so it's a local measure."""
    lo = max(0, m - lookback)
    hi = min(len(x), m + lookback + 1)
    prom_before = float(x[lo : m + 1].max() - x[m])
    prom_after = float(x[m:hi].max() - x[m])
    return prom_before, prom_after


def detect_flow_starvation(
    breaths: pd.DataFrame,
    flow: np.ndarray,
    pressure: np.ndarray,
    dip_prominence: float = 2.0,
    lookback_sec: float = 0.4,
    edge_margin_sec: float = 0.12,
    require_constant_flow: bool = False,
    flow_range_max: float = 20.0,
) -> pd.DataFrame:
    """Flag one flow-starvation notch per breath's inspiratory window, at most.

    `breaths` is one capture's breath table from `breath_segment.segment_capture`
    (needs `insp_start_idx`, `insp_end_idx`, `t_insp_start`, `t_insp_end`,
    `breath_idx`). Scored for every breath, including the trailing partial one.
    """
    margin = max(1, int(round(edge_margin_sec * SAMPLE_RATE_HZ)))
    lookback = max(1, int(round(lookback_sec * SAMPLE_RATE_HZ)))
    rows = []

    for _, b in breaths.iterrows():
        i0 = int(b["insp_start_idx"]) + margin
        i1 = int(b["insp_end_idx"]) - margin
        if i1 - i0 < 3:
            continue

        pwin = _smooth(pressure[i0 : i1 + 1], 3)
        fwin = flow[i0 : i1 + 1]

        best = None
        for m in _local_minima(pwin):
            prom_before, prom_after = _notch_prominence(pwin, m, lookback)
            if prom_before < dip_prominence or prom_after < dip_prominence:
                continue
            score = min(prom_before, prom_after)
            if best is None or score > best[0]:
                best = (score, m, prom_before, prom_after)
        if best is None:
            continue
        _, m_idx, prom_before, prom_after = best

        flow_range = float(fwin.max() - fwin.min())
        if require_constant_flow and flow_range > flow_range_max:
            continue

        t_dip = (i0 + m_idx) / SAMPLE_RATE_HZ

        rows.append({
            "patient_id": b["patient_id"] if "patient_id" in b else "",
            "raw_data": b["raw_data"] if "raw_data" in b else "",
            "breath_idx_a": int(b["breath_idx"]),
            "t_start": round(float(b["t_insp_start"]), 3),
            "t_end": round(float(b["t_insp_end"]), 3),
            "t_dip": round(t_dip, 3),
            "dip_pressure": round(float(pwin[m_idx]), 2),
            "prominence_before": round(prom_before, 2),
            "prominence_after": round(prom_after, 2),
            "flow_range": round(flow_range, 1),
        })

    return pd.DataFrame(rows, columns=FLOW_STARVATION_COLUMNS)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from breath_segment import segment_dataset
    from parser import load_waveform

    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Detect flow-starvation asynchrony from segmented breaths.")
    ap.add_argument("data_dir", nargs="?", default=root / "smart_icu_data", type=Path)
    ap.add_argument("--baseline", default="slope")
    ap.add_argument("--hysteresis", type=float, default=0.0)
    ap.add_argument("--dip-prominence", type=float, default=2.0)
    ap.add_argument("--lookback-sec", type=float, default=0.4)
    ap.add_argument("--require-constant-flow", action="store_true")
    ap.add_argument("--flow-range-max", type=float, default=20.0)
    ap.add_argument("--calibrate", action="store_true",
                     help="print the dataset's real notch-prominence percentiles instead of detecting")
    args = ap.parse_args()

    baseline = args.baseline
    if baseline not in ("zero", "auto", "patient", "slope"):
        baseline = float(baseline)
    breaths = segment_dataset(args.data_dir, baseline=baseline, hysteresis=args.hysteresis)

    if args.calibrate:
        margin = max(1, int(round(0.12 * SAMPLE_RATE_HZ)))
        lookback = max(1, int(round(args.lookback_sec * SAMPLE_RATE_HZ)))
        proms = []
        for fname, grp in breaths.groupby("raw_data", sort=False):
            wf = load_waveform(args.data_dir / fname)
            pressure = wf["pressure"].to_numpy()
            for _, b in grp.iterrows():
                i0 = int(b["insp_start_idx"]) + margin
                i1 = int(b["insp_end_idx"]) - margin
                if i1 - i0 < 3:
                    continue
                pwin = _smooth(pressure[i0:i1 + 1], 3)
                for m in _local_minima(pwin):
                    pb, pa = _notch_prominence(pwin, m, lookback)
                    proms.append(min(pb, pa))
        proms = np.array(proms)
        print(f"n candidates: {len(proms)}")
        print("percentiles (50/75/85/90/95/99):",
              np.round(np.percentile(proms, [50, 75, 85, 90, 95, 99]), 2))
    else:
        parts = []
        for fname, grp in breaths.groupby("raw_data", sort=False):
            wf = load_waveform(args.data_dir / fname)
            parts.append(detect_flow_starvation(
                grp, wf["flow"].to_numpy(), wf["pressure"].to_numpy(),
                dip_prominence=args.dip_prominence, lookback_sec=args.lookback_sec,
                require_constant_flow=args.require_constant_flow,
                flow_range_max=args.flow_range_max,
            ))
        events = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=FLOW_STARVATION_COLUMNS)

        n_caps = events["raw_data"].nunique() if len(events) else 0
        print(f"{len(events)} flow-starvation notches across {n_caps} captures "
              f"(dip_prominence>={args.dip_prominence} cmH2O, lookback={args.lookback_sec}s"
              f"{', constant-flow required' if args.require_constant_flow else ''})")
        if len(events):
            print(events.to_string(index=False))
