"""Mechanical power tracking — per-patient rolling average, with a threshold alert.

Mechanical power (MP): the energy delivered to the respiratory system per unit
time by the ventilator. Popularized as a unifying ventilator-induced lung
injury (VILI) risk metric by Gattinoni L et al., "Ventilator-related causes of
lung injury: the mechanical power." Intensive Care Med. 2016;42(10):1567-1575.
A large ICU meta-analysis (Serpa Neto A et al., "Mechanical power of
ventilation is associated with mortality in critically ill patients: an
individual patient data meta-analysis." Crit Care Med. 2018;46(2):200-207)
found mortality risk increasing above roughly 17-19 J/min — the threshold
range this module's default (17.0 J/min) sits at.

Unlike the four breath-level asynchrony detectors, this is tracked PER
PATIENT as a rolling average over a trailing time window (default 24h) ending
at their most recent capture, not a per-breath event — a single unusually
high breath doesn't mean much on its own; a sustained elevated exposure does.

Formula: direct pressure-volume loop integration, per breath, over the
inspiratory limb (insp_start_idx -> insp_end_idx) --

    energy_joules = 0.0980665 * integral(pressure d(volume_in_liters))
    mp_j_per_min  = energy_joules * rr_bpm

This works for any breath shape/ventilator mode and needs no detected
end-inspiratory plateau (unlike Gattinoni's algebraic "simplified equation",
which needs driving pressure = Pplateau - PEEP -- not present on every
breath). The direct integral IS the definition mechanical power's algebraic
forms are themselves derived from (the area of the inspiratory P-V curve),
so this is not an approximation of the simplified equation -- it's the more
general form the simplified equation approximates for the specific case of
constant-flow volume control with a plateau. See __main__'s --compare flag
for a cross-check against the simplified equation on breaths where a plateau
is available.

0.0980665 J per (cmH2O x L) is the standard pressure-volume-to-energy
conversion (1 cmH2O = 98.0665 Pa; 1 Pa x m^3 = 1 J; 1 L = 1e-3 m^3).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from parser import SAMPLE_RATE_HZ

CMH2O_L_TO_JOULES = 0.0980665

# np.trapz was renamed np.trapezoid in numpy 2.0 (and removed outright in later
# 2.x releases) -- support either so this doesn't break depending on which
# numpy a given environment has installed.
_trapz = getattr(np, "trapezoid", None) or np.trapz

MP_COLUMNS = ["breath_idx", "t_insp_start", "energy_joules", "rr_bpm", "mp_j_per_min"]


def breath_energy_joules(pressure: np.ndarray, volume_ml: np.ndarray) -> float:
    """Mechanical energy (Joules) delivered during one breath's inspiration,
    from the area of the pressure-volume curve: 0.0980665 x integral(P dV).

    `pressure`/`volume_ml` are the *inspiratory-limb* samples only (already
    sliced by the caller), in cmH2O and mL respectively.
    """
    if len(pressure) < 2:
        return 0.0
    volume_l = volume_ml / 1000.0
    return float(CMH2O_L_TO_JOULES * _trapz(pressure, volume_l))


def compute_breath_mp(breaths: pd.DataFrame, pressure: np.ndarray, volume: np.ndarray) -> pd.DataFrame:
    """Per-breath mechanical power (J/min) for one capture.

    `breaths` is one capture's breath table from `breath_segment.segment_capture`
    (needs `insp_start_idx`, `insp_end_idx`, `breath_idx`, `t_insp_start`,
    `rr_bpm`, `is_complete`). The trailing partial breath is always excluded:
    its `rr_bpm` is computed the same as any other breath's (never None/NaN)
    but is a known-unreliable artifact of where the recording happened to cut
    off (see breath-segment.md) -- multiplying real per-breath energy by that
    bogus rate produces wildly inflated MP values, exactly the failure mode
    `features.py` already guards against for its own per-capture summaries.
    """
    complete = breaths[breaths["is_complete"]] if "is_complete" in breaths else breaths
    rows = []
    for _, b in complete.iterrows():
        rr = b.get("rr_bpm")
        if rr is None or (isinstance(rr, float) and np.isnan(rr)):
            continue
        i0 = int(b["insp_start_idx"])
        i1 = int(b["insp_end_idx"])
        energy = breath_energy_joules(pressure[i0 : i1 + 1], volume[i0 : i1 + 1])
        rows.append({
            "breath_idx": int(b["breath_idx"]),
            "t_insp_start": float(b["t_insp_start"]),
            "energy_joules": round(energy, 4),
            "rr_bpm": float(rr),
            "mp_j_per_min": round(energy * float(rr), 2),
        })
    return pd.DataFrame(rows, columns=MP_COLUMNS)


def gattinoni_simplified_mp(row: dict) -> float | None:
    """Gattinoni's algebraic "simplified equation", for cross-checking the
    direct P-V integral against the standard textbook formula. Needs a
    detected plateau (driving pressure); returns None otherwise.

        MP (J/min) = 0.098 x RR x VT(L) x (PIP - 0.5 x driving_pressure)
    """
    driving = row.get("driving_pressure_cmh2o")
    pip = row.get("pip_cmh2o")
    vt_ml = row.get("tidal_volume_ml")
    rr = row.get("rr_bpm")
    if driving is None or pip is None or vt_ml is None or rr is None:
        return None
    if any(isinstance(v, float) and np.isnan(v) for v in (driving, pip, vt_ml, rr)):
        return None
    vt_l = vt_ml / 1000.0
    return round(CMH2O_L_TO_JOULES * rr * vt_l * (pip - 0.5 * driving), 2)


def capture_hours(day, time_str) -> float:
    """Synthetic timeline position for one capture: day*24 + time-of-day as a
    fraction of 24h. Captures don't carry an absolute calendar date, so this
    is only meaningful for ordering/windowing *within* one patient.
    """
    d = day if day is not None else 0
    h, m, s = 0, 0, 0
    if time_str:
        parts = time_str.split(":")
        h = int(parts[0]) if len(parts) > 0 else 0
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0
    return d * 24 + h + m / 60 + s / 3600


def rolling_patient_mp(
    capture_breath_mps: list[tuple[int, str, pd.DataFrame]],
    window_hours: float = 24.0,
) -> dict | None:
    """Trailing rolling-average mechanical power for one patient, as of their
    most recent capture.

    `capture_breath_mps` is a list of (day, time_str, breath_mp_df) tuples,
    one per capture already scanned for this patient (breath_mp_df from
    `compute_breath_mp`, e.g. via day/time carried alongside). Returns None if
    there are no breaths at all. `day`/`time` become a synthetic timeline
    (day*24 + hour:minute:second as a fraction of 24h) since captures don't
    carry an absolute calendar date -- only meaningful *within* one patient.
    """
    if not capture_breath_mps:
        return None

    entries = []  # (hours, mp_j_per_min)
    latest = None  # (hours, day, time, raw_data)
    for day, time_str, raw_data, mp_df in capture_breath_mps:
        h = capture_hours(day, time_str)
        if latest is None or h > latest[0]:
            latest = (h, day, time_str, raw_data)
        for _, r in mp_df.iterrows():
            entries.append((h, float(r["mp_j_per_min"])))

    if not entries or latest is None:
        return None

    cutoff = latest[0] - window_hours
    windowed = [mp for h, mp in entries if h > cutoff]
    if not windowed:
        return None

    return {
        "avg_mp_j_per_min": round(float(np.mean(windowed)), 2),
        "n_breaths": len(windowed),
        "n_captures_total": len(capture_breath_mps),
        "latest_day": latest[1],
        "latest_time": latest[2],
        "latest_raw_data": latest[3],
    }


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from breath_segment import segment_dataset
    from parser import load_dataset, load_waveform, metadata_frame

    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Track per-patient rolling mechanical power.")
    ap.add_argument("data_dir", nargs="?", default=root / "smart_icu_data", type=Path)
    ap.add_argument("--baseline", default="slope")
    ap.add_argument("--hysteresis", type=float, default=0.0)
    ap.add_argument("--threshold", type=float, default=17.0)
    ap.add_argument("--window-hours", type=float, default=24.0)
    ap.add_argument("--compare", action="store_true",
                     help="cross-check the P-V integral against Gattinoni's simplified equation "
                          "on breaths with a detected plateau")
    args = ap.parse_args()

    baseline = args.baseline
    if baseline not in ("zero", "auto", "patient", "slope"):
        baseline = float(baseline)

    meta = metadata_frame(load_dataset(args.data_dir))
    captures = meta.dropna(subset=["raw_data"])[["patient_id", "raw_data", "day", "capture_time"]]

    if args.compare:
        from breath_metrics import add_metrics
        from breath_segment import segment_capture
        diffs = []
        for _, row in captures.iterrows():
            wf = load_waveform(args.data_dir / row["raw_data"])
            breaths = segment_capture(wf, raw_data=row["raw_data"], baseline=baseline, hysteresis=args.hysteresis)
            if breaths.empty:
                continue
            breaths = add_metrics(breaths, wf)
            mp_df = compute_breath_mp(breaths, wf["pressure"].to_numpy(), wf["volume"].to_numpy())
            for _, b in breaths.iterrows():
                simplified = gattinoni_simplified_mp(b.to_dict())
                if simplified is None:
                    continue
                match = mp_df[mp_df["breath_idx"] == b["breath_idx"]]
                if match.empty:
                    continue
                direct = float(match.iloc[0]["mp_j_per_min"])
                diffs.append((row["raw_data"], int(b["breath_idx"]), direct, simplified))
        print(f"{len(diffs)} breaths with a detected plateau (comparable):")
        print(f"{'capture':<50}{'breath':>7}{'direct J/min':>14}{'simplified J/min':>18}{'diff%':>8}")
        for fname, bidx, direct, simplified in diffs:
            pct = (direct - simplified) / simplified * 100 if simplified else float("nan")
            print(f"{fname[:50]:<50}{bidx:>7}{direct:>14.2f}{simplified:>18.2f}{pct:>7.1f}%")
    else:
        breaths_all = segment_dataset(args.data_dir, baseline=baseline, hysteresis=args.hysteresis)
        by_patient: dict[str, list] = {}
        for _, row in captures.iterrows():
            wf = load_waveform(args.data_dir / row["raw_data"])
            grp = breaths_all[breaths_all["raw_data"] == row["raw_data"]]
            if grp.empty:
                continue
            mp_df = compute_breath_mp(grp, wf["pressure"].to_numpy(), wf["volume"].to_numpy())
            by_patient.setdefault(row["patient_id"], []).append(
                (row["day"], row["capture_time"], row["raw_data"], mp_df)
            )

        print(f"threshold={args.threshold} J/min, window={args.window_hours}h\n")
        for pid, caps in by_patient.items():
            status = rolling_patient_mp(caps, window_hours=args.window_hours)
            if status is None:
                continue
            flag = " <-- ABOVE THRESHOLD" if status["avg_mp_j_per_min"] >= args.threshold else ""
            print(f"{pid[:12]}...  avg={status['avg_mp_j_per_min']:>6.2f} J/min  "
                  f"n_breaths={status['n_breaths']:<4} n_captures={status['n_captures_total']:<3} "
                  f"as of day {status['latest_day']} {status['latest_time']}{flag}")
