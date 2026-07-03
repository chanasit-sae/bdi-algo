"""Double-triggering asynchrony detection from segmented breaths.

Double triggering: the patient's neural inspiratory effort continues past the
ventilator's inspiratory termination, so a second breath is triggered almost
immediately after the first -- i.e. an abnormally short expiratory pause
between two consecutive breaths.

Formula (Thille AW, Rodriguez P, Cabello B, Lellouche F, Brochard L.
"Patient-ventilator asynchrony during assisted mechanical ventilation."
Intensive Care Med. 2006;32(10):1515-1522 -- the standard clinical definition):

    Te(i) < ratio * Ti_ref                (default ratio = 0.5)

  Te(i)   te_sec of breath i: the expiratory gap before breath i+1 begins.
          te_sec = t_exp_end - t_insp_end, and t_exp_end IS breath i+1's
          t_insp_start (see breath_segment.py), so this is exactly the
          inter-breath gap -- no separate computation needed.
  Ti_ref  the inspiratory-time reference the short Te is judged against
          (`ti_ref`, see below).
  ratio   0.5 by default: "less than one half the [reference] Ti".

`ti_ref` selects what Ti_ref means:
  "pair"    (default) mean(Ti(i), Ti(i+1)) -- the pair's own average Ti.
            Robust to one noisy breath and adapts across a drifting session,
            without needing a whole-capture baseline.
  "capture" mean Ti over the capture's complete breaths -- closest to
            Thille's original "mean Ti" of the whole recording.
  "self"    Ti(i) alone -- the simplest, purely local comparison.

Optional secondary check, "volume stacking": double-triggered breaths
typically deliver close to double the tidal volume of a normal breath pair,
which is the actual clinical harm (volutrauma risk; Pohlman MC et al.,
"Excessive tidal volume from breath stacking during lung-protective
ventilation for acute lung injury." Crit Care Med. 2008;36(11):3019-23).
`require_stacking=True` additionally requires

    Vt(i) + Vt(i+1) > stack_ratio * 2 * median(Vt)

over the capture's complete breaths (stack_ratio default 1.5), tightening the
criterion to timing events that also stacked volume. Off by default so the
detector matches the plain Thille timing definition; `vt_ratio` is always
reported on flagged pairs so it can be reviewed either way.
"""

from __future__ import annotations

import pandas as pd

DOUBLE_TRIGGER_COLUMNS = [
    "patient_id", "raw_data", "breath_idx_a", "breath_idx_b",
    "t_insp_start_a", "t_insp_start_b", "t_exp_end_b",
    "ti_a", "ti_b", "te_gap", "ti_ref", "te_ti_ratio",
    "vt_a", "vt_b", "vt_pair", "vt_ratio", "stacked",
]


def _ti_ref(ti: pd.Series, complete_ti: pd.Series, i: int, mode: str) -> float | None:
    if mode == "self":
        return float(ti.iloc[i])
    if mode == "capture":
        return float(complete_ti.mean()) if len(complete_ti) else float(ti.mean())
    return float(ti.iloc[i:i + 2].mean())  # "pair" (default)


def detect_double_triggers(
    breaths: pd.DataFrame,
    ratio: float = 0.5,
    ti_ref: str = "pair",
    require_stacking: bool = False,
    stack_ratio: float = 1.5,
) -> pd.DataFrame:
    """Flag consecutive breath pairs in one capture as double-triggered.

    `breaths` is one capture's breath table from `breath_segment.segment_capture`
    (only `ti_sec`, `te_sec`, `tidal_volume_ml`, `t_insp_start`, `t_exp_end`,
    `breath_idx`, `is_complete` are used, so `breath_metrics.add_metrics` is not
    required). Returns one row per flagged pair; empty if fewer than 2 breaths
    or none qualify.
    """
    if ti_ref not in ("self", "pair", "capture"):
        raise ValueError(f"ti_ref must be self|pair|capture, got {ti_ref!r}")
    if len(breaths) < 2:
        return pd.DataFrame(columns=DOUBLE_TRIGGER_COLUMNS)

    b = breaths.reset_index(drop=True)
    complete = b[b["is_complete"]] if "is_complete" in b else b
    complete_ti = complete["ti_sec"]
    complete_vt = complete["tidal_volume_ml"]
    median_vt = float(complete_vt.median()) if len(complete_vt) else float(b["tidal_volume_ml"].median())

    rows = []
    for i in range(len(b) - 1):
        te_gap = float(b["te_sec"].iloc[i])
        tref = _ti_ref(b["ti_sec"], complete_ti, i, ti_ref)
        if not tref or tref <= 0:
            continue
        te_ti_ratio = te_gap / tref
        if te_ti_ratio >= ratio:
            continue

        vt_a = float(b["tidal_volume_ml"].iloc[i])
        vt_b = float(b["tidal_volume_ml"].iloc[i + 1])
        vt_pair = vt_a + vt_b
        vt_ratio = (vt_pair / (2 * median_vt)) if median_vt > 0 else None
        stacked = vt_ratio is not None and vt_ratio > stack_ratio
        if require_stacking and not stacked:
            continue

        rows.append({
            "patient_id": b["patient_id"].iloc[i] if "patient_id" in b else "",
            "raw_data": b["raw_data"].iloc[i] if "raw_data" in b else "",
            "breath_idx_a": int(b["breath_idx"].iloc[i]),
            "breath_idx_b": int(b["breath_idx"].iloc[i + 1]),
            "t_insp_start_a": float(b["t_insp_start"].iloc[i]),
            "t_insp_start_b": float(b["t_insp_start"].iloc[i + 1]),
            "t_exp_end_b": float(b["t_exp_end"].iloc[i + 1]),
            "ti_a": round(float(b["ti_sec"].iloc[i]), 3),
            "ti_b": round(float(b["ti_sec"].iloc[i + 1]), 3),
            "te_gap": round(te_gap, 3),
            "ti_ref": round(tref, 3),
            "te_ti_ratio": round(te_ti_ratio, 3),
            "vt_a": round(vt_a, 1),
            "vt_b": round(vt_b, 1),
            "vt_pair": round(vt_pair, 1),
            "vt_ratio": round(vt_ratio, 2) if vt_ratio is not None else None,
            "stacked": bool(stacked),
        })

    return pd.DataFrame(rows, columns=DOUBLE_TRIGGER_COLUMNS)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from breath_segment import segment_dataset

    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Detect double-triggering asynchrony from segmented breaths.")
    ap.add_argument("data_dir", nargs="?", default=root / "smart_icu_data", type=Path)
    ap.add_argument("--baseline", default="slope")
    ap.add_argument("--hysteresis", type=float, default=0.0)
    ap.add_argument("--ratio", type=float, default=0.5,
                     help="Te/Ti_ref cutoff; Thille et al. 2006 default is 0.5")
    ap.add_argument("--ti-ref", default="pair", choices=["self", "pair", "capture"])
    ap.add_argument("--require-stacking", action="store_true")
    ap.add_argument("--stack-ratio", type=float, default=1.5)
    args = ap.parse_args()

    baseline = args.baseline
    if baseline not in ("zero", "auto", "patient", "slope"):
        baseline = float(baseline)
    breaths = segment_dataset(args.data_dir, baseline=baseline, hysteresis=args.hysteresis)

    parts = []
    for _, grp in breaths.groupby("raw_data", sort=False):
        parts.append(detect_double_triggers(
            grp, ratio=args.ratio, ti_ref=args.ti_ref,
            require_stacking=args.require_stacking, stack_ratio=args.stack_ratio,
        ))
    events = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=DOUBLE_TRIGGER_COLUMNS)

    n_caps = events["raw_data"].nunique() if len(events) else 0
    print(f"{len(events)} double-triggered pairs across {n_caps} captures "
          f"(ratio<{args.ratio}, ti_ref={args.ti_ref}"
          f"{', stacking required' if args.require_stacking else ''})")
    if len(events):
        print(events.to_string(index=False))
