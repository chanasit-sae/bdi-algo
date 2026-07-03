"""Double-triggering asynchrony detection API.

    GET /api/double-triggers?file=...&<segmentation params>&ratio=&ti_ref=&require_stacking=&stack_ratio=

Segmentation query params are identical to /api/breaths (the pair timing the
formula compares comes directly from the chosen breath boundaries). See
backend/asynchrony.py for the detection formula itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from parser import load_waveform
from asynchrony import detect_double_triggers

from ..dataset import Dataset, denan
from ..deps import get_dataset
from ..segmentation import segment_from_params
from ..util import require_valid, as_float

router = APIRouter(prefix="/api", tags=["asynchrony"])


@router.get("/double-triggers")
def get_double_triggers(
    file: str = Query(..., description="capture CSV filename from /api/index"),
    baseline: str = Query("slope", description="zero | auto | slope | <numeric offset>"),
    hysteresis: float = Query(0.0, ge=0.0),
    slope: float = Query(0.0, ge=0.0, description="level-crossing rise-rate gate"),
    sdelta: float = Query(100.0, ge=0.0, description="slope-mode jump threshold"),
    swin: float = Query(0.32, ge=0.04, description="slope-mode trend window (s)"),
    srefr: float = Query(1.0, ge=0.0, description="slope-mode refractory gap (s)"),
    sguard: float = Query(100.0, ge=0.0, description="slope-mode expiratory guard"),
    speak: str = Query("mean", description='slope-mode peak-min (L/min) or "mean"'),
    ratio: float = Query(0.5, gt=0.0, description="Te/Ti_ref cutoff; Thille et al. 2006 default is 0.5"),
    ti_ref: str = Query("pair", description="self | pair | capture"),
    require_stacking: bool = Query(False, description="also require combined Vt > stack_ratio x 2x median Vt"),
    stack_ratio: float = Query(1.5, gt=0.0),
    ds: Dataset = Depends(get_dataset),
):
    require_valid(ds, file)

    speak_val: float | str = "mean" if speak == "mean" else as_float(speak, 60.0)
    wf = load_waveform(ds.data_dir / file)
    breaths, base_val = segment_from_params(
        wf, file, baseline, hysteresis, slope, sdelta, swin, srefr, sguard, speak_val
    )
    events = detect_double_triggers(
        breaths, ratio=ratio, ti_ref=ti_ref,
        require_stacking=require_stacking, stack_ratio=stack_ratio,
    )
    return denan(
        {
            "events": events.to_dict(orient="records"),
            "n_breaths": len(breaths),
            "baseline": base_val,
            "formula": {
                "criterion": "te_gap < ratio * ti_ref",
                "ratio": ratio,
                "ti_ref": ti_ref,
                "require_stacking": require_stacking,
                "stack_ratio": stack_ratio,
            },
        }
    )
