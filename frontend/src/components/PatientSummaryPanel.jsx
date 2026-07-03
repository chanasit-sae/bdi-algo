// Compact per-patient table: rolling mechanical power (J/min) and
// asynchrony index (%) for every patient, side by side, so a high-level scan
// across patients doesn't require clicking into each one individually. Rows
// render as soon as the patient list is known; each cell shows "loading…"
// until that specific patient's own MP/AI fetch resolves, rather than the
// whole table waiting on the slowest patient.
export default function PatientSummaryPanel({ rows, selectedId }) {
  if (!rows.length) {
    return <p className="muted" style={{ fontSize: 13 }}>no patients</p>;
  }
  return (
    <table className="patient-summary" style={{ width: "100%", fontSize: 12 }}>
      <thead>
        <tr>
          <th style={{ textAlign: "left" }}>Patient</th>
          <th style={{ textAlign: "right" }}>MP (J/min)</th>
          <th style={{ textAlign: "right" }}>AI %</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.patient_id} style={r.patient_id === selectedId ? { fontWeight: "bold" } : undefined}>
            <td>{r.patient_id.slice(0, 8)}…</td>
            <td style={{ textAlign: "right" }}>{r.loading ? "loading…" : r.mp != null ? r.mp.toFixed(1) : "—"}</td>
            <td style={{ textAlign: "right" }}>{r.loading ? "loading…" : r.ai != null ? (r.ai * 100).toFixed(1) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
