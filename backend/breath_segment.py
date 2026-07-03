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
    flow: np.ndarray,
    baseline: float = 0.0,
    hysteresis: float = 0.0,
    slope_threshold: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (rising, falling) sample indices via a hysteresis state machine.

    Inspiration is entered when flow rises above `baseline + hysteresis` **and**
    the local rise rate has reached `slope_threshold`; expiration when flow drops
    below `baseline - hysteresis`. The band rejects noise-driven false crossings
    near the baseline; the slope gate rejects slow baseline drift that clears the
    band without a real inspiratory effort. A crossing index i is the first
    sample of the new phase.

    slope_threshold is in flow units per second (L/min per second). The slope is
    a centered derivative `np.gradient(flow) * SAMPLE_RATE_HZ`. Both the band and
    the slope condition must hold at the same sample for a rising crossing to be
    marked, so the onset lands where flow is genuinely accelerating upward.

    With baseline=0, hysteresis=0 and slope_threshold=0 this reproduces pure
    zero-crossing.
    """
    upper = baseline + hysteresis
    lower = baseline - hysteresis
    slope = np.gradient(flow) * SAMPLE_RATE_HZ
    rising: list[int] = []
    falling: list[int] = []
    state = "insp" if flow[0] > baseline else "exp"
    for i in range(1, len(flow)):
        if state == "exp" and flow[i] > upper and slope[i] >= slope_threshold:
            rising.append(i)
            state = "insp"
        elif state == "insp" and flow[i] <= lower:
            falling.append(i)
            state = "exp"
    return np.array(rising, dtype=int), np.array(falling, dtype=int)


def _first_peak_flow(flow: np.ndarray, i: int, cap: int) -> float:
    """Flow value at the first inspiratory peak at or after index i.

    Walk forward from i while flow keeps rising and return the value at the first
    point where it stops climbing (the first descending point / local max), i.e.
    the peak inspiratory flow of the rise the onset started. Search is capped at
    `cap` samples so a slow drift does not run past the breath.
    """
    j = i
    end = min(len(flow) - 1, i + cap)
    while j < end and flow[j + 1] >= flow[j]:
        j += 1
    return float(flow[j])


def _detect_slope_onsets(
    flow: np.ndarray,
    window: int,
    delta_threshold: float,
    refractory: int | None = None,
    exp_guard: float = 0.0,
    peak_min: float = 0.0,
    peak_cap: int | None = None,
) -> np.ndarray:
    """Return inspiration-onset indices from a rise in slope relative to its trend.

    Level-agnostic detector (no baseline needed): compute the slope at each point,
    keep a trailing window of the past `window` slopes as the local trend (their
    mean), and flag point i as a breath start when its slope exceeds that trend by
    at least `delta_threshold`. A refractory gap (default = `window`) prevents the
    same rising edge from firing repeatedly. Because it keys on the *change* in
    slope, it segments captures whose flow is offset high and never crosses zero.

    exp_guard (L/min per second, 0 = off) rejects candidates that sit on the
    expiratory limb: if the flow was steeply *decreasing* just before the candidate
    (min slope over the trailing window drops below `-exp_guard`), the point is a
    fall into / recovery out of expiration, not a real inspiratory onset, so it is
    skipped. A real onset is preceded by the near-flat end-expiratory pause, whose
    slope stays above the guard; the guard is a magnitude so plateau noise dipping
    slightly negative is not mistaken for expiration.

    peak_min (L/min, 0 = off) requires the rise the onset starts to reach a real
    peak inspiratory flow: the first flow peak after the candidate (see
    `_first_peak_flow`, searched up to `peak_cap` samples ahead, default =
    refractory) must be at least `peak_min`, else the point is too weak to be a
    breath and is skipped. ~60-90 L/min is typical for a normal adult.

    window / refractory / peak_cap are in samples; delta_threshold / exp_guard are
    L/min per second; peak_min is L/min.
    """
    slope = np.gradient(flow) * SAMPLE_RATE_HZ
    if refractory is None:
        refractory = window
    if peak_cap is None:
        peak_cap = max(1, refractory)
    onsets: list[int] = []
    last = -(10 ** 9)
    for i in range(window, len(flow)):
        trend = slope[i - window:i].mean()
        if slope[i] - trend < delta_threshold or (i - last) <= refractory:
            continue
        if exp_guard > 0 and slope[i - window:i].min() < -exp_guard:
            continue
        if peak_min > 0 and _first_peak_flow(flow, i, peak_cap) < peak_min:
            continue
        onsets.append(i)
        last = i
    return np.array(onsets, dtype=int)


def segment_capture(
    wf: pd.DataFrame,
    patient_id: str = "",
    raw_data: str = "",
    min_breath_sec: float = 0.0,
    baseline: str | float = "zero",
    hysteresis: float = 0.0,
    slope_threshold: float = 0.0,
    slope_window_sec: float = 0.32,
    slope_delta: float = 100.0,
    slope_refractory_sec: float = 1.0,
    slope_exp_guard: float = 100.0,
    slope_peak_min: float | str = 60.0,
) -> pd.DataFrame:
    """Segment one waveform DataFrame (from load_waveform) into breaths.

    min_breath_sec: drop breaths shorter than this (0 = no filter).
    baseline: "zero" (literal 0), "auto" (low-percentile offset), "slope" (adaptive
        slope-change onset detection, level-agnostic), or a numeric offset.
    hysteresis: dead-band (L/min) around the baseline to reject noise crossings.
    slope_threshold: min rise rate (L/min per second) at the inspiration onset;
        both this and the hysteresis band must be met to mark a breath boundary
        (0 = no slope gate). Used by the level-crossing modes only.
    slope_window_sec / slope_delta / slope_refractory_sec / slope_exp_guard /
        slope_peak_min: for baseline="slope" — the trailing trend window (seconds),
        the slope-jump threshold (L/min per second) above that trend that flags a
        breath start, the minimum spacing between onsets (seconds), the expiratory
        guard (L/min per second) that drops candidates preceded by a steep flow
        *decrease* i.e. the expiratory limb, and the minimum peak inspiratory flow
        (L/min) the rise must reach for the onset to count, or "mean" to use the
        whole-capture average flow as that threshold (see `_detect_slope_onsets`).
    """
    flow = wf["flow"].to_numpy()
    slope_mode = baseline == "slope"
    if baseline in ("auto", "patient", "slope"):
        # "patient" is resolved to a number by segment_dataset; if it reaches here
        # (single-capture call) it degrades to per-capture auto. "slope" uses the
        # auto baseline only to find expiration onsets (insp_end); its breath
        # boundaries come from the slope-change detector.
        base = estimate_baseline(flow)
    elif baseline == "zero":
        base = 0.0
    else:
        base = float(baseline)
    pressure = wf["pressure"].to_numpy()
    volume = wf["volume"].to_numpy()
    n = len(flow)

    if slope_mode:
        window = max(1, int(round(slope_window_sec * SAMPLE_RATE_HZ)))
        refractory = max(1, int(round(slope_refractory_sec * SAMPLE_RATE_HZ)))
        # "mean" -> use the whole-capture average flow as the peak-flow threshold
        peak_min = (float(np.mean(flow)) if slope_peak_min == "mean"
                    else float(slope_peak_min))
        rising = _detect_slope_onsets(flow, window, slope_delta, refractory,
                                      slope_exp_guard, peak_min)
        _, falling = _detect_crossings(flow, base, hysteresis)
    else:
        rising, falling = _detect_crossings(flow, base, hysteresis, slope_threshold)
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
    slope_threshold: float = 0.0,
    slope_window_sec: float = 0.32,
    slope_delta: float = 100.0,
    slope_refractory_sec: float = 1.0,
    slope_exp_guard: float = 100.0,
    slope_peak_min: float | str = 60.0,
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
        frames.append(segment_capture(wf, pid, raw, min_breath_sec, base, hysteresis,
                                       slope_threshold, slope_window_sec, slope_delta,
                                       slope_refractory_sec, slope_exp_guard, slope_peak_min))
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
                         '"patient" (per-patient low percentile), "slope" (adaptive '
                         'slope-change onset detection), or a numeric offset; '
                         'pair auto/patient with --hysteresis')
    ap.add_argument("--hysteresis", type=float, default=0.0,
                    help="dead-band (L/min) around baseline to reject noise crossings")
    ap.add_argument("--slope-threshold", type=float, default=0.0,
                    help="min rise rate (L/min per second) at inspiration onset; "
                         "both this and the hysteresis band must be met to mark a "
                         "breath (0 = off; recommended ~30)")
    ap.add_argument("--slope-window-sec", type=float, default=0.32,
                    help="baseline=slope: trailing trend window in seconds (default 0.32)")
    ap.add_argument("--slope-delta", type=float, default=100.0,
                    help="baseline=slope: slope jump (L/min per second) above the "
                         "recent trend that flags a breath start (default 100)")
    ap.add_argument("--slope-refractory-sec", type=float, default=1.0,
                    help="baseline=slope: min spacing between onsets in seconds; "
                         "suppresses the expiratory-recovery double-fire (default 1.0)")
    ap.add_argument("--slope-exp-guard", type=float, default=100.0,
                    help="baseline=slope: drop onsets preceded by a steep flow "
                         "decrease (expiratory limb); min pre-onset slope below "
                         "this magnitude (L/min per second) is rejected (0 = off, default 100)")
    ap.add_argument("--slope-peak-min", default="60",
                    help='baseline=slope: min peak inspiratory flow (L/min) the rise '
                         'must reach for an onset to count; ~60-90 for a normal adult, '
                         'or "mean" to use the whole-capture average flow '
                         '(0 = off, default 60)')
    args = ap.parse_args()

    baseline = args.baseline
    if baseline not in ("zero", "auto", "patient", "slope"):
        baseline = float(baseline)
    peak_min = args.slope_peak_min if args.slope_peak_min == "mean" else float(args.slope_peak_min)
    breaths = segment_dataset(args.data_dir, min_breath_sec=args.min_breath_sec,
                              baseline=baseline, hysteresis=args.hysteresis,
                              slope_threshold=args.slope_threshold,
                              slope_window_sec=args.slope_window_sec,
                              slope_delta=args.slope_delta,
                              slope_refractory_sec=args.slope_refractory_sec,
                              slope_exp_guard=args.slope_exp_guard,
                              slope_peak_min=peak_min)
    n_partial = int((~breaths["is_complete"]).sum())
    print(f"segmented {breaths['raw_data'].nunique()} captures "
          f"into {len(breaths)} breaths "
          f"({n_partial} partial edge breaths)")

    written = save_breaths(breaths, args.out)
    print(f"saved {len(breaths)} breaths -> {written}")
