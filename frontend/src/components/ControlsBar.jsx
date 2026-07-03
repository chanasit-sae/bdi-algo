import NumberField from "./NumberField.jsx";

// Segmentation controls. `params` is the current settings object and `set`
// patches one key. The greying-out rules mirror the original syncBaselineUI.
export default function ControlsBar({ params, set }) {
  const p = params;
  const slopeMode = p.baselineMode === "slope";
  const manual = p.baselineMode === "manual";

  return (
    <div className="controls">
      <div className="field">
        <label title="crossing baseline: zero, auto = per-capture low-percentile offset, manual = the offset field, slope = adaptive slope-change onset detection (level-agnostic)">
          Baseline
        </label>
        <select value={p.baselineMode} onChange={(e) => set("baselineMode", e.target.value)}>
          <option value="zero">zero</option>
          <option value="auto">auto</option>
          <option value="manual">manual</option>
          <option value="slope">slope</option>
        </select>
      </div>

      <NumberField
        label="Offset"
        title="manual crossing-baseline offset (L/min); used when Baseline = manual"
        value={p.baseoff}
        step="1"
        disabled={!manual}
        onChange={(v) => set("baseoff", v)}
      />
      <NumberField
        label="Hysteresis"
        title="dead-band around baseline (L/min) to reject noise crossings"
        value={p.hyst}
        min="0"
        step="1"
        disabled={slopeMode}
        onChange={(v) => set("hyst", v)}
      />
      <NumberField
        label="Slope"
        title="min flow rise rate (L/min per second) at inspiration onset; both this and hysteresis must be met to mark a breath. ~30 recommended"
        value={p.slope}
        min="0"
        step="1"
        disabled={slopeMode}
        onChange={(v) => set("slope", v)}
      />
      <NumberField
        label="Δslope"
        title="Baseline=slope: slope jump (L/min per second) above the recent trend that flags a breath start"
        value={p.sdelta}
        min="0"
        step="5"
        disabled={!slopeMode}
        onChange={(v) => set("sdelta", v)}
      />
      <NumberField
        label="Win s"
        title="Baseline=slope: trailing trend window in seconds"
        value={p.swin}
        min="0.04"
        step="0.04"
        disabled={!slopeMode}
        onChange={(v) => set("swin", v)}
      />
      <NumberField
        label="Refr s"
        title="Baseline=slope: min spacing between onsets in seconds; suppresses the expiratory-recovery double-fire"
        value={p.srefr}
        min="0"
        step="0.1"
        disabled={!slopeMode}
        onChange={(v) => set("srefr", v)}
      />
      <NumberField
        label="ExpGuard"
        title="Baseline=slope: drop onsets preceded by a steep flow DECREASE (expiratory limb); pre-onset slope below this magnitude (L/min per second) is rejected. 0 = off"
        value={p.sguard}
        min="0"
        step="10"
        disabled={!slopeMode}
        onChange={(v) => set("sguard", v)}
      />
      <NumberField
        label="PeakMin"
        title="Baseline=slope: min peak inspiratory flow (L/min) the rise must reach for an onset to count; ~60-90 for a normal adult. 0 = off. Tick 'avg' to use the whole-capture average flow as the threshold instead."
        value={p.speak}
        min="0"
        step="5"
        disabled={!slopeMode || p.speakMean}
        onChange={(v) => set("speak", v)}
      />
      <div className="field">
        <label
          style={{ fontWeight: 400 }}
          title="use the whole-capture average flow as the PeakMin threshold"
        >
          <input
            type="checkbox"
            checked={p.speakMean}
            disabled={!slopeMode}
            onChange={(e) => set("speakMean", e.target.checked)}
            style={{ verticalAlign: "middle" }}
          />{" "}
          avg
        </label>
      </div>

      <div className="field">
        <label title="also list flat captures where the ventilator is not connected to a patient">
          Show disconnected
        </label>
        <input
          type="checkbox"
          checked={p.showDisc}
          onChange={(e) => set("showDisc", e.target.checked)}
        />
      </div>
    </div>
  );
}
