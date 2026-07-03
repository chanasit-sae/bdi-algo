"""Auto-PEEP (air trapping) asynchrony detection.

See auto-peep.md for the full spec this module implements.

Auto-PEEP (intrinsic PEEP / air trapping / dynamic hyperinflation): the lung
does not fully empty before the next breath begins, so gas is trapped and
end-expiratory alveolar pressure sits above the set PEEP. It is the
physiological opposite of the short-Te double trigger (asynchrony.md) — there
expiration is too *short*; here it is too *incomplete*.

Neither waveform alone is specific, so detection requires the two signals to
agree (the flow + pressure mix):

  Flow (air trapping):          expiratory flow fails to return to the zero
                                 baseline before the next inspiration.
  Pressure (dynamic hyperinflation): end-expiratory airway pressure sits
                                 above the set PEEP.

Only complete breaths are scored — the trailing partial breath's `exp_end_idx`
is the capture edge, not a real end-expiration. Needs >=2 complete breaths.

Capture-level reference levels (data-driven, no absolute calibration):
    z_ref    = percentile(all end-expiratory flow, zero_pct)      # true-zero flow
    set_peep = percentile(all end-expiratory pressure, setpeep_pct)
Breaths that empty completely settle at true zero flow; trapped breaths stay
*below* it, so the high percentile of end-expiratory flow picks the
well-emptied breaths as the zero reference. Symmetrically, the best-emptied
breaths reach set PEEP, so the low percentile of end-expiratory pressure picks
it out. Do NOT reuse breath_segment.estimate_baseline_from_onsets as z_ref:
that is the *median* end-expiratory level and would subtract out the very
residual this test measures.

Per-breath metrics, over the expiratory limb flow[insp_end_idx : exp_end_idx+1]:
    peak_exp_flow      = min(exp_limb_flow)          # most negative = peak exp flow
    residual           = z_ref - eef                 # >0 => still expiring at end
    peak_mag           = z_ref - peak_exp_flow        # full exp flow magnitude
    flow_residual_frac = residual / peak_mag          # fraction still present at end-exp
    peep_delta         = eep - set_peep               # ~ intrinsic PEEP (cmH2O)

Decision (both signatures must hold, the "mix"):
    flow  hit:  flow_residual_frac > flow_frac  AND  residual > flow_abs
    pressure :  peep_delta > peep_min
    flag = flow_hit AND (pressure_flag if require_pressure else True)
`flow_abs` is an absolute noise floor so a large *fraction* on a low-flow
breath doesn't trigger on its own. With require_pressure=False, only the flow
signature is required (peep_delta/pressure_flag still reported for review).

Limitations: z_ref/set_peep are estimated from the same breaths being tested,
so if *every* breath in a capture traps, the references shift toward the
trapped level and the detector under-flags — it finds breaths trapped
*relative to* the capture's best-emptied ones, not absolute intrinsic PEEP
(which needs an expiratory-hold maneuver). Breaths with peak_mag <= 0 are
skipped (degenerate expiratory limb).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

AUTO_PEEP_COLUMNS = [
    "patient_id", "raw_data", "breath_idx", "t_insp_start", "t_insp_end", "t_exp_end",
    "eef", "peak_exp_flow", "z_ref", "residual", "peak_mag", "flow_residual_frac",
    "eep", "set_peep", "peep_delta", "pressure_flag",
]


def detect_auto_peep(
    breaths: pd.DataFrame,
    flow: np.ndarray,
    pressure: np.ndarray,
    flow_frac: float = 0.15,
    flow_abs: float = 2.0,
    peep_min: float = 1.0,
    require_pressure: bool = True,
    zero_pct: float = 75.0,
    setpeep_pct: float = 10.0,
) -> pd.DataFrame:
    """Flag complete breaths showing auto-PEEP (air trapping), per capture.

    `breaths` is one capture's breath table from `breath_segment.segment_capture`
    (needs `insp_end_idx`, `exp_end_idx`, `t_insp_start`, `t_insp_end`, `t_exp_end`,
    `breath_idx`, `is_complete`). Returns one row per flagged breath.
    """
    complete = breaths[breaths["is_complete"]] if "is_complete" in breaths else breaths
    if len(complete) < 2:
        return pd.DataFrame(columns=AUTO_PEEP_COLUMNS)

    eef_all = np.array([flow[int(r["exp_end_idx"])] for _, r in complete.iterrows()])
    eep_all = np.array([pressure[int(r["exp_end_idx"])] for _, r in complete.iterrows()])
    z_ref = float(np.percentile(eef_all, zero_pct))
    set_peep = float(np.percentile(eep_all, setpeep_pct))

    rows = []
    for _, b in complete.iterrows():
        i0 = int(b["insp_end_idx"])
        i1 = int(b["exp_end_idx"])
        exp_limb = flow[i0 : i1 + 1]
        if len(exp_limb) == 0:
            continue

        eef = float(flow[i1])
        eep = float(pressure[i1])
        peak_exp_flow = float(exp_limb.min())
        peak_mag = z_ref - peak_exp_flow
        if peak_mag <= 0:
            continue  # degenerate expiratory limb

        residual = z_ref - eef
        flow_residual_frac = residual / peak_mag
        peep_delta = eep - set_peep

        flow_hit = flow_residual_frac > flow_frac and residual > flow_abs
        pressure_flag = peep_delta > peep_min
        flagged = flow_hit and (pressure_flag if require_pressure else True)
        if not flagged:
            continue

        rows.append({
            "patient_id": b["patient_id"] if "patient_id" in b else "",
            "raw_data": b["raw_data"] if "raw_data" in b else "",
            "breath_idx": int(b["breath_idx"]),
            "t_insp_start": float(b["t_insp_start"]),
            "t_insp_end": float(b["t_insp_end"]),
            "t_exp_end": float(b["t_exp_end"]),
            "eef": round(eef, 2),
            "peak_exp_flow": round(peak_exp_flow, 2),
            "z_ref": round(z_ref, 2),
            "residual": round(residual, 2),
            "peak_mag": round(peak_mag, 2),
            "flow_residual_frac": round(flow_residual_frac, 3),
            "eep": round(eep, 2),
            "set_peep": round(set_peep, 2),
            "peep_delta": round(peep_delta, 2),
            "pressure_flag": bool(pressure_flag),
        })

    return pd.DataFrame(rows, columns=AUTO_PEEP_COLUMNS)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from breath_segment import segment_dataset
    from parser import load_waveform

    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Detect auto-PEEP (air trapping) asynchrony from segmented breaths.")
    ap.add_argument("data_dir", nargs="?", default=root / "smart_icu_data", type=Path)
    ap.add_argument("--baseline", default="slope")
    ap.add_argument("--hysteresis", type=float, default=0.0)
    ap.add_argument("--flow-frac", type=float, default=0.15)
    ap.add_argument("--flow-abs", type=float, default=2.0)
    ap.add_argument("--peep-min", type=float, default=1.0)
    ap.add_argument("--flow-only", action="store_true", help="don't require the pressure signature")
    args = ap.parse_args()

    baseline = args.baseline
    if baseline not in ("zero", "auto", "patient", "slope"):
        baseline = float(baseline)
    breaths = segment_dataset(args.data_dir, baseline=baseline, hysteresis=args.hysteresis)

    parts = []
    for fname, grp in breaths.groupby("raw_data", sort=False):
        wf = load_waveform(args.data_dir / fname)
        parts.append(detect_auto_peep(
            grp, wf["flow"].to_numpy(), wf["pressure"].to_numpy(),
            flow_frac=args.flow_frac, flow_abs=args.flow_abs, peep_min=args.peep_min,
            require_pressure=not args.flow_only,
        ))
    events = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=AUTO_PEEP_COLUMNS)

    n_caps = events["raw_data"].nunique() if len(events) else 0
    mode = "flow-only" if args.flow_only else "flow+pressure mix"
    print(f"{len(events)} auto-PEEP breaths across {n_caps} captures "
          f"({mode}: flow_frac>={args.flow_frac}, flow_abs>={args.flow_abs}, peep_min>={args.peep_min})")
    if len(events):
        print(events.to_string(index=False))
