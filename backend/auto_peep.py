"""Auto-PEEP (intrinsic PEEP / air trapping) detection from flow + pressure.

Auto-PEEP is dynamic hyperinflation: the lung does not fully empty before the
next breath begins, so gas is trapped and end-expiratory alveolar pressure sits
above the set PEEP. It is the physiological opposite of the short-Te double
trigger in `asynchrony.py` -- here expiration is *too incomplete*, not too short.

Neither waveform alone is specific, so this detector requires the two signals to
agree ("flow + pressure mix"):

  Flow (air trapping): expiratory flow fails to return to the zero baseline
      before the next inspiration. For breath i,
          residual_frac = (z_ref - flow[exp_end]) / (z_ref - peak_exp_flow)
      is the fraction of the expiratory flow magnitude still present at the end
      of expiration. z_ref is a capture-level estimate of true zero flow taken
      as a high percentile of every breath's end-expiratory flow -- the breaths
      that empty completely settle at true zero, trapped breaths stay below it.
      (The onset-derived segmentation baseline must NOT be used here: it is the
      median end-expiratory level and would zero out the very residual we test;
      see breath_segment.estimate_baseline_from_onsets.)

  Pressure (dynamic hyperinflation): end-expiratory airway pressure sits above
      the set PEEP. set_peep is a low percentile of every breath's
      end-expiratory pressure (the best-emptied breaths reach set PEEP), and
          peep_delta = pressure[exp_end] - set_peep
      approximates the intrinsic PEEP contribution in cmH2O.

A breath is flagged when residual_frac > flow_frac AND its absolute residual
flow > flow_abs (noise floor) AND peep_delta > peep_min (require_pressure=True,
the default). `peep_delta` is always reported so a flow-only screen can be
reviewed too.

Only complete breaths are scored -- the trailing partial breath's expiratory end
is the capture edge, not a real end-expiration.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

AUTO_PEEP_COLUMNS = [
    "patient_id", "raw_data", "breath_idx",
    "t_insp_start", "t_exp_end", "ti_sec", "te_sec",
    "eef", "peak_exp_flow", "z_ref", "flow_residual_frac",
    "eep", "set_peep", "peep_delta", "pressure_flag",
]


def detect_auto_peep(
    wf: pd.DataFrame,
    breaths: pd.DataFrame,
    flow_frac: float = 0.15,
    flow_abs: float = 2.0,
    peep_min: float = 1.0,
    require_pressure: bool = True,
    zero_pct: float = 75.0,
    setpeep_pct: float = 10.0,
) -> pd.DataFrame:
    """Flag breaths in one capture showing auto-PEEP (air trapping).

    `wf` is the capture waveform from `parser.load_waveform` (flow/pressure).
    `breaths` is the same capture's table from `breath_segment.segment_capture`
    (`insp_end_idx`, `exp_end_idx`, `is_complete`, timing/index columns used).
    Returns one row per flagged breath; empty if fewer than 2 complete breaths.
    """
    flow = wf["flow"].to_numpy()
    pressure = wf["pressure"].to_numpy()
    n = len(flow)

    b = breaths.reset_index(drop=True)
    complete = b[b["is_complete"]] if "is_complete" in b else b
    if len(complete) < 2:
        return pd.DataFrame(columns=AUTO_PEEP_COLUMNS)

    # Per-breath end-expiratory flow / pressure at the last expiratory sample.
    eef_all, eep_all = [], []
    for _, row in complete.iterrows():
        j = min(int(row["exp_end_idx"]), n - 1)
        eef_all.append(float(flow[j]))
        eep_all.append(float(pressure[j]))

    # Capture-level references: true-zero flow (high pct of EEF) and set PEEP
    # (low pct of EEP). Both are data-driven so no absolute calibration needed.
    z_ref = float(np.percentile(eef_all, zero_pct))
    set_peep = float(np.percentile(eep_all, setpeep_pct))

    rows = []
    for _, row in complete.iterrows():
        insp_end = int(row["insp_end_idx"])
        exp_end = min(int(row["exp_end_idx"]), n - 1)
        if exp_end <= insp_end:
            continue

        exp_flow = flow[insp_end:exp_end + 1]
        peak_exp_flow = float(np.nanmin(exp_flow))  # most negative = peak exp
        eef = float(flow[exp_end])
        eep = float(pressure[exp_end])

        residual = z_ref - eef            # >0 = flow still expiring at end
        peak_mag = z_ref - peak_exp_flow  # full expiratory flow magnitude
        if peak_mag <= 0:
            continue
        residual_frac = residual / peak_mag

        peep_delta = eep - set_peep
        pressure_flag = peep_delta > peep_min

        flow_hit = residual_frac > flow_frac and residual > flow_abs
        if not flow_hit:
            continue
        if require_pressure and not pressure_flag:
            continue

        rows.append({
            "patient_id": row["patient_id"] if "patient_id" in row else "",
            "raw_data": row["raw_data"] if "raw_data" in row else "",
            "breath_idx": int(row["breath_idx"]),
            "t_insp_start": float(row["t_insp_start"]),
            "t_exp_end": float(row["t_exp_end"]),
            "ti_sec": round(float(row["ti_sec"]), 3),
            "te_sec": round(float(row["te_sec"]), 3),
            "eef": round(eef, 2),
            "peak_exp_flow": round(peak_exp_flow, 2),
            "z_ref": round(z_ref, 2),
            "flow_residual_frac": round(residual_frac, 3),
            "eep": round(eep, 2),
            "set_peep": round(set_peep, 2),
            "peep_delta": round(peep_delta, 2),
            "pressure_flag": bool(pressure_flag),
        })

    return pd.DataFrame(rows, columns=AUTO_PEEP_COLUMNS)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from parser import load_dataset, load_waveform, metadata_frame
    from breath_segment import segment_capture

    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Detect auto-PEEP (air trapping) from flow + pressure.")
    ap.add_argument("data_dir", nargs="?", default=root / "smart_icu_data", type=Path)
    ap.add_argument("--baseline", default="slope")
    ap.add_argument("--hysteresis", type=float, default=0.0)
    ap.add_argument("--flow-frac", type=float, default=0.15,
                    help="min fraction of expiratory flow still present at end-expiration")
    ap.add_argument("--flow-abs", type=float, default=2.0,
                    help="min absolute residual end-expiratory flow (L/min) noise floor")
    ap.add_argument("--peep-min", type=float, default=1.0,
                    help="min end-expiratory pressure excess over set PEEP (cmH2O)")
    ap.add_argument("--flow-only", action="store_true",
                    help="do not require the pressure signature (flow evidence alone)")
    args = ap.parse_args()

    baseline = args.baseline
    if baseline not in ("zero", "auto", "patient", "slope"):
        baseline = float(baseline)

    meta = metadata_frame(load_dataset(args.data_dir))
    captures = meta.dropna(subset=["raw_data"])[["patient_id", "raw_data"]].drop_duplicates()

    parts = []
    for _, cap in captures.iterrows():
        wf = load_waveform(args.data_dir / cap["raw_data"])
        breaths = segment_capture(wf, cap["patient_id"], cap["raw_data"],
                                  baseline=baseline, hysteresis=args.hysteresis)
        parts.append(detect_auto_peep(
            wf, breaths,
            flow_frac=args.flow_frac, flow_abs=args.flow_abs,
            peep_min=args.peep_min, require_pressure=not args.flow_only,
        ))
    events = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=AUTO_PEEP_COLUMNS)

    n_caps = events["raw_data"].nunique() if len(events) else 0
    print(f"{len(events)} auto-PEEP breaths across {n_caps} captures "
          f"(flow_frac>{args.flow_frac}, peep_min>{args.peep_min}"
          f"{', flow-only' if args.flow_only else ', flow+pressure'})")
    if len(events):
        print(events.to_string(index=False))
