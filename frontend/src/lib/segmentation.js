// Shared segmentation-parameter defaults + the params-state -> API-query
// mapping, used by every page that runs breath segmentation (ViewerPage,
// DoubleTriggerPage, ...).

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
