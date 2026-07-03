// Patient + capture metadata for the currently selected capture. MP/AI are
// fetched separately from (and slower than) the waveform, so `mpLoading`/
// `aiLoading` distinguish "still computing" from "computed, nothing to show".
export default function MetadataPanel({ patient, capture, asynchronyIndex, aiLoading, mpStatus, mpLoading }) {
  if (!patient || !capture) return null;
  const rows = [
    ["Patient", patient.patient_id],
    ["Sex / Age", `${patient.sex || "?"} · ${patient.age ?? "?"} yr`],
    ["BW / HT", `${patient.bw_kg ?? "—"} kg / ${patient.ht_cm ?? "—"} cm`],
    ["BMI", patient.bmi ?? "—"],
    ["Ventilator", patient.ven ?? "—"],
    ["Mechanical power", mpLoading ? "loading…" : mpStatus ? `${mpStatus.avg_mp_j_per_min.toFixed(1)} J/min` : "—"],
    ["Asynchrony index", aiLoading ? "loading…" : asynchronyIndex != null ? `${(asynchronyIndex * 100).toFixed(1)}%` : "—"],
    ["ICU day", capture.day ?? "—"],
    ["Time", capture.time ?? "—"],
    ["PDx", capture.pdx || "—"],
    ["SDx", capture.sdx || "—"],
    ["Operation", capture.operation || "—"],
    ["File", capture.raw_data],
  ];
  return (
    <dl className="kv">
      {rows.map(([k, v]) => (
        <FragmentRow key={k} k={k} v={v} />
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
