import { visibleCaps } from "../lib/usePatientCapture.js";

// Patient + Capture dropdowns, bound to the state from usePatientCapture().
export default function CaptureSelect({ visiblePatients, patientId, setPatientId, caps, file, setFile, showDisc }) {
  return (
    <>
      <div className="field">
        <label>Patient</label>
        <select value={patientId || ""} onChange={(e) => setPatientId(e.target.value)}>
          {visiblePatients.map((p) => (
            <option key={p.patient_id} value={p.patient_id}>
              {p.patient_id.slice(0, 8)}… ({visibleCaps(p, showDisc).length} cap)
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>Capture</label>
        <select value={file || ""} onChange={(e) => setFile(e.target.value)}>
          {caps.map((c) => (
            <option key={c.raw_data} value={c.raw_data}>
              day {c.day} · {c.time}
              {c.connected ? "" : " · disconnected"}
            </option>
          ))}
        </select>
      </div>
    </>
  );
}
