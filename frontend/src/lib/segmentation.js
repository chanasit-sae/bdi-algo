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
