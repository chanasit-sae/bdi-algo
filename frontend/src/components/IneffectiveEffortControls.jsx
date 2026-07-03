import NumberField from "./NumberField.jsx";

// Knobs for the ineffective-effort formula: a concordant flow-bump +
// pressure-dip within a short time window, both sub-threshold (never
// clearing the real trigger).
export default function IneffectiveEffortControls({ params, set }) {
  return (
    <div className="controls">
      <NumberField
        label="Flow bump"
        title="min flow-bump rise (L/min), measured within Lookback of the peak, to count as an effort"
        value={params.flowProminence}
        min="0"
        step="1"
        onChange={(v) => set("flowProminence", v)}
      />
      <NumberField
        label="Flow bump max"
        title="bumps at or above this (L/min) are treated as a real breath segmentation missed, not a failed effort, and are excluded"
        value={params.flowProminenceMax}
        min="0"
        step="5"
        onChange={(v) => set("flowProminenceMax", v)}
      />
      <NumberField
        label="Pressure dip"
        title="min pressure-dip depth (cmH2O), measured within Lookback of the trough, to count as an effort"
        value={params.pressureProminence}
        min="0"
        step="0.1"
        onChange={(v) => set("pressureProminence", v)}
      />
      <NumberField
        label="Concur. tol"
        title="max time gap (s) between the flow bump and the pressure dip for them to count as the same effort"
        value={params.concurrentTol}
        min="0.02"
        step="0.05"
        onChange={(v) => set("concurrentTol", v)}
      />
      <NumberField
        label="Lookback"
        title="how far back (s) prominence is measured from each candidate peak/trough — bounds it to a local reference instead of the whole expiratory window, which is what keeps ordinary decay-curve noise from being miscounted as a bump/dip"
        value={params.bumpLookback}
        min="0.1"
        step="0.1"
        onChange={(v) => set("bumpLookback", v)}
      />
    </div>
  );
}
