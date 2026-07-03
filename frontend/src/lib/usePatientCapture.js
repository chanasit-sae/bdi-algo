import { useEffect, useMemo, useState } from "react";

export const visibleCaps = (p, showDisc) =>
  showDisc ? p.captures : p.captures.filter((c) => c.connected);

// Shared "pick a patient, then a capture" selection state, plus the effects
// that keep the selection valid as `patients` loads or the disconnected
// filter flips. Used by every page that needs a capture picker.
export function usePatientCapture(patients, showDisc) {
  const [patientId, setPatientId] = useState(null);
  const [file, setFile] = useState(null);

  const visiblePatients = useMemo(
    () => (patients ? patients.filter((p) => visibleCaps(p, showDisc).length) : []),
    [patients, showDisc]
  );

  useEffect(() => {
    if (!visiblePatients.length) return;
    if (!visiblePatients.some((p) => p.patient_id === patientId)) {
      setPatientId(visiblePatients[0].patient_id);
    }
  }, [visiblePatients, patientId]);

  const patient = useMemo(
    () => visiblePatients.find((p) => p.patient_id === patientId) || null,
    [visiblePatients, patientId]
  );
  const caps = patient ? visibleCaps(patient, showDisc) : [];

  // keep a valid capture selected (also when Show-disconnected hides the current one)
  useEffect(() => {
    if (!patient) return;
    if (!caps.some((c) => c.raw_data === file)) {
      setFile(caps.length ? caps[0].raw_data : null);
    }
  }, [patient, showDisc]); // eslint-disable-line react-hooks/exhaustive-deps

  const capture = caps.find((c) => c.raw_data === file) || null;

  return { visiblePatients, patientId, setPatientId, patient, caps, file, setFile, capture };
}
