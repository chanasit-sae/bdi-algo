"""EXPERIMENT (not wired into anything): compare flow zero-crossing segmentation
against a volume-based detector, and check how often they agree.

Standalone — reuses parser.load_waveform and breath_segment's crossing detector
without modifying them. Run:

    python3 backend/segment_compare.py [data_dir] [--hysteresis N] [--tol-sec T]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from parser import SAMPLE_RATE_HZ, load_waveform, load_dataset, metadata_frame
from breath_segment import _detect_crossings, estimate_baseline

MIN_FLOW_RANGE = 5.0        # skip flat/disconnected captures (same cutoff as viz)
VOL_MIN_PROM = 30.0         # mL: min rise amplitude to count a volume breath
VOL_SMOOTH = 3              # moving-average window (samples)


def _smooth(x: np.ndarray, w: int) -> np.ndarray:
    if w <= 1:
        return x
    k = np.ones(w) / w
    return np.convolve(x, k, mode="same")


def flow_onsets(flow: np.ndarray, hysteresis: float) -> np.ndarray:
    """Inspiration onsets from flow: rising crossings of the auto baseline."""
    base = estimate_baseline(flow)
    rising, _ = _detect_crossings(flow, base, hysteresis)
    return rising


def volume_onsets(volume: np.ndarray, min_prom: float = VOL_MIN_PROM) -> np.ndarray:
    """Inspiration onsets from volume: local minima where volume starts rising.

    Volume rises through inspiration and falls through expiration, so a breath
    boundary is a trough. We take the sign change of the smoothed derivative
    (<=0 -> >0) and keep troughs whose following rise clears min_prom.
    """
    v = _smooth(volume, VOL_SMOOTH)
    d = np.diff(v)
    onsets = []
    for i in range(1, len(d)):
        if d[i] > 0 and d[i - 1] <= 0:            # trough: fall/flat -> rise
            # peak of the ensuing rise, before the next fall
            j = i + 1
            while j < len(d) and d[j] >= 0:
                j += 1
            if v[j] - v[i] >= min_prom:
                onsets.append(i + 1)              # first rising sample
    return np.array(onsets, dtype=int)


def agreement(a: np.ndarray, b: np.ndarray, tol: int) -> int:
    """Count onsets in `a` that have a match in `b` within +/- tol samples."""
    matched = 0
    used = np.zeros(len(b), dtype=bool)
    for x in a:
        if len(b) == 0:
            break
        k = int(np.argmin(np.abs(b - x)))
        if not used[k] and abs(b[k] - x) <= tol:
            used[k] = True
            matched += 1
    return matched


def main():
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data_dir", nargs="?", default=root / "smart_icu_data", type=Path)
    ap.add_argument("--hysteresis", type=float, default=3.0)
    ap.add_argument("--tol-sec", type=float, default=0.4)
    args = ap.parse_args()

    tol = int(round(args.tol_sec * SAMPLE_RATE_HZ))
    meta = metadata_frame(load_dataset(args.data_dir))
    caps = meta.dropna(subset=["raw_data"])[["raw_data"]].drop_duplicates()

    print(f"hysteresis={args.hysteresis}  tol=+/-{tol} samples ({args.tol_sec}s)\n")
    print(f"{'capture':<44}{'flow':>5}{'vol':>5}{'agree':>6}")
    tot_f = tot_v = tot_a = 0
    n_caps = 0
    for r in caps["raw_data"]:
        wf = load_waveform(args.data_dir / r)
        flow = wf["flow"].to_numpy()
        if float(flow.max() - flow.min()) < MIN_FLOW_RANGE:
            continue                              # skip disconnected
        n_caps += 1
        fo = flow_onsets(flow, args.hysteresis)
        vo = volume_onsets(wf["volume"].to_numpy())
        ag = agreement(fo, vo, tol)
        tot_f += len(fo); tot_v += len(vo); tot_a += ag
        print(f"{r[:44]:<44}{len(fo):>5}{len(vo):>5}{ag:>6}")

    print(f"\n{n_caps} connected captures")
    print(f"flow onsets: {tot_f}   volume onsets: {tot_v}   agreed: {tot_a}")
    if tot_f:
        print(f"flow onsets confirmed by volume: {tot_a}/{tot_f} = {tot_a/tot_f:.0%}")
    if tot_v:
        print(f"volume onsets confirmed by flow: {tot_a}/{tot_v} = {tot_a/tot_v:.0%}")


if __name__ == "__main__":
    main()
