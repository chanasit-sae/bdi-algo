// Shared segmentation-parameter defaults + the params-state <-> API-query
// mapping, used by every page that runs breath segmentation.

export const DEFAULT_SEGMENTATION_PARAMS = {
  baselineMode: "slope",
  baseoff: 0,
  hyst: 0,
  slope: 30,
  sdelta: 100,
  swin: 0.32,
  srefr: 1.0,
  sguard: 100,
  speak: 60,
  speakMean: true,
  showDisc: false,
};

export function segmentationQuery(params) {
  return {
    baseline:
      params.baselineMode === "manual"
        ? String(Number(params.baseoff) || 0)
        : params.baselineMode,
    hysteresis: params.hyst,
    slope: params.slope,
    sdelta: params.sdelta,
    swin: params.swin,
    srefr: params.srefr,
    sguard: params.sguard,
    speak: params.speakMean ? "mean" : String(Number(params.speak) || 0),
  };
}

// The inverse of segmentationQuery: given a URL's search params (as produced
// by a notification link — see NotificationList.jsx), rebuild a params object
// a page can seed its state with. Returns null if the URL carries no
// segmentation info at all (e.g. a plain visit with no query string), so
// callers can fall back to DEFAULT_SEGMENTATION_PARAMS.
export function paramsFromSearchParams(sp) {
  if (!sp.has("baseline")) return null;
  const baseline = sp.get("baseline");
  const named = baseline === "zero" || baseline === "auto" || baseline === "slope";
  const speak = sp.get("speak");
  return {
    ...DEFAULT_SEGMENTATION_PARAMS,
    baselineMode: named ? baseline : "manual",
    baseoff: named ? DEFAULT_SEGMENTATION_PARAMS.baseoff : Number(baseline) || 0,
    hyst: Number(sp.get("hysteresis") ?? DEFAULT_SEGMENTATION_PARAMS.hyst),
    slope: Number(sp.get("slope") ?? DEFAULT_SEGMENTATION_PARAMS.slope),
    sdelta: Number(sp.get("sdelta") ?? DEFAULT_SEGMENTATION_PARAMS.sdelta),
    swin: Number(sp.get("swin") ?? DEFAULT_SEGMENTATION_PARAMS.swin),
    srefr: Number(sp.get("srefr") ?? DEFAULT_SEGMENTATION_PARAMS.srefr),
    sguard: Number(sp.get("sguard") ?? DEFAULT_SEGMENTATION_PARAMS.sguard),
    speak: speak === "mean" ? DEFAULT_SEGMENTATION_PARAMS.speak : Number(speak ?? DEFAULT_SEGMENTATION_PARAMS.speak),
    speakMean: speak === "mean",
    // arriving via a deep link: make sure the target capture is selectable
    // regardless of the (crude, flow-range-based) connected heuristic
    showDisc: true,
  };
}

// Defaults for the double-triggering formula itself (separate from breath
// segmentation) — shared by every page that runs the detector
// (NotificationsPage, ViewerPage).
export const DEFAULT_DT_PARAMS = {
  ratio: 0.5,
  tiRef: "pair",
  requireStacking: false,
  stackRatio: 1.5,
};

export function dtQuery(params) {
  return {
    ratio: params.ratio,
    ti_ref: params.tiRef,
    require_stacking: params.requireStacking,
    stack_ratio: params.stackRatio,
  };
}

// The inverse of dtQuery — mirrors paramsFromSearchParams above, so a Viewer
// deep link can reproduce the exact ratio/ti_ref that flagged an event
// (otherwise the event might not reappear in the Viewer's own fresh scan).
// Returns null if the URL carries no formula info.
export function dtParamsFromSearchParams(sp) {
  if (!sp.has("ratio")) return null;
  return {
    ratio: Number(sp.get("ratio")) || DEFAULT_DT_PARAMS.ratio,
    tiRef: sp.get("ti_ref") || DEFAULT_DT_PARAMS.tiRef,
    requireStacking: sp.get("require_stacking") === "true",
    stackRatio: Number(sp.get("stack_ratio") ?? DEFAULT_DT_PARAMS.stackRatio),
  };
}

// Defaults for the ineffective-effort formula (concordant flow-bump +
// pressure-dip) — same sharing pattern as the double-trigger params above.
export const DEFAULT_IE_PARAMS = {
  flowProminence: 25,
  flowProminenceMax: 60,
  pressureProminence: 1.5,
  concurrentTol: 0.3,
  bumpLookback: 0.4,
};

export function ieQuery(params) {
  return {
    flow_prominence: params.flowProminence,
    flow_prominence_max: params.flowProminenceMax,
    pressure_prominence: params.pressureProminence,
    concurrent_tol_sec: params.concurrentTol,
    bump_lookback_sec: params.bumpLookback,
  };
}

export function ieParamsFromSearchParams(sp) {
  if (!sp.has("flow_prominence")) return null;
  return {
    flowProminence: Number(sp.get("flow_prominence")) || DEFAULT_IE_PARAMS.flowProminence,
    flowProminenceMax: Number(sp.get("flow_prominence_max")) || DEFAULT_IE_PARAMS.flowProminenceMax,
    pressureProminence: Number(sp.get("pressure_prominence") ?? DEFAULT_IE_PARAMS.pressureProminence),
    concurrentTol: Number(sp.get("concurrent_tol_sec") ?? DEFAULT_IE_PARAMS.concurrentTol),
    bumpLookback: Number(sp.get("bump_lookback_sec") ?? DEFAULT_IE_PARAMS.bumpLookback),
  };
}

// Defaults for the auto-PEEP (air trapping) formula — see auto-peep.md.
export const DEFAULT_AP_PARAMS = {
  flowFrac: 0.15,
  flowAbs: 2.0,
  peepMin: 1.0,
  requirePressure: true,
};

export function apQuery(params) {
  return {
    flow_frac: params.flowFrac,
    flow_abs: params.flowAbs,
    peep_min: params.peepMin,
    require_pressure: params.requirePressure,
  };
}

export function apParamsFromSearchParams(sp) {
  if (!sp.has("flow_frac")) return null;
  return {
    flowFrac: Number(sp.get("flow_frac")) || DEFAULT_AP_PARAMS.flowFrac,
    flowAbs: Number(sp.get("flow_abs") ?? DEFAULT_AP_PARAMS.flowAbs),
    peepMin: Number(sp.get("peep_min") ?? DEFAULT_AP_PARAMS.peepMin),
    requirePressure: sp.get("require_pressure") !== "false",
  };
}

// Defaults for the flow-starvation formula (rise-dip-rise notch in
// inspiratory pressure) — see backend/flow_starvation.py.
export const DEFAULT_FS_PARAMS = {
  dipProminence: 2.0,
  lookback: 0.4,
  requireConstantFlow: false,
  flowRangeMax: 20.0,
};

export function fsQuery(params) {
  return {
    dip_prominence: params.dipProminence,
    lookback_sec: params.lookback,
    require_constant_flow: params.requireConstantFlow,
    flow_range_max: params.flowRangeMax,
  };
}

export function fsParamsFromSearchParams(sp) {
  if (!sp.has("dip_prominence")) return null;
  return {
    dipProminence: Number(sp.get("dip_prominence")) || DEFAULT_FS_PARAMS.dipProminence,
    lookback: Number(sp.get("lookback_sec") ?? DEFAULT_FS_PARAMS.lookback),
    requireConstantFlow: sp.get("require_constant_flow") === "true",
    flowRangeMax: Number(sp.get("flow_range_max") ?? DEFAULT_FS_PARAMS.flowRangeMax),
  };
}
