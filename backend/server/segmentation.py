"""Shared breath-segmentation resolution used by more than one router.

Pulls the baseline-mode handling out of the /api/breaths and
/api/double-triggers routes so both run the exact same segmentation for a
given set of query params.
"""

from __future__ import annotations

import pandas as pd

from breath_segment import segment_capture, estimate_baseline, slope_baseline


def segment_from_params(
    wf: pd.DataFrame,
    file: str,
    baseline: str,
    hysteresis: float,
    slope: float,
    sdelta: float,
    swin: float,
    srefr: float,
    sguard: float,
    speak: float | str,
) -> tuple[pd.DataFrame, float]:
    """Resolve the baseline mode and run segment_capture; returns (breaths, baseline_value)."""
    flow = wf["flow"].to_numpy()
    if baseline == "auto":
        base_arg: str | float = "auto"
        base_val = estimate_baseline(flow)
    elif baseline == "slope":
        base_arg = "slope"
        base_val = slope_baseline(
            flow,
            slope_window_sec=swin,
            slope_delta=sdelta,
            slope_refractory_sec=srefr,
            slope_exp_guard=sguard,
            slope_peak_min=speak,
        )
    elif baseline == "zero":
        base_arg, base_val = "zero", 0.0
    else:  # numeric manual offset; bad input -> zero
        try:
            base_val = float(baseline)
            base_arg = base_val
        except ValueError:
            base_arg, base_val = "zero", 0.0

    breaths = segment_capture(
        wf,
        raw_data=file,
        baseline=base_arg,
        hysteresis=hysteresis,
        slope_threshold=slope,
        slope_window_sec=swin,
        slope_delta=sdelta,
        slope_refractory_sec=srefr,
        slope_exp_guard=sguard,
        slope_peak_min=speak,
    )
    return breaths, base_val
