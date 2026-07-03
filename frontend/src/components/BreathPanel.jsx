import { COLORS } from "../lib/charts.js";

const f = (v, d = 2) => (v == null ? "—" : (+v).toFixed(d));

// Derived metrics for the selected breath, or a hint when none is selected.
export default function BreathPanel({ breath: b }) {
  if (!b) return <dl className="kv"><dd className="muted">select a breath</dd></dl>;

  const swatch = (c) => <span className="swatch" style={{ background: c }} />;
  const rows = [
    ["Index", b.breath_idx + (b.is_complete ? "" : " (partial)")],
    [<>{swatch(COLORS.flow)}Inspiration</>, `${f(b.ti_sec)} s`],
    [<>{swatch(COLORS.pressure)}Expiration</>, `${f(b.te_sec)} s`],
    ["I:E", b.ie_ratio == null ? "—" : `1 : ${f(1 / b.ie_ratio)}`],
    ["Cycle time", `${f(b.cycle_time_sec)} s`],
    ["Duty (Ti/Ttot)", f(b.duty_cycle)],
    ["Rate", `${f(b.rr_bpm, 1)} /min`],
    ["Tidal vol", `${f(b.tidal_volume_ml, 1)} mL`],
    ["Vt insp / exp", `${f(b.vti_ml, 0)} / ${f(b.vte_ml, 0)} mL`],
    ["Leak", `${f(b.leak_ml, 0)} mL`],
    ["Peak flow insp", `${f(b.peak_insp_flow, 1)} L/min`],
    ["Peak flow exp", `${f(b.peak_exp_flow, 1)} L/min`],
    ["Mean insp flow", `${f(b.mean_insp_flow, 1)} L/min`],
    ["Time to peak", `${f(b.time_to_peak_flow_sec)} s`],
    ["End-exp flow", `${f(b.end_exp_flow, 1)} L/min`],
    ["Flow shape", f(b.flow_shape_ratio)],
    ["PIP", `${f(b.pip_cmh2o, 1)} cmH₂O`],
    ["Plateau", `${f(b.plateau_pressure_cmh2o, 1)} cmH₂O`],
    ["Mean press", `${f(b.mean_pressure, 1)} cmH₂O`],
    ["PEEP", `${f(b.peep, 1)} cmH₂O`],
    ["Driving press", `${f(b.driving_pressure_cmh2o, 1)} cmH₂O`],
    ["Compliance (stat)", `${f(b.static_compliance_ml_cmh2o, 1)} mL/cmH₂O`],
    ["Compliance (dyn)", `${f(b.dynamic_compliance_ml_cmh2o, 1)} mL/cmH₂O`],
    ["Resistance", `${f(b.resistance_cmh2o_l_s, 1)} cmH₂O/(L/s)`],
  ];
  return (
    <dl className="kv">
      {rows.map(([k, v], i) => (
        <FragmentRow key={i} k={k} v={v} />
      ))}
    </dl>
  );
}

function FragmentRow({ k, v }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{v}</dd>
    </>
  );
}
