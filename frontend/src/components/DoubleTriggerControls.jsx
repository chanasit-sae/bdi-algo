import NumberField from "./NumberField.jsx";

// Knobs for the double-triggering formula itself (separate from the breath
// segmentation controls, which come from the shared ControlsBar).
export default function DoubleTriggerControls({ params, set }) {
  return (
    <div className="controls">
      <NumberField
        label="Ratio"
        title="Te/Ti_ref cutoff: a breath pair is flagged when the expiratory gap is less than this fraction of Ti_ref. Thille et al. 2006 default is 0.5 (half the inspiratory time)."
        value={params.ratio}
        min="0.05"
        max="1"
        step="0.05"
        onChange={(v) => set("ratio", v)}
      />
      <div className="field">
        <label title='What Ti_ref means: "pair" = mean Ti of this breath pair (default), "capture" = mean Ti over the whole capture&#39;s complete breaths, "self" = this breath&#39;s own Ti alone.'>
          Ti ref
        </label>
        <select value={params.tiRef} onChange={(e) => set("tiRef", e.target.value)}>
          <option value="pair">pair</option>
          <option value="capture">capture</option>
          <option value="self">self</option>
        </select>
      </div>
      <div className="field">
        <label
          style={{ fontWeight: 400 }}
          title="also require the pair's combined tidal volume to exceed stack_ratio x 2x the capture's median Vt (the breath-stacking / volutrauma signature)"
        >
          <input
            type="checkbox"
            checked={params.requireStacking}
            onChange={(e) => set("requireStacking", e.target.checked)}
            style={{ verticalAlign: "middle" }}
          />{" "}
          Require volume stacking
        </label>
      </div>
      <NumberField
        label="Stack ratio"
        title="combined-Vt threshold, as a multiple of 2x the capture's median Vt; only applied when 'Require volume stacking' is on"
        value={params.stackRatio}
        min="1"
        step="0.1"
        disabled={!params.requireStacking}
        onChange={(v) => set("stackRatio", v)}
      />
    </div>
  );
}
