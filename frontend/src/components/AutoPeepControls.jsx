import NumberField from "./NumberField.jsx";

// Knobs for the auto-PEEP (air trapping) formula: a breath's end-expiratory
// flow/pressure failing to return to reference levels. See auto-peep.md.
export default function AutoPeepControls({ params, set }) {
  return (
    <div className="controls">
      <NumberField
        label="Flow frac"
        title="min fraction of expiratory flow still present at end-expiration to count as trapped"
        value={params.flowFrac}
        min="0"
        max="1"
        step="0.01"
        onChange={(v) => set("flowFrac", v)}
      />
      <NumberField
        label="Flow abs"
        title="min absolute residual end-expiratory flow (L/min) — a noise floor so a large fraction on a low-flow breath doesn't trigger alone"
        value={params.flowAbs}
        min="0"
        step="0.5"
        onChange={(v) => set("flowAbs", v)}
      />
      <NumberField
        label="PEEP min"
        title="min end-expiratory pressure excess over the capture's set PEEP (cmH2O)"
        value={params.peepMin}
        min="0"
        step="0.1"
        onChange={(v) => set("peepMin", v)}
      />
      <div className="field">
        <label
          style={{ fontWeight: 400 }}
          title="require both the flow and pressure signature (the mix); unchecked flags on flow alone (peep_delta is still reported for review)"
        >
          <input
            type="checkbox"
            checked={params.requirePressure}
            onChange={(e) => set("requirePressure", e.target.checked)}
            style={{ verticalAlign: "middle" }}
          />{" "}
          Require pressure
        </label>
      </div>
    </div>
  );
}
