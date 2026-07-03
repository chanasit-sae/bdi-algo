"""Waveform + breath-segmentation API.

Endpoints (all under /api):
    GET /api/index                     patient / capture metadata tree
    GET /api/waveform?file=...         raw Flow/Pressure/Volume + flow slope
    GET /api/breaths?file=...&...      segmented breaths with derived metrics

The segmentation query parameters mirror the knobs in breath_segment.py.
"""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, Query

from parser import load_waveform, SAMPLE_RATE_HZ
from breath_metrics import add_metrics

from ..dataset import Dataset, denan
from ..deps import get_dataset
from ..segmentation import segment_from_params
from ..util import require_valid, as_float

router = APIRouter(prefix="/api", tags=["waveform"])


@router.get("/index")
def get_index(ds: Dataset = Depends(get_dataset)):
    """Patient/capture metadata tree (the `valid` file set is kept server-side)."""
    return denan({"patients": ds.patients})


@router.get("/waveform")
def get_waveform(
    file: str = Query(..., description="capture CSV filename from /api/index"),
    ds: Dataset = Depends(get_dataset),
):
    require_valid(ds, file)
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
    require_valid(ds, file)

    speak_val: float | str = "mean" if speak == "mean" else as_float(speak, 60.0)
    wf = load_waveform(ds.data_dir / file)
    breaths, base_val = segment_from_params(
        wf, file, baseline, hysteresis, slope, sdelta, swin, srefr, sguard, speak_val
    )
    breaths = add_metrics(breaths, wf)
    return denan({"breaths": breaths.to_dict(orient="records"), "baseline": base_val})
