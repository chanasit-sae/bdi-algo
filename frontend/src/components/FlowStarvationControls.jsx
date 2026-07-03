import NumberField from "./NumberField.jsx";

// Knobs for the flow-starvation formula: a rise-dip-rise "scoop" notch in
// the inspiratory pressure trace (constant-flow delivery not meeting patient
// demand).
export default function FlowStarvationControls({ params, set }) {
  return (
    <div className="controls">
      <NumberField
        label="Dip prom."
        title="min rise-before AND rise-after (cmH2O) around a candidate inspiratory pressure notch, measured within Lookback of the dip"
        value={params.dipProminence}
        min="0"
        step="0.1"
        onChange={(v) => set("dipProminence", v)}
      />
      <NumberField
        label="Lookback"
        title="how far back/forward (s) the notch's prominence is measured — bounds it to a local reference instead of the whole inspiratory window"
        value={params.lookback}
        min="0.1"
        step="0.1"
        onChange={(v) => set("lookback", v)}
      />
      <div className="field">
        <label
          style={{ fontWeight: 400 }}
          title="also require the inspiratory flow trace to stay flat (volume-control-like); off by default"
        >
          <input
            type="checkbox"
            checked={params.requireConstantFlow}
            onChange={(e) => set("requireConstantFlow", e.target.checked)}
            style={{ verticalAlign: "middle" }}
          />{" "}
          Require constant flow
        </label>
      </div>
      <NumberField
        label="Flow range max"
        title="max inspiratory flow range (L/min) allowed when 'Require constant flow' is on"
        value={params.flowRangeMax}
        min="0"
        step="1"
        disabled={!params.requireConstantFlow}
        onChange={(v) => set("flowRangeMax", v)}
      />
    </div>
  );
}
