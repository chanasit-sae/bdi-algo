"""Asynchrony detection + notification API.

    GET /api/asynchrony?file=...&<segmentation>&<double-trigger>&<ineffective-effort>&<auto-peep>&<flow-starvation>
    GET /api/auto-peep?file=...&<segmentation>&<auto-peep formula>   (single capture, auto-PEEP only)
    GET /api/flow-starvation?file=...&<segmentation>&<flow-starvation formula>   (single capture, flow-starvation only)
    GET /api/mechanical-power?<segmentation>&<mp formula>&patient_id=&include_disconnected=   (per-patient, not per-capture)
    GET /api/asynchrony-index?<segmentation>&<dt/ie/ap/fs formulas>&patient_id=   (per-patient, not per-capture)
    GET /api/notifications?<same params>&patient_id=&include_disconnected=&types=&page=&page_size=

Segmentation query params are identical to /api/breaths (event timing comes
directly from the chosen breath boundaries). See backend/asynchrony.py,
backend/ineffective_effort.py, backend/auto_peep.py, backend/flow_starvation.py,
and backend/mechanical_power.py for the detection formulas.

Every event, regardless of `type`, carries two generalized fields so the
frontend never needs per-type branching: `t0`/`t1` (the span to highlight on
a chart) and `detail` (a short human-readable summary). Type-specific raw
fields (te_gap, flow_prominence, peep_delta, ...) are also included for
anyone who wants the full detail. Mechanical power and the asynchrony index
are both exceptions to "a chart span" -- they're per-patient aggregates, not
single breath events, so their `t0`/`t1` are null; see mechanical_power.py and
_patient_asynchrony_index below.

/api/notifications is backed by a `NotificationScan` (see dataset.py): captures
are sorted most-recent-first once, then scanned lazily, one at a time, with
each found event appended straight to a shared results list — a page request
only advances the scan until it has enough results to answer that page, so
opening the Notifications page never waits on the whole dataset, and no
capture is ever scanned twice for the same params. A background task started
at server boot (main.py) advances the same shared scan toward completion, so
later requests increasingly find it already done. Mechanical power and the
asynchrony index are each merged in alongside it via their own per-patient
NotificationScan (see get_or_create_mp_scan/get_or_create_ai_scan), computed
lazily and cached (ds.mp_cache/ds.asynchrony_index_cache) rather than advanced
per-capture, since each needs a patient's whole capture set to mean anything.

Note: mp_params and ai_params both have a concept of "threshold" but use
different query param names (`threshold` vs `ai_threshold`) -- FastAPI binds
same-named params from different Depends() to the same query key when both
are used on one endpoint, so giving them the same name would make the two
thresholds impossible to set independently (verified this the hard way).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from parser import load_waveform
from asynchrony import detect_double_triggers
from ineffective_effort import detect_ineffective_efforts
from auto_peep import detect_auto_peep
from flow_starvation import detect_flow_starvation
from mechanical_power import capture_hours, compute_breath_mp, rolling_patient_mp

from ..dataset import Dataset, NotificationScan, denan
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
_FS_FIELDS = ("breath_idx_a", "dip_pressure", "prominence_before", "prominence_after", "flow_range")


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


def flow_starvation_params(
    dip_prominence: float = Query(2.0, ge=0.0, description="min rise-before AND rise-after (cmH2O) around a candidate inspiratory pressure notch"),
    lookback_sec: float = Query(0.4, gt=0.0, description="how far back/forward the notch's prominence is measured; bounds it to a local, not window-wide, reference"),
    require_constant_flow: bool = Query(False, description="also require the inspiratory flow trace to stay flat (volume-control-like); off by default"),
    flow_range_max: float = Query(20.0, gt=0.0, description="max inspiratory flow range (L/min) allowed when require_constant_flow is on"),
) -> dict:
    return {
        "dip_prominence": dip_prominence, "lookback_sec": lookback_sec,
        "require_constant_flow": require_constant_flow, "flow_range_max": flow_range_max,
    }


def mp_params(
    threshold: float = Query(17.0, ge=0.0, description="alert once a patient's trailing rolling-average mechanical power (J/min) reaches this; Serpa Neto et al. 2018 puts elevated mortality risk around 17-19 J/min"),
    window_hours: float = Query(24.0, gt=0.0, description="trailing window (hours), ending at the patient's most recent capture, the rolling average is computed over"),
) -> dict:
    return {"threshold": threshold, "window_hours": window_hours}


def ai_params(
    # aliased to ai_threshold -- mp_params also has a query param literally
    # named "threshold", and FastAPI binds same-named params from different
    # Depends() to the same query key when both are used together on one
    # endpoint (verified: ?threshold=5 was silently setting BOTH MP's and
    # AI's threshold at once). The alias keeps them independently settable;
    # the dict key stays "threshold" since nothing downstream needs to know
    # about the query-string rename.
    threshold: float = Query(10.0, alias="ai_threshold", ge=0.0, le=100.0, description="alert once a patient's asynchrony index (%) reaches this"),
) -> dict:
    return {"threshold": threshold}


def _scan_capture(wf, fname: str, seg: dict, dt: dict, ie: dict, ap: dict, fs: dict) -> tuple[list[dict], float, int]:
    """Run every detector on one capture's waveform; returns (events, baseline, n_breaths)."""
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

    fs_events = detect_flow_starvation(
        breaths, wf["flow"].to_numpy(), wf["pressure"].to_numpy(),
        dip_prominence=fs["dip_prominence"], lookback_sec=fs["lookback_sec"],
        require_constant_flow=fs["require_constant_flow"], flow_range_max=fs["flow_range_max"],
    )
    for e in fs_events.to_dict(orient="records"):
        scoop = min(e["prominence_before"], e["prominence_after"])
        events.append({
            "type": "flow_starvation",
            "t0": e["t_start"],
            "t1": e["t_end"],
            "detail": f"pressure scoop -{scoop:.1f} cmH2O",
            **{k: e[k] for k in _FS_FIELDS},
        })

    return events, base_val, len(breaths)


def _formula_block(dt: dict, ie: dict, ap: dict, fs: dict, mp: dict, ai: dict) -> dict:
    return {
        "double_trigger": {"criterion": "te_gap < ratio * ti_ref", **dt},
        "ineffective_effort": {"criterion": "concordant flow-bump + pressure-dip within concurrent_tol_sec", **ie},
        "auto_peep": {"criterion": "flow_residual_frac > flow_frac (+ peep_delta > peep_min)", **ap},
        "flow_starvation": {"criterion": "rise-dip-rise notch in inspiratory pressure, both sides >= dip_prominence", **fs},
        "mechanical_power": {"criterion": "trailing rolling-average mp_j_per_min >= threshold", **mp},
        "asynchrony_index": {"criterion": "asynchrony_index (%) >= threshold", **ai},
    }


def _patient_mp_raw(ds: Dataset, seg: dict, patient: dict, window_hours: float, include_disconnected: bool) -> dict | None:
    """Trailing rolling-average mechanical power for one patient, cached per
    (patient, segmentation, window) -- NOT per threshold, so the same raw
    number can be reused whether it's being checked against 17.0 or 20.0.

    Captures are walked most-recent-first and stop as soon as one falls more
    than `window_hours` before the patient's latest capture -- the same
    early-exit bounding idea as `NotificationScan`, just per-patient instead
    of dataset-wide, since a rolling average never needs captures outside its
    own window.
    """
    key = (patient["patient_id"], tuple(sorted(seg.items())), window_hours, include_disconnected)
    if key in ds.mp_cache:
        return ds.mp_cache[key]

    caps = sorted(patient["captures"], key=_capture_sort_key, reverse=True)
    if not include_disconnected:
        caps = [c for c in caps if c["connected"]]

    accumulated = []
    cutoff = None
    for c in caps:
        h = capture_hours(c["day"], c["time"])
        if cutoff is None:
            cutoff = h - window_hours
        elif h < cutoff:
            break
        wf = load_waveform(ds.data_dir / c["raw_data"])
        breaths, _base_val = segment_from_params(
            wf, c["raw_data"], seg["baseline"], seg["hysteresis"], seg["slope"], seg["sdelta"],
            seg["swin"], seg["srefr"], seg["sguard"], seg["speak_val"],
        )
        mp_df = compute_breath_mp(breaths, wf["pressure"].to_numpy(), wf["volume"].to_numpy())
        accumulated.append((c["day"], c["time"], c["raw_data"], mp_df))

    status = rolling_patient_mp(accumulated, window_hours=window_hours)
    ds.mp_cache[key] = status
    return status


def _mp_notification(patient: dict, status: dict | None, threshold: float, window_hours: float, seg: dict) -> dict | None:
    """Notification-shaped dict for one patient's MP status, or None if
    there's no status yet or it's below threshold."""
    if status is None or status["avg_mp_j_per_min"] < threshold:
        return None
    return {
        "type": "mechanical_power",
        "patient_id": patient["patient_id"],
        "raw_data": status["latest_raw_data"],
        "day": status["latest_day"],
        "time": status["latest_time"],
        "t0": None,
        "t1": None,
        "detail": f"avg {status['avg_mp_j_per_min']:.1f} J/min over {status['n_breaths']} breaths ({window_hours:.0f}h window)",
        "avg_mp_j_per_min": status["avg_mp_j_per_min"],
        "n_breaths": status["n_breaths"],
        "n_captures_total": status["n_captures_total"],
        "threshold": threshold,
        "window_hours": window_hours,
        "segmentation": {k: seg[k] for k in _SEG_KEYS},
    }


def _all_patient_mp_notifications(
    ds: Dataset, seg: dict, mp: dict, patient_id: str | None, include_disconnected: bool
) -> list[dict]:
    """Every patient at/above threshold, computed eagerly for every patient in
    one call. Used by the dedicated /api/mechanical-power endpoint, where
    there's no pagination story and running the whole thing synchronously is
    expected. NOT used by /api/notifications -- see `get_or_create_mp_scan` /
    `advance_mp_scan` below for the lazy version that keeps the Notifications
    page from waiting on every patient's rolling window just to answer page 1.
    """
    out = []
    for p in ds.patients:
        if patient_id and p["patient_id"] != patient_id:
            continue
        status = _patient_mp_raw(ds, seg, p, mp["window_hours"], include_disconnected)
        notif = _mp_notification(p, status, mp["threshold"], mp["window_hours"], seg)
        if notif is not None:
            out.append(notif)
    return out


def _build_mp_pending(ds: Dataset, patient_id: str | None) -> list[dict]:
    """Every patient this MP scan covers -- metadata only, no waveform
    loading, mirroring `_build_pending`'s per-capture equivalent below."""
    return [p for p in ds.patients if not patient_id or p["patient_id"] == patient_id]


def _mp_scan_key(seg: dict, mp: dict, patient_id: str | None, include_disconnected: bool):
    return (tuple(sorted(seg.items())), tuple(sorted(mp.items())), patient_id, include_disconnected)


def get_or_create_mp_scan(
    ds: Dataset, seg: dict, mp: dict, patient_id: str | None, include_disconnected: bool
) -> NotificationScan:
    """One patient-level scan per distinct param combo, reusing `NotificationScan`
    as-is (its claim/add/mark-scanned bookkeeping doesn't care whether a
    'pending item' is a capture or a whole patient)."""
    key = _mp_scan_key(seg, mp, patient_id, include_disconnected)
    scan = ds.mp_scans.get(key)
    if scan is None:
        scan = NotificationScan(_build_mp_pending(ds, patient_id))
        ds.mp_scans[key] = scan
    return scan


def advance_mp_scan(
    ds: Dataset, scan: NotificationScan, seg: dict, mp: dict, include_disconnected: bool, needed: int
) -> None:
    """Claim and process pending patients until either `scan.results` has at
    least `needed` flagged patients or every patient has been checked -- the
    same bounded-work-per-request pattern as `advance_scan`, just one patient
    at a time instead of one capture at a time, so a Notifications page
    request never blocks on every patient's rolling window either."""
    while len(scan.results) < needed:
        p = scan.claim_next()
        if p is None:
            break
        status = _patient_mp_raw(ds, seg, p, mp["window_hours"], include_disconnected)
        scan.mark_scanned()
        notif = _mp_notification(p, status, mp["threshold"], mp["window_hours"], seg)
        if notif is not None:
            scan.add_result(notif)


def _ai_scan_key(seg: dict, dt: dict, ie: dict, ap: dict, fs: dict, ai: dict, patient_id: str | None):
    return (
        tuple(sorted(seg.items())), tuple(sorted(dt.items())), tuple(sorted(ie.items())),
        tuple(sorted(ap.items())), tuple(sorted(fs.items())), tuple(sorted(ai.items())), patient_id,
    )


def get_or_create_ai_scan(
    ds: Dataset, seg: dict, dt: dict, ie: dict, ap: dict, fs: dict, ai: dict, patient_id: str | None
) -> NotificationScan:
    """Same idea as `get_or_create_mp_scan`, one patient-level scan per param
    combo for the asynchrony index instead of mechanical power."""
    key = _ai_scan_key(seg, dt, ie, ap, fs, ai, patient_id)
    scan = ds.ai_scans.get(key)
    if scan is None:
        scan = NotificationScan(_build_mp_pending(ds, patient_id))
        ds.ai_scans[key] = scan
    return scan


def advance_ai_scan(
    ds: Dataset, scan: NotificationScan, seg: dict, dt: dict, ie: dict, ap: dict, fs: dict, ai: dict, needed: int
) -> None:
    """Claim and process pending patients until `scan.results` has at least
    `needed` flagged patients or every patient has been checked (same bounded
    pattern as `advance_mp_scan`)."""
    while len(scan.results) < needed:
        p = scan.claim_next()
        if p is None:
            break
        result = _patient_asynchrony_index(ds, seg, dt, ie, ap, fs, p)
        scan.mark_scanned()
        notif = _ai_notification(p, result, ai["threshold"], seg)
        if notif is not None:
            scan.add_result(notif)


@router.get("/asynchrony")
def get_asynchrony(
    file: str = Query(..., description="capture CSV filename from /api/index"),
    seg: dict = Depends(segmentation_params),
    dt: dict = Depends(dt_params),
    ie: dict = Depends(ie_params),
    ap: dict = Depends(auto_peep_params),
    fs: dict = Depends(flow_starvation_params),
    mp: dict = Depends(mp_params),
    ai: dict = Depends(ai_params),
    ds: Dataset = Depends(get_dataset),
):
    """All asynchrony events (every detector) for one capture. Mechanical
    power and the asynchrony index are both patient-level (not per-capture)
    so neither is in `events` here -- see /api/mechanical-power,
    /api/asynchrony-index, or /api/notifications -- but their params still
    round-trip through `formula` so a notification's deep link stays intact.
    """
    require_valid(ds, file)
    wf = load_waveform(ds.data_dir / file)
    events, base_val, n_breaths = _scan_capture(wf, file, seg, dt, ie, ap, fs)
    return denan({
        "events": events,
        "n_breaths": n_breaths,
        "baseline": base_val,
        "formula": _formula_block(dt, ie, ap, fs, mp, ai),
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


@router.get("/flow-starvation")
def get_flow_starvation_only(
    file: str = Query(..., description="capture CSV filename from /api/index"),
    seg: dict = Depends(segmentation_params),
    fs: dict = Depends(flow_starvation_params),
    ds: Dataset = Depends(get_dataset),
):
    """Flow-starvation events only, for one capture (see backend/flow_starvation.py)."""
    require_valid(ds, file)
    wf = load_waveform(ds.data_dir / file)
    breaths, base_val = segment_from_params(
        wf, file, seg["baseline"], seg["hysteresis"], seg["slope"], seg["sdelta"],
        seg["swin"], seg["srefr"], seg["sguard"], seg["speak_val"],
    )
    events = detect_flow_starvation(
        breaths, wf["flow"].to_numpy(), wf["pressure"].to_numpy(),
        dip_prominence=fs["dip_prominence"], lookback_sec=fs["lookback_sec"],
        require_constant_flow=fs["require_constant_flow"], flow_range_max=fs["flow_range_max"],
    )
    return denan({
        "events": events.to_dict(orient="records"),
        "n_breaths": len(breaths),
        "baseline": base_val,
        "formula": {"criterion": "rise-dip-rise notch in inspiratory pressure, both sides >= dip_prominence", **fs},
    })


@router.get("/mechanical-power")
def get_mechanical_power(
    seg: dict = Depends(segmentation_params),
    mp: dict = Depends(mp_params),
    patient_id: str | None = Query(None, description="one patient's status; omit to list every patient at/above threshold"),
    include_disconnected: bool = Query(False, description="also include captures flagged disconnected"),
    ds: Dataset = Depends(get_dataset),
):
    """Per-patient rolling mechanical power (see backend/mechanical_power.py).

    With `patient_id`: that patient's full status (returned even if below
    threshold). Without it: every patient currently at/above threshold, in
    the same shape /api/notifications uses for `type: mechanical_power`.
    """
    if patient_id:
        patient = next((p for p in ds.patients if p["patient_id"] == patient_id), None)
        if patient is None:
            return denan({"error": f"unknown patient_id: {patient_id}"})
        status = _patient_mp_raw(ds, seg, patient, mp["window_hours"], include_disconnected)
        return denan({
            "patient_id": patient_id,
            "status": status,
            "above_threshold": bool(status and status["avg_mp_j_per_min"] >= mp["threshold"]),
            "threshold": mp["threshold"],
            "window_hours": mp["window_hours"],
            "formula": {"criterion": "trailing rolling-average mp_j_per_min >= threshold", **mp},
        })

    flagged = _all_patient_mp_notifications(ds, seg, mp, None, include_disconnected)
    return denan({
        "patients": flagged,
        "total": len(flagged),
        "threshold": mp["threshold"],
        "window_hours": mp["window_hours"],
        "formula": {"criterion": "trailing rolling-average mp_j_per_min >= threshold", **mp},
    })


def _patient_asynchrony_index(ds: Dataset, seg: dict, dt: dict, ie: dict, ap: dict, fs: dict, patient: dict) -> dict:
    """asynchrony_index = total flagged-event seconds / total waveform seconds,
    across the patient's connected captures. Cached per (patient, all params).
    Also tracks the most recent capture seen, so a notification built from
    this has somewhere to link/sort by even though the index itself is a
    whole-patient aggregate rather than a single-capture event.
    """
    key = (
        patient["patient_id"], tuple(sorted(seg.items())), tuple(sorted(dt.items())),
        tuple(sorted(ie.items())), tuple(sorted(ap.items())), tuple(sorted(fs.items())),
    )
    if key in ds.asynchrony_index_cache:
        return ds.asynchrony_index_cache[key]

    total_async_sec = 0.0
    total_wave_sec = 0.0
    latest = None  # (day, time, raw_data), most recent by _capture_sort_key
    for c in patient["captures"]:
        if not c["connected"]:
            continue
        if latest is None or _capture_sort_key(c) > _capture_sort_key(latest[3]):
            latest = (c["day"], c["time"], c["raw_data"], c)
        wf = load_waveform(ds.data_dir / c["raw_data"])
        events, _base_val, _n = _scan_capture(wf, c["raw_data"], seg, dt, ie, ap, fs)
        total_wave_sec += float(wf["t_sec"].iloc[-1]) if len(wf) else 0.0
        for e in events:
            if e["t0"] is not None and e["t1"] is not None:
                total_async_sec += e["t1"] - e["t0"]

    result = {
        "patient_id": patient["patient_id"],
        "total_asynchrony_sec": round(total_async_sec, 3),
        "total_waveform_sec": round(total_wave_sec, 3),
        "asynchrony_index": round(total_async_sec / total_wave_sec, 6) if total_wave_sec > 0 else 0.0,
        "latest_day": latest[0] if latest else None,
        "latest_time": latest[1] if latest else None,
        "latest_raw_data": latest[2] if latest else None,
    }
    ds.asynchrony_index_cache[key] = result
    return result


def _ai_notification(patient: dict, result: dict | None, threshold: float, seg: dict) -> dict | None:
    """Notification-shaped dict for one patient's asynchrony index, or None
    if there's no result yet, no waveform time to compute it from, or it's
    below threshold."""
    if result is None or result["latest_raw_data"] is None:
        return None
    pct = result["asynchrony_index"] * 100
    if pct < threshold:
        return None
    return {
        "type": "asynchrony_index",
        "patient_id": patient["patient_id"],
        "raw_data": result["latest_raw_data"],
        "day": result["latest_day"],
        "time": result["latest_time"],
        "t0": None,
        "t1": None,
        "detail": f"asynchrony index {pct:.1f}% ({result['total_asynchrony_sec']:.1f}s / {result['total_waveform_sec']:.1f}s)",
        "asynchrony_index": result["asynchrony_index"],
        "total_asynchrony_sec": result["total_asynchrony_sec"],
        "total_waveform_sec": result["total_waveform_sec"],
        "threshold": threshold,
        "segmentation": {k: seg[k] for k in _SEG_KEYS},
    }


@router.get("/asynchrony-index")
def get_asynchrony_index(
    seg: dict = Depends(segmentation_params),
    dt: dict = Depends(dt_params),
    ie: dict = Depends(ie_params),
    ap: dict = Depends(auto_peep_params),
    fs: dict = Depends(flow_starvation_params),
    patient_id: str | None = Query(None, description="one patient; omit to compute for every patient"),
    ds: Dataset = Depends(get_dataset),
):
    """Per-patient asynchrony index: all_asynchrony_length / all_waveform_length,
    summed across the patient's connected captures using the four breath-level
    detectors (mechanical power has no t0/t1 span, so it isn't part of this).
    """
    if patient_id:
        patient = next((p for p in ds.patients if p["patient_id"] == patient_id), None)
        if patient is None:
            return denan({"error": f"unknown patient_id: {patient_id}"})
        return denan(_patient_asynchrony_index(ds, seg, dt, ie, ap, fs, patient))

    return denan({"patients": [_patient_asynchrony_index(ds, seg, dt, ie, ap, fs, p) for p in ds.patients]})


def _capture_sort_key(capture: dict):
    day = capture["day"] if capture["day"] is not None else -1
    return (day, capture["time"] or "")


def _build_pending(ds: Dataset, patient_id: str | None, include_disconnected: bool) -> list[tuple[dict, dict]]:
    """Every (patient, capture) pair this scan covers, sorted most-recent-first.
    Metadata only — no waveform loading, so this is cheap even for a huge dataset.
    """
    pending = []
    for p in ds.patients:
        if patient_id and p["patient_id"] != patient_id:
            continue
        for c in p["captures"]:
            if not include_disconnected and not c["connected"]:
                continue
            pending.append((p, c))
    pending.sort(key=lambda pc: _capture_sort_key(pc[1]), reverse=True)
    return pending


def _notif_scan_key(seg: dict, dt: dict, ie: dict, ap: dict, fs: dict, patient_id: str | None, include_disconnected: bool):
    """A hashable key covering every param that affects which scan this is."""
    return (
        tuple(sorted(seg.items())), tuple(sorted(dt.items())),
        tuple(sorted(ie.items())), tuple(sorted(ap.items())), tuple(sorted(fs.items())),
        patient_id, include_disconnected,
    )


def get_or_create_scan(
    ds: Dataset, seg: dict, dt: dict, ie: dict, ap: dict, fs: dict,
    patient_id: str | None, include_disconnected: bool,
) -> NotificationScan:
    key = _notif_scan_key(seg, dt, ie, ap, fs, patient_id, include_disconnected)
    scan = ds.notification_scans.get(key)
    if scan is None:
        scan = NotificationScan(_build_pending(ds, patient_id, include_disconnected))
        ds.notification_scans[key] = scan
    return scan


def advance_scan(ds: Dataset, scan: NotificationScan, seg: dict, dt: dict, ie: dict, ap: dict, fs: dict, needed: int) -> None:
    """Claim and process pending captures (most-recent-first) until either
    `scan.results` has at least `needed` entries or the scan is exhausted.
    The actual per-capture work happens without holding the scan's lock, so
    this can be called concurrently (e.g. a live request racing the
    background warmup task) without one blocking the other for long.
    """
    seg_echo = {k: seg[k] for k in _SEG_KEYS}
    while len(scan.results) < needed:
        item = scan.claim_next()
        if item is None:
            break
        p, c = item
        fname = c["raw_data"]
        wf = load_waveform(ds.data_dir / fname)
        events, _base_val, _n = _scan_capture(wf, fname, seg, dt, ie, ap, fs)
        scan.mark_scanned()
        for e in events:
            scan.add_result({
                "patient_id": p["patient_id"],
                "raw_data": fname,
                "day": c["day"],
                "time": c["time"],
                **e,
                "segmentation": seg_echo,
            })


@router.get("/notifications")
def get_notifications(
    seg: dict = Depends(segmentation_params),
    dt: dict = Depends(dt_params),
    ie: dict = Depends(ie_params),
    ap: dict = Depends(auto_peep_params),
    fs: dict = Depends(flow_starvation_params),
    mp: dict = Depends(mp_params),
    ai: dict = Depends(ai_params),
    patient_id: str | None = Query(None, description="restrict the scan to one patient; omit to scan the whole dataset"),
    include_disconnected: bool = Query(False, description="also scan captures flagged disconnected (flat flow, no real breathing -> never produces events, skipped by default for speed)"),
    types: list[str] | None = Query(None, description="restrict to these notification types (double_trigger, ineffective_effort, auto_peep, flow_starvation, mechanical_power, asynchrony_index); omit for all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    ds: Dataset = Depends(get_dataset),
):
    scan = get_or_create_scan(ds, seg, dt, ie, ap, fs, patient_id, include_disconnected)
    mp_scan = get_or_create_mp_scan(ds, seg, mp, patient_id, include_disconnected)
    ai_scan = get_or_create_ai_scan(ds, seg, dt, ie, ap, fs, ai, patient_id)

    # Mechanical power and the asynchrony index are both patient-level, not
    # per-capture, so neither can share the breath-event scan above -- each
    # gets its own NotificationScan over patients instead of captures,
    # advanced with the exact same "only do enough work for this page" bound,
    # so a page request never waits on the whole capture list OR every
    # patient's own computation either.
    needed = page * page_size
    if not scan.complete and len(scan.results) < needed:
        advance_scan(ds, scan, seg, dt, ie, ap, fs, needed)
    if not mp_scan.complete and len(mp_scan.results) < needed:
        advance_mp_scan(ds, mp_scan, seg, mp, include_disconnected, needed)
    if not ai_scan.complete and len(ai_scan.results) < needed:
        advance_ai_scan(ds, ai_scan, seg, dt, ie, ap, fs, ai, needed)

    # results can complete out of claim-order under concurrent advancing
    # (two captures processed in parallel may finish in either order), so
    # re-sort before slicing rather than trusting append order.
    ordered = sorted(scan.results + mp_scan.results + ai_scan.results, key=_capture_sort_key, reverse=True)
    # Filtered after the merge (not baked into the scans themselves) so the
    # underlying scan stays shared/cached across every filter selection --
    # `types` only ever narrows which already-found results are shown.
    if types:
        allowed = set(types)
        ordered = [n for n in ordered if n["type"] in allowed]
    total = len(ordered)
    start = (page - 1) * page_size
    page_items = ordered[start : start + page_size]

    return denan({
        "notifications": page_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, -(-total // page_size)),
        "scanned_captures": scan.scanned,
        "scan_complete": scan.complete and mp_scan.complete and ai_scan.complete,
        "formula": _formula_block(dt, ie, ap, fs, mp, ai),
    })


def warmup_notifications(ds: Dataset) -> None:
    """Advance the exact scan the Notifications page always requests (it has
    no tunable controls, so this is the only param combination it ever asks
    for) to completion in the background, called once at server startup —
    later requests increasingly find it already fully scanned.
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
    fs = flow_starvation_params(
        dip_prominence=2.0, lookback_sec=0.4, require_constant_flow=False, flow_range_max=20.0,
    )
    scan = get_or_create_scan(ds, seg, dt, ie, ap, fs, None, False)
    advance_scan(ds, scan, seg, dt, ie, ap, fs, needed=len(scan.pending))

    mp = mp_params(threshold=17.0, window_hours=24.0)
    mp_scan = get_or_create_mp_scan(ds, seg, mp, None, False)
    advance_mp_scan(ds, mp_scan, seg, mp, False, needed=len(mp_scan.pending))

    ai = ai_params(threshold=10.0)
    ai_scan = get_or_create_ai_scan(ds, seg, dt, ie, ap, fs, ai, None)
    advance_ai_scan(ds, ai_scan, seg, dt, ie, ap, fs, ai, needed=len(ai_scan.pending))
