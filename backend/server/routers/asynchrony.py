"""Asynchrony detection + notification API.

    GET /api/asynchrony?file=...&<segmentation>&<double-trigger>&<ineffective-effort>&<auto-peep>
    GET /api/auto-peep?file=...&<segmentation>&<auto-peep formula>   (single capture, auto-PEEP only)
    GET /api/notifications?<same params>&patient_id=&include_disconnected=&page=&page_size=

Segmentation query params are identical to /api/breaths (event timing comes
directly from the chosen breath boundaries). See backend/asynchrony.py,
backend/ineffective_effort.py, and backend/auto_peep.py for the three
detection formulas.

Every event, regardless of `type`, carries two generalized fields so the
frontend never needs per-type branching: `t0`/`t1` (the span to highlight on
a chart) and `detail` (a short human-readable summary). Type-specific raw
fields (te_gap, flow_prominence, peep_delta, ...) are also included for
anyone who wants the full detail.

/api/notifications scans every capture (or one patient's), runs all three
detectors on each, and flattens everything into one paginated, most-recent-first
list (sorted by capture day desc, then time desc — captures don't carry an
absolute date, so cross-patient ordering is approximate). Each notification
echoes the segmentation + formula params that produced it, so a client can
reproduce the exact same event elsewhere (e.g. the Viewer page).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from parser import load_waveform
from asynchrony import detect_double_triggers
from ineffective_effort import detect_ineffective_efforts
from auto_peep import detect_auto_peep

from ..dataset import Dataset, denan
from ..deps import get_dataset
from ..segmentation import segment_from_params
from ..util import require_valid, as_float

router = APIRouter(prefix="/api", tags=["asynchrony"])

_SEG_KEYS = ("baseline", "hysteresis", "slope", "sdelta", "swin", "srefr", "sguard", "speak")
_DT_FIELDS = ("breath_idx_a", "breath_idx_b", "te_gap", "ti_ref", "te_ti_ratio", "vt_pair", "vt_ratio", "stacked")
_IE_FIELDS = ("breath_idx_a", "breath_idx_b", "t_flow_peak", "t_pressure_trough",
              "flow_prominence", "pressure_prominence", "dt_sec")
_AP_FIELDS = ("flow_residual_frac", "peep_delta", "eef", "z_ref",
              "eep", "set_peep", "residual", "peak_mag", "pressure_flag")


def segmentation_params(
    baseline: str = Query("slope", description="zero | auto | slope | <numeric offset>"),
    hysteresis: float = Query(0.0, ge=0.0),
    slope: float = Query(0.0, ge=0.0, description="level-crossing rise-rate gate"),
    sdelta: float = Query(100.0, ge=0.0, description="slope-mode jump threshold"),
    swin: float = Query(0.32, ge=0.04, description="slope-mode trend window (s)"),
    srefr: float = Query(1.0, ge=0.0, description="slope-mode refractory gap (s)"),
    sguard: float = Query(100.0, ge=0.0, description="slope-mode expiratory guard"),
    speak: str = Query("mean", description='slope-mode peak-min (L/min) or "mean"'),
) -> dict:
    speak_val: float | str = "mean" if speak == "mean" else as_float(speak, 60.0)
    return {
        "baseline": baseline, "hysteresis": hysteresis, "slope": slope, "sdelta": sdelta,
        "swin": swin, "srefr": srefr, "sguard": sguard, "speak": speak, "speak_val": speak_val,
    }


def dt_params(
    ratio: float = Query(0.5, gt=0.0, description="Te/Ti_ref cutoff; Thille et al. 2006 default is 0.5"),
    ti_ref: str = Query("pair", description="self | pair | capture"),
    require_stacking: bool = Query(False, description="also require combined Vt > stack_ratio x 2x median Vt"),
    stack_ratio: float = Query(1.5, gt=0.0),
) -> dict:
    return {"ratio": ratio, "ti_ref": ti_ref, "require_stacking": require_stacking, "stack_ratio": stack_ratio}


def ie_params(
    flow_prominence: float = Query(25.0, ge=0.0, description="min flow-bump rise (L/min), measured within bump_lookback_sec, to count as an effort"),
    flow_prominence_max: float = Query(60.0, gt=0.0, description="bumps at/above this are treated as a missed real breath, not flagged"),
    pressure_prominence: float = Query(1.5, ge=0.0, description="min pressure-dip depth (cmH2O), measured within bump_lookback_sec, to count as an effort"),
    concurrent_tol_sec: float = Query(0.3, gt=0.0, description="max time gap between the flow bump and pressure dip"),
    bump_lookback_sec: float = Query(0.4, gt=0.0, description="how far back prominence is measured; bounds it to a local, not window-wide, reference"),
) -> dict:
    return {
        "flow_prominence": flow_prominence, "flow_prominence_max": flow_prominence_max,
        "pressure_prominence": pressure_prominence, "concurrent_tol_sec": concurrent_tol_sec,
        "bump_lookback_sec": bump_lookback_sec,
    }


def auto_peep_params(
    flow_frac: float = Query(0.15, ge=0.0, description="min fraction of expiratory flow still present at end-expiration"),
    flow_abs: float = Query(2.0, ge=0.0, description="min absolute residual end-expiratory flow (L/min), noise floor"),
    peep_min: float = Query(1.0, ge=0.0, description="min end-expiratory pressure excess over set PEEP (cmH2O)"),
    require_pressure: bool = Query(True, description="require the pressure signature too (the flow+pressure mix)"),
) -> dict:
    return {
        "flow_frac": flow_frac, "flow_abs": flow_abs,
        "peep_min": peep_min, "require_pressure": require_pressure,
    }


def _scan_capture(wf, fname: str, seg: dict, dt: dict, ie: dict, ap: dict) -> tuple[list[dict], float, int]:
    """Run both detectors on one capture's waveform; returns (events, baseline, n_breaths)."""
    breaths, base_val = segment_from_params(
        wf, fname, seg["baseline"], seg["hysteresis"], seg["slope"], seg["sdelta"],
        seg["swin"], seg["srefr"], seg["sguard"], seg["speak_val"],
    )

    events: list[dict] = []

    dt_events = detect_double_triggers(
        breaths, ratio=dt["ratio"], ti_ref=dt["ti_ref"],
        require_stacking=dt["require_stacking"], stack_ratio=dt["stack_ratio"],
    )
    for e in dt_events.to_dict(orient="records"):
        events.append({
            "type": "double_trigger",
            "t0": e["t_insp_start_a"],
            "t1": e["t_exp_end_b"],
            "detail": f"Te/Ti {e['te_ti_ratio']:.2f}" + (" · stacked" if e["stacked"] else ""),
            **{k: e[k] for k in _DT_FIELDS},
        })

    ie_events = detect_ineffective_efforts(
        breaths, wf["flow"].to_numpy(), wf["pressure"].to_numpy(),
        flow_prominence=ie["flow_prominence"], flow_prominence_max=ie["flow_prominence_max"],
        pressure_prominence=ie["pressure_prominence"], concurrent_tol_sec=ie["concurrent_tol_sec"],
        bump_lookback_sec=ie["bump_lookback_sec"],
    )
    for e in ie_events.to_dict(orient="records"):
        events.append({
            "type": "ineffective_effort",
            "t0": e["t_start"],
            "t1": e["t_end"],
            "detail": f"flow +{e['flow_prominence']:.0f} L/min · pressure -{e['pressure_prominence']:.1f} cmH2O",
            **{k: e[k] for k in _IE_FIELDS},
        })

    ap_events = detect_auto_peep(
        breaths, wf["flow"].to_numpy(), wf["pressure"].to_numpy(),
        flow_frac=ap["flow_frac"], flow_abs=ap["flow_abs"],
        peep_min=ap["peep_min"], require_pressure=ap["require_pressure"],
    )
    for e in ap_events.to_dict(orient="records"):
        events.append({
            "type": "auto_peep",
            "t0": e["t_insp_end"],
            "t1": e["t_exp_end"],
            "detail": (
                f"residual {e['flow_residual_frac']:.0%} · PEEP +{e['peep_delta']:.1f} cmH2O · "
                + ("flow+pressure" if e["pressure_flag"] else "flow only")
            ),
            "breath_idx_a": e["breath_idx"],
            **{k: e[k] for k in _AP_FIELDS},
        })

    return events, base_val, len(breaths)


def _formula_block(dt: dict, ie: dict, ap: dict) -> dict:
    return {
        "double_trigger": {"criterion": "te_gap < ratio * ti_ref", **dt},
        "ineffective_effort": {"criterion": "concordant flow-bump + pressure-dip within concurrent_tol_sec", **ie},
        "auto_peep": {"criterion": "flow_residual_frac > flow_frac (+ peep_delta > peep_min)", **ap},
    }


@router.get("/asynchrony")
def get_asynchrony(
    file: str = Query(..., description="capture CSV filename from /api/index"),
    seg: dict = Depends(segmentation_params),
    dt: dict = Depends(dt_params),
    ie: dict = Depends(ie_params),
    ap: dict = Depends(auto_peep_params),
    ds: Dataset = Depends(get_dataset),
):
    """All asynchrony events (every detector) for one capture."""
    require_valid(ds, file)
    wf = load_waveform(ds.data_dir / file)
    events, base_val, n_breaths = _scan_capture(wf, file, seg, dt, ie, ap)
    return denan({
        "events": events,
        "n_breaths": n_breaths,
        "baseline": base_val,
        "formula": _formula_block(dt, ie, ap),
    })


@router.get("/auto-peep")
def get_auto_peep_only(
    file: str = Query(..., description="capture CSV filename from /api/index"),
    seg: dict = Depends(segmentation_params),
    ap: dict = Depends(auto_peep_params),
    ds: Dataset = Depends(get_dataset),
):
    """Auto-PEEP events only, for one capture (see auto-peep.md)."""
    require_valid(ds, file)
    wf = load_waveform(ds.data_dir / file)
    breaths, base_val = segment_from_params(
        wf, file, seg["baseline"], seg["hysteresis"], seg["slope"], seg["sdelta"],
        seg["swin"], seg["srefr"], seg["sguard"], seg["speak_val"],
    )
    events = detect_auto_peep(
        breaths, wf["flow"].to_numpy(), wf["pressure"].to_numpy(),
        flow_frac=ap["flow_frac"], flow_abs=ap["flow_abs"],
        peep_min=ap["peep_min"], require_pressure=ap["require_pressure"],
    )
    return denan({
        "events": events.to_dict(orient="records"),
        "n_breaths": len(breaths),
        "baseline": base_val,
        "formula": {"criterion": "flow_residual_frac > flow_frac (+ peep_delta > peep_min)", **ap},
    })


def _notification_sort_key(n: dict):
    day = n["day"] if n["day"] is not None else -1
    return (day, n["time"] or "")


def _scan_dataset(
    ds: Dataset, seg: dict, dt: dict, ie: dict, ap: dict,
    patient_id: str | None, include_disconnected: bool,
) -> tuple[list[dict], int]:
    """Scan every capture (or one patient's) and return the full, sorted,
    unpaginated notification list. This is the expensive part of
    /api/notifications — cached by the caller (see `notification_cache` on
    Dataset) since these params rarely change between requests.
    """
    seg_echo = {k: seg[k] for k in _SEG_KEYS}

    all_notifications: list[dict] = []
    scanned = 0
    for p in ds.patients:
        if patient_id and p["patient_id"] != patient_id:
            continue
        for c in p["captures"]:
            if not include_disconnected and not c["connected"]:
                continue
            fname = c["raw_data"]
            wf = load_waveform(ds.data_dir / fname)
            events, _base_val, _n = _scan_capture(wf, fname, seg, dt, ie, ap)
            scanned += 1
            for e in events:
                all_notifications.append({
                    "patient_id": p["patient_id"],
                    "raw_data": fname,
                    "day": c["day"],
                    "time": c["time"],
                    **e,
                    "segmentation": seg_echo,
                })

    all_notifications.sort(key=_notification_sort_key, reverse=True)
    return all_notifications, scanned


def _notif_cache_key(seg, dt, ie, ap, patient_id, include_disconnected):
    """A hashable key covering every param that affects the scan result."""
    return (
        tuple(sorted(seg.items())), tuple(sorted(dt.items())),
        tuple(sorted(ie.items())), tuple(sorted(ap.items())),
        patient_id, include_disconnected,
    )


@router.get("/notifications")
def get_notifications(
    seg: dict = Depends(segmentation_params),
    dt: dict = Depends(dt_params),
    ie: dict = Depends(ie_params),
    ap: dict = Depends(auto_peep_params),
    patient_id: str | None = Query(None, description="restrict the scan to one patient; omit to scan the whole dataset"),
    include_disconnected: bool = Query(False, description="also scan captures flagged disconnected (flat flow, no real breathing -> never produces events, skipped by default for speed)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    ds: Dataset = Depends(get_dataset),
):
    key = _notif_cache_key(seg, dt, ie, ap, patient_id, include_disconnected)
    cached = ds.notification_cache.get(key)
    if cached is None:
        cached = _scan_dataset(ds, seg, dt, ie, ap, patient_id, include_disconnected)
        ds.notification_cache[key] = cached
    all_notifications, scanned = cached

    total = len(all_notifications)
    start = (page - 1) * page_size
    page_items = all_notifications[start : start + page_size]

    return denan({
        "notifications": page_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, -(-total // page_size)),
        "scanned_captures": scanned,
        "formula": _formula_block(dt, ie, ap),
    })


def warmup_notifications(ds: Dataset) -> None:
    """Pre-run the exact scan the Notifications page always requests (it has
    no tunable controls, so this is the only param combination it ever asks
    for) and cache it, so the very first visitor never waits on a full scan —
    called once at server startup, mirroring how `ds.index` is force-built
    eagerly in main.py's lifespan.
    """
    seg = segmentation_params(
        baseline="slope", hysteresis=0.0, slope=0.0, sdelta=100.0,
        swin=0.32, srefr=1.0, sguard=100.0, speak="mean",
    )
    dt = dt_params(ratio=0.5, ti_ref="pair", require_stacking=False, stack_ratio=1.5)
    ie = ie_params(
        flow_prominence=25.0, flow_prominence_max=60.0,
        pressure_prominence=1.5, concurrent_tol_sec=0.3, bump_lookback_sec=0.4,
    )
    ap = auto_peep_params(flow_frac=0.15, flow_abs=2.0, peep_min=1.0, require_pressure=True)
    key = _notif_cache_key(seg, dt, ie, ap, None, False)
    ds.notification_cache[key] = _scan_dataset(ds, seg, dt, ie, ap, None, False)
