// Patient + capture metadata for the currently selected capture.
export default function MetadataPanel({ patient, capture }) {
  if (!patient || !capture) return null;
  const rows = [
    ["Patient", patient.patient_id],
    ["Sex / Age", `${patient.sex || "?"} · ${patient.age ?? "?"} yr`],
    ["BW / HT", `${patient.bw_kg ?? "—"} kg / ${patient.ht_cm ?? "—"} cm`],
    ["BMI", patient.bmi ?? "—"],
    ["Ventilator", patient.ven ?? "—"],
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
