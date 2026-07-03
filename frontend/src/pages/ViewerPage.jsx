import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { COLORS } from "../lib/charts.js";
import { usePatientCapture } from "../lib/usePatientCapture.js";
import {
  DEFAULT_SEGMENTATION_PARAMS,
  segmentationQuery,
  paramsFromSearchParams,
  DEFAULT_ASYNCHRONY_PARAMS,
  asynchronyQuery,
  asynchronyParamsFromSearchParams,
} from "../lib/segmentation.js";
import CaptureSelect from "../components/CaptureSelect.jsx";
import ControlsBar from "../components/ControlsBar.jsx";
import DoubleTriggerControls from "../components/DoubleTriggerControls.jsx";
import WaveformChart from "../components/WaveformChart.jsx";
import MetadataPanel from "../components/MetadataPanel.jsx";
import BreathPanel from "../components/BreathPanel.jsx";
import AsynchronyPanel from "../components/AsynchronyPanel.jsx";

const DEFAULT_PARAMS = { ...DEFAULT_SEGMENTATION_PARAMS, ...DEFAULT_ASYNCHRONY_PARAMS };

export default function ViewerPage() {
  const [searchParams] = useSearchParams();
  const [patients, setPatients] = useState(null);
  const [params, setParams] = useState(() => ({
    ...(paramsFromSearchParams(searchParams) || DEFAULT_SEGMENTATION_PARAMS),
    ...(asynchronyParamsFromSearchParams(searchParams) || DEFAULT_ASYNCHRONY_PARAMS),
  }));
  const [breathIdx, setBreathIdx] = useState(-1);
  const [wf, setWf] = useState(null);
  const [breaths, setBreaths] = useState([]);
  const [baselineVal, setBaselineVal] = useState(null);
  const [asyncEvents, setAsyncEvents] = useState([]);
  const [activeEventIdx, setActiveEventIdx] = useState(-1);
  const [status, setStatus] = useState("");

  const appliedUrlCapture = useRef(false);
  const appliedUrlBreath = useRef(false);
  const appliedUrlEvent = useRef(false);

  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    api
      .index()
      .then((d) => setPatients(d.patients))
      .catch((e) => setStatus("error: " + e.message));
  }, []);

  const { visiblePatients, patientId, setPatientId, patient, caps, file, setFile, capture } =
    usePatientCapture(patients, params.showDisc);

  // deep link: once patients load, jump straight to the notification's capture
  useEffect(() => {
    if (appliedUrlCapture.current) return;
    const targetFile = searchParams.get("file");
    if (!patients || !targetFile) return;
    const owner = patients.find((p) => p.captures.some((c) => c.raw_data === targetFile));
    if (owner) {
      setPatientId(owner.patient_id);
      setFile(targetFile);
    }
    appliedUrlCapture.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patients]);

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
  const breathsOpts = useMemo(() => segmentationQuery(params), [params]);

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

  // deep link: once this capture's breaths are in, select the flagged one
  useEffect(() => {
    if (appliedUrlBreath.current) return;
    const targetBreath = searchParams.get("breath");
    if (targetBreath == null || !breaths.length) return;
    const idx = breaths.findIndex((b) => String(b.breath_idx) === targetBreath);
    if (idx >= 0) setBreathIdx(idx);
    appliedUrlBreath.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [breaths]);

  // --- fetch every asynchrony event for this capture (all of it, not just one) ---
  const asyncOpts = useMemo(() => asynchronyQuery(params), [params]);

  useEffect(() => {
    if (!file) {
      setAsyncEvents([]);
      setActiveEventIdx(-1);
      return;
    }
    let cancelled = false;
    api
      .doubleTriggers(file, { ...breathsOpts, ...asyncOpts })
      .then((d) => {
        if (cancelled) return;
        setAsyncEvents(d.events);
        setActiveEventIdx(-1);
      })
      .catch((e) => !cancelled && setStatus("error: " + e.message));
    return () => {
      cancelled = true;
    };
  }, [file, breathsOpts, asyncOpts]);

  // deep link: once this capture's events are in, mark the flagged one active
  useEffect(() => {
    if (appliedUrlEvent.current) return;
    const targetBreath = searchParams.get("breath");
    if (targetBreath == null || !asyncEvents.length) return;
    const idx = asyncEvents.findIndex((e) => String(e.breath_idx_a) === targetBreath);
    if (idx >= 0) setActiveEventIdx(idx);
    appliedUrlEvent.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asyncEvents]);

  // status line once the waveform is in
  useEffect(() => {
    if (!wf) return;
    const n = wf.t_sec.length;
    const dur = wf.t_sec[n - 1] || 0;
    setStatus(
      `${n} samples · ${dur.toFixed(1)}s @ 25Hz · ${breaths.length} breaths · ${asyncEvents.length} asynchrony flagged`
    );
  }, [wf, breaths, asyncEvents]);

  // clicking an asynchrony event makes its band active AND selects its breath
  function selectEvent(i) {
    setActiveEventIdx(i);
    const ev = asyncEvents[i];
    if (!ev) return;
    const idx = breaths.findIndex((b) => b.breath_idx === ev.breath_idx_a);
    if (idx >= 0) setBreathIdx(idx);
  }

  const highlights = useMemo(
    () =>
      asyncEvents.map((e, i) => ({
        t0: e.t_insp_start_a,
        t1: e.t_exp_end_b,
        active: i === activeEventIdx,
      })),
    [asyncEvents, activeEventIdx]
  );

  const sel = breathIdx >= 0 ? breaths[breathIdx] : null;
  const slopeRef =
    params.baselineMode === "slope"
      ? Number(params.sdelta) || 0
      : Number(params.slope) || 0;

  return (
    <>
      <div className="controls">
        <CaptureSelect
          visiblePatients={visiblePatients}
          patientId={patientId}
          setPatientId={setPatientId}
          caps={caps}
          file={file}
          setFile={setFile}
          showDisc={params.showDisc}
        />
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
      <DoubleTriggerControls params={params} set={set} />

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
            highlights={highlights}
          />
          <WaveformChart
            title="Pressure (cmH2O)"
            color={COLORS.pressure}
            t={wf?.t_sec}
            y={wf?.pressure}
            breaths={breaths}
            sel={sel}
            highlights={highlights}
          />
          <WaveformChart
            title="Volume (mL)"
            color={COLORS.volume}
            t={wf?.t_sec}
            y={wf?.volume}
            breaths={breaths}
            sel={sel}
            highlights={highlights}
          />
          <WaveformChart
            title="Flow slope (L/min/s)"
            color={COLORS.slope}
            t={wf?.t_sec}
            y={wf?.slope}
            breaths={breaths}
            sel={sel}
            baseVal={slopeRef || null}
            highlights={highlights}
          />
        </div>
        <aside>
          <h2>Metadata</h2>
          <MetadataPanel patient={patient} capture={capture} />
          <h2 style={{ marginTop: 16 }}>Asynchrony</h2>
          <AsynchronyPanel events={asyncEvents} activeIdx={activeEventIdx} onSelect={selectEvent} />
          <h2 style={{ marginTop: 16 }}>Breath</h2>
          <BreathPanel breath={sel} />
        </aside>
      </main>
    </>
  );
}
