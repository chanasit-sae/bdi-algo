import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api.js";
import { COLORS } from "../lib/charts.js";
import ControlsBar from "../components/ControlsBar.jsx";
import WaveformChart from "../components/WaveformChart.jsx";
import MetadataPanel from "../components/MetadataPanel.jsx";
import BreathPanel from "../components/BreathPanel.jsx";

const DEFAULT_PARAMS = {
  baselineMode: "slope",
  baseoff: 0,
  hyst: 0,
  slope: 30,
  sdelta: 100,
  swin: 0.32,
  srefr: 1.0,
  sguard: 100,
  speak: 60,
  speakMean: true,
  showDisc: false,
};

const visibleCaps = (p, showDisc) =>
  showDisc ? p.captures : p.captures.filter((c) => c.connected);

export default function ViewerPage() {
  const [patients, setPatients] = useState(null);
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [patientId, setPatientId] = useState(null);
  const [file, setFile] = useState(null);
  const [breathIdx, setBreathIdx] = useState(-1);
  const [wf, setWf] = useState(null);
  const [breaths, setBreaths] = useState([]);
  const [baselineVal, setBaselineVal] = useState(null);
  const [status, setStatus] = useState("");

  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  // --- load the patient/capture index once ---
  useEffect(() => {
    api
      .index()
      .then((d) => setPatients(d.patients))
      .catch((e) => setStatus("error: " + e.message));
  }, []);

  const visiblePatients = useMemo(
    () => (patients ? patients.filter((p) => visibleCaps(p, params.showDisc).length) : []),
    [patients, params.showDisc]
  );

  // keep a valid patient selected
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
  const caps = patient ? visibleCaps(patient, params.showDisc) : [];

  // keep a valid capture selected (also when Show-disconnected hides the current one)
  useEffect(() => {
    if (!patient) return;
    if (!caps.some((c) => c.raw_data === file)) {
      setFile(caps.length ? caps[0].raw_data : null);
    }
  }, [patient, params.showDisc]); // eslint-disable-line react-hooks/exhaustive-deps

  const capture = caps.find((c) => c.raw_data === file) || null;

  // --- fetch the raw waveform when the capture changes ---
  useEffect(() => {
    if (!file) {
      setWf(null);
      return;
    }
    let cancelled = false;
    setStatus("loading " + file + " …");
    api
      .waveform(file)
      .then((d) => !cancelled && setWf(d))
      .catch((e) => !cancelled && setStatus("error: " + e.message));
    return () => {
      cancelled = true;
    };
  }, [file]);

  // --- fetch breaths when the capture or any segmentation param changes ---
  const breathsOpts = useMemo(
    () => ({
      baseline:
        params.baselineMode === "manual"
          ? String(Number(params.baseoff) || 0)
          : params.baselineMode,
      hysteresis: params.hyst,
      slope: params.slope,
      sdelta: params.sdelta,
      swin: params.swin,
      srefr: params.srefr,
      sguard: params.sguard,
      speak: params.speakMean ? "mean" : String(Number(params.speak) || 0),
    }),
    [
      params.baselineMode,
      params.baseoff,
      params.hyst,
      params.slope,
      params.sdelta,
      params.swin,
      params.srefr,
      params.sguard,
      params.speak,
      params.speakMean,
    ]
  );

  useEffect(() => {
    if (!file) {
      setBreaths([]);
      setBaselineVal(null);
      return;
    }
    let cancelled = false;
    api
      .breaths(file, breathsOpts)
      .then((d) => {
        if (cancelled) return;
        setBreaths(d.breaths);
        setBaselineVal(d.baseline);
        setBreathIdx(-1);
      })
      .catch((e) => !cancelled && setStatus("error: " + e.message));
    return () => {
      cancelled = true;
    };
  }, [file, breathsOpts]);

  // status line once the waveform is in
  useEffect(() => {
    if (!wf) return;
    const n = wf.t_sec.length;
    const dur = wf.t_sec[n - 1] || 0;
    setStatus(`${n} samples · ${dur.toFixed(1)}s @ 25Hz · ${breaths.length} breaths`);
  }, [wf, breaths]);

  const sel = breathIdx >= 0 ? breaths[breathIdx] : null;
  const slopeRef =
    params.baselineMode === "slope"
      ? Number(params.sdelta) || 0
      : Number(params.slope) || 0;

  return (
    <>
      <div className="controls">
        <div className="field">
          <label>Patient</label>
          <select value={patientId || ""} onChange={(e) => setPatientId(e.target.value)}>
            {visiblePatients.map((p) => (
              <option key={p.patient_id} value={p.patient_id}>
                {p.patient_id.slice(0, 8)}… ({visibleCaps(p, params.showDisc).length} cap)
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
        <div className="field">
          <label>Breath</label>
          <select
            value={breathIdx}
            onChange={(e) => setBreathIdx(parseInt(e.target.value, 10))}
          >
            <option value={-1}>— whole capture —</option>
            {breaths.map((b, i) => (
              <option key={i} value={i}>
                breath {b.breath_idx} · {b.t_insp_start.toFixed(2)}–{b.t_exp_end.toFixed(2)}s
                {b.is_complete ? "" : " (partial)"}
              </option>
            ))}
          </select>
        </div>
        <span className="muted">{status}</span>
      </div>

      <ControlsBar params={params} set={set} />

      <main className="viewer">
        <div className="charts">
          <WaveformChart
            title="Flow (L/min)"
            color={COLORS.flow}
            t={wf?.t_sec}
            y={wf?.flow}
            breaths={breaths}
            sel={sel}
            baseVal={baselineVal}
          />
          <WaveformChart
            title="Pressure (cmH2O)"
            color={COLORS.pressure}
            t={wf?.t_sec}
            y={wf?.pressure}
            breaths={breaths}
            sel={sel}
          />
          <WaveformChart
            title="Volume (mL)"
            color={COLORS.volume}
            t={wf?.t_sec}
            y={wf?.volume}
            breaths={breaths}
            sel={sel}
          />
          <WaveformChart
            title="Flow slope (L/min/s)"
            color={COLORS.slope}
            t={wf?.t_sec}
            y={wf?.slope}
            breaths={breaths}
            sel={sel}
            baseVal={slopeRef || null}
          />
        </div>
        <aside>
          <h2>Metadata</h2>
          <MetadataPanel patient={patient} capture={capture} />
          <h2 style={{ marginTop: 16 }}>Breath</h2>
          <BreathPanel breath={sel} />
        </aside>
      </main>
    </>
  );
}
