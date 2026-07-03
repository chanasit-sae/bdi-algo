"""Asynchrony detection + notification API.

    GET /api/double-triggers?file=...&<segmentation params>&ratio=&ti_ref=&require_stacking=&stack_ratio=
    GET /api/notifications?<segmentation params>&ratio=&ti_ref=&...&patient_id=&include_disconnected=

Segmentation query params are identical to /api/breaths (the pair timing the
formula compares comes directly from the chosen breath boundaries). See
backend/asynchrony.py for the detection formula itself.

/api/notifications scans every capture (or one patient's) and flattens all
flagged events into one notification list. Only double-triggering exists today
(`type: "double_trigger"`), but the shape has room for other asynchrony types
later. Each notification echoes the segmentation params that produced it, so a
client can reproduce the exact same breath boundaries when jumping to a
detail view (e.g. the Viewer page).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from parser import load_waveform
from asynchrony import detect_double_triggers
from auto_peep import detect_auto_peep

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


@router.get("/auto-peep")
def get_auto_peep(
    file: str = Query(..., description="capture CSV filename from /api/index"),
    baseline: str = Query("slope", description="zero | auto | slope | <numeric offset>"),
    hysteresis: float = Query(0.0, ge=0.0),
    slope: float = Query(0.0, ge=0.0, description="level-crossing rise-rate gate"),
    sdelta: float = Query(100.0, ge=0.0, description="slope-mode jump threshold"),
    swin: float = Query(0.32, ge=0.04, description="slope-mode trend window (s)"),
    srefr: float = Query(1.0, ge=0.0, description="slope-mode refractory gap (s)"),
    sguard: float = Query(100.0, ge=0.0, description="slope-mode expiratory guard"),
    speak: str = Query("mean", description='slope-mode peak-min (L/min) or "mean"'),
    flow_frac: float = Query(0.15, gt=0.0, description="min fraction of expiratory flow still present at end-expiration"),
    flow_abs: float = Query(2.0, ge=0.0, description="min absolute residual end-expiratory flow (L/min) noise floor"),
    peep_min: float = Query(1.0, description="min end-expiratory pressure excess over set PEEP (cmH2O)"),
    require_pressure: bool = Query(True, description="require the pressure signature too (flow + pressure mix)"),
    ds: Dataset = Depends(get_dataset),
):
    require_valid(ds, file)

    speak_val: float | str = "mean" if speak == "mean" else as_float(speak, 60.0)
    wf = load_waveform(ds.data_dir / file)
    breaths, base_val = segment_from_params(
        wf, file, baseline, hysteresis, slope, sdelta, swin, srefr, sguard, speak_val
    )
    events = detect_auto_peep(
        wf, breaths, flow_frac=flow_frac, flow_abs=flow_abs,
        peep_min=peep_min, require_pressure=require_pressure,
    )
    return denan(
        {
            "events": events.to_dict(orient="records"),
            "n_breaths": len(breaths),
            "baseline": base_val,
            "formula": {
                "criterion": "flow_residual_frac > flow_frac (+ peep_delta > peep_min)",
                "flow_frac": flow_frac,
                "flow_abs": flow_abs,
                "peep_min": peep_min,
                "require_pressure": require_pressure,
            },
        }
    )


_EVENT_FIELDS = (
    "breath_idx_a", "breath_idx_b", "t_insp_start_a", "t_insp_start_b", "t_exp_end_b",
    "te_gap", "ti_ref", "te_ti_ratio", "vt_pair", "vt_ratio", "stacked",
)

_AUTO_PEEP_FIELDS = (
    "breath_idx", "t_insp_start", "t_exp_end", "ti_sec", "te_sec",
    "flow_residual_frac", "peep_delta", "eef", "z_ref", "pressure_flag",
)


@router.get("/notifications")
def get_notifications(
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
    flow_frac: float = Query(0.15, gt=0.0, description="auto-PEEP: min fraction of expiratory flow still present at end-expiration"),
    flow_abs: float = Query(2.0, ge=0.0, description="auto-PEEP: min absolute residual end-expiratory flow (L/min)"),
    peep_min: float = Query(1.0, description="auto-PEEP: min end-expiratory pressure excess over set PEEP (cmH2O)"),
    require_pressure: bool = Query(True, description="auto-PEEP: require the pressure signature too (flow + pressure mix)"),
    patient_id: str | None = Query(None, description="restrict the scan to one patient; omit to scan the whole dataset"),
    include_disconnected: bool = Query(False, description="also scan captures flagged disconnected (flat flow, no real breathing -> never produces events, skipped by default for speed)"),
    ds: Dataset = Depends(get_dataset),
):
    speak_val: float | str = "mean" if speak == "mean" else as_float(speak, 60.0)
    seg_params = {
        "baseline": baseline, "hysteresis": hysteresis, "slope": slope,
        "sdelta": sdelta, "swin": swin, "srefr": srefr, "sguard": sguard, "speak": speak,
    }

    notifications: list[dict] = []
    scanned = 0
    for p in ds.patients:
        if patient_id and p["patient_id"] != patient_id:
            continue
        for c in p["captures"]:
            if not include_disconnected and not c["connected"]:
                continue
            fname = c["raw_data"]
            wf = load_waveform(ds.data_dir / fname)
            breaths, _base_val = segment_from_params(
                wf, fname, baseline, hysteresis, slope, sdelta, swin, srefr, sguard, speak_val
            )
            scanned += 1
            events = detect_double_triggers(
                breaths, ratio=ratio, ti_ref=ti_ref,
                require_stacking=require_stacking, stack_ratio=stack_ratio,
            )
            for e in events.to_dict(orient="records"):
                notifications.append({
                    "type": "double_trigger",
                    "patient_id": p["patient_id"],
                    "raw_data": fname,
                    "day": c["day"],
                    "time": c["time"],
                    **{k: e[k] for k in _EVENT_FIELDS},
                    "segmentation": seg_params,
                })

            ap_events = detect_auto_peep(
                wf, breaths, flow_frac=flow_frac, flow_abs=flow_abs,
                peep_min=peep_min, require_pressure=require_pressure,
            )
            for e in ap_events.to_dict(orient="records"):
                notifications.append({
                    "type": "auto_peep",
                    "patient_id": p["patient_id"],
                    "raw_data": fname,
                    "day": c["day"],
                    "time": c["time"],
                    "breath_idx_a": e["breath_idx"],
                    **{k: e[k] for k in _AUTO_PEEP_FIELDS},
                    "segmentation": seg_params,
                })

    return denan(
        {
            "notifications": notifications,
            "scanned_captures": scanned,
            "formula": {
                "criterion": "te_gap < ratio * ti_ref",
                "ratio": ratio,
                "ti_ref": ti_ref,
                "require_stacking": require_stacking,
                "stack_ratio": stack_ratio,
            },
            "auto_peep_formula": {
                "criterion": "flow_residual_frac > flow_frac (+ peep_delta > peep_min)",
                "flow_frac": flow_frac,
                "flow_abs": flow_abs,
                "peep_min": peep_min,
                "require_pressure": require_pressure,
            },
        }
    )
