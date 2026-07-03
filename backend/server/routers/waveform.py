"""Waveform + breath-segmentation API.

Endpoints (all under /api):
    GET /api/index                     patient / capture metadata tree
    GET /api/waveform?file=...         raw Flow/Pressure/Volume + flow slope
    GET /api/breaths?file=...&...      segmented breaths with derived metrics

The segmentation query parameters mirror the knobs in breath_segment.py.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query

from parser import load_waveform, SAMPLE_RATE_HZ
from breath_segment import segment_capture, estimate_baseline, slope_baseline
from breath_metrics import add_metrics

from ..dataset import Dataset, denan
from ..deps import get_dataset

router = APIRouter(prefix="/api", tags=["waveform"])


@router.get("/index")
def get_index(ds: Dataset = Depends(get_dataset)):
    """Patient/capture metadata tree (the `valid` file set is kept server-side)."""
    return denan({"patients": ds.patients})


def _require_valid(ds: Dataset, file: str) -> None:
    if file not in ds.valid:  # guard against path traversal / unknown files
        raise HTTPException(status_code=404, detail="unknown file")


@router.get("/waveform")
def get_waveform(
    file: str = Query(..., description="capture CSV filename from /api/index"),
    ds: Dataset = Depends(get_dataset),
):
    _require_valid(ds, file)
    wf = load_waveform(ds.data_dir / file)
    slope = np.gradient(wf["flow"].to_numpy()) * SAMPLE_RATE_HZ
    return denan(
        {
            "t_sec": wf["t_sec"].round(3).tolist(),
            "flow": wf["flow"].tolist(),
            "pressure": wf["pressure"].tolist(),
            "volume": wf["volume"].tolist(),
            "slope": np.round(slope, 1).tolist(),
        }
    )


@router.get("/breaths")
def get_breaths(
    file: str = Query(..., description="capture CSV filename from /api/index"),
    baseline: str = Query("zero", description="zero | auto | slope | <numeric offset>"),
    hysteresis: float = Query(0.0, ge=0.0),
    slope: float = Query(0.0, ge=0.0, description="level-crossing rise-rate gate"),
    sdelta: float = Query(100.0, ge=0.0, description="slope-mode jump threshold"),
    swin: float = Query(0.32, ge=0.04, description="slope-mode trend window (s)"),
    srefr: float = Query(1.0, ge=0.0, description="slope-mode refractory gap (s)"),
    sguard: float = Query(100.0, ge=0.0, description="slope-mode expiratory guard"),
    speak: str = Query("mean", description='slope-mode peak-min (L/min) or "mean"'),
    ds: Dataset = Depends(get_dataset),
):
    _require_valid(ds, file)

    speak_val: float | str = "mean" if speak == "mean" else _as_float(speak, 60.0)
    wf = load_waveform(ds.data_dir / file)
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
            slope_peak_min=speak_val,
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
        slope_peak_min=speak_val,
    )
    breaths = add_metrics(breaths, wf)
    return denan({"breaths": breaths.to_dict(orient="records"), "baseline": base_val})


def _as_float(text: str, default: float) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default
