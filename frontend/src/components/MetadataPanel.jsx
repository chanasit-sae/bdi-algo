// Patient + capture metadata for the currently selected capture. MP/AI are
// fetched separately from (and slower than) the waveform, so `mpLoading`/
// `aiLoading` distinguish "still computing" from "computed, nothing to show".
// AI% is the headline number here (big, accent-colored) -- it's the one
// figure meant to be readable at a glance -- with MP shown next to it,
// smaller, as supporting context rather than an equal peer.
export default function MetadataPanel({ patient, capture, asynchronyIndex, aiLoading, mpStatus, mpLoading }) {
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
  const aiPct = asynchronyIndex != null ? asynchronyIndex * 100 : null;
  const aiColor = aiPct != null && aiPct > 10 ? "var(--alert)" : "var(--accent)";

  return (
    <>
      <div style={{ display: "flex", alignItems: "baseline", gap: 20, marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 36, fontWeight: 700, lineHeight: 1, color: aiLoading ? "var(--muted)" : aiColor }}>
            {aiLoading ? "…" : aiPct != null ? `${aiPct.toFixed(1)}%` : "—"}
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5, marginTop: 2 }}>
            Asynchrony index
          </div>
        </div>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600, lineHeight: 1 }}>
            {mpLoading ? "…" : mpStatus ? mpStatus.avg_mp_j_per_min.toFixed(1) : "—"}
            {!mpLoading && mpStatus && (
              <span style={{ fontSize: 11, fontWeight: 400, color: "var(--muted)" }}> J/min</span>
            )}
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5, marginTop: 2 }}>
            Mech. power
          </div>
        </div>
      </div>
      <dl className="kv">
        {rows.map(([k, v]) => (
          <FragmentRow key={k} k={k} v={v} />
        ))}
      </dl>
    </>
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
