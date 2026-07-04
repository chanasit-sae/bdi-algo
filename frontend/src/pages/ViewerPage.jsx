import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import { COLORS } from "../lib/charts.js";
import { usePatientCapture } from "../lib/usePatientCapture.js";
import {
  DEFAULT_SEGMENTATION_PARAMS,
  segmentationQuery,
  paramsFromSearchParams,
  DEFAULT_DT_PARAMS,
  dtQuery,
  dtParamsFromSearchParams,
  DEFAULT_IE_PARAMS,
  ieQuery,
  ieParamsFromSearchParams,
  DEFAULT_AP_PARAMS,
  apQuery,
  apParamsFromSearchParams,
  DEFAULT_FS_PARAMS,
  fsQuery,
  fsParamsFromSearchParams,
} from "../lib/segmentation.js";
import CaptureSelect from "../components/CaptureSelect.jsx";
import WaveformChart from "../components/WaveformChart.jsx";
import MetadataPanel from "../components/MetadataPanel.jsx";
import BreathPanel from "../components/BreathPanel.jsx";
import AsynchronyPanel from "../components/AsynchronyPanel.jsx";
import VitalsPanel from "../components/VitalsPanel.jsx";

export default function ViewerPage() {
  const [searchParams] = useSearchParams();
  const [patients, setPatients] = useState(null);
  const [params, setParams] = useState(() => ({
    ...(paramsFromSearchParams(searchParams) || DEFAULT_SEGMENTATION_PARAMS),
    ...(dtParamsFromSearchParams(searchParams) || DEFAULT_DT_PARAMS),
    ...(ieParamsFromSearchParams(searchParams) || DEFAULT_IE_PARAMS),
    ...(apParamsFromSearchParams(searchParams) || DEFAULT_AP_PARAMS),
    ...(fsParamsFromSearchParams(searchParams) || DEFAULT_FS_PARAMS),
  }));
  const [breathIdx, setBreathIdx] = useState(-1);
  const [wf, setWf] = useState(null);
  const [breaths, setBreaths] = useState([]);
  const [baselineVal, setBaselineVal] = useState(null);
  const [asyncEvents, setAsyncEvents] = useState([]);
  const [activeEventIdx, setActiveEventIdx] = useState(-1);
  const [asynchronyIndex, setAsynchronyIndex] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [mpStatus, setMpStatus] = useState(null);
  const [mpAboveThreshold, setMpAboveThreshold] = useState(false);
  const [mpLoading, setMpLoading] = useState(false);
  const [status, setStatus] = useState("");

  const appliedUrlCapture = useRef(false);
  const appliedUrlBreath = useRef(false);
  const appliedUrlEvent = useRef(false);

  useEffect(() => {
    api
      .index()
      .then((d) => setPatients(d.patients))
      .catch((e) => setStatus("error: " + e.message));
  }, []);

  const { visiblePatients, patientId, setPatientId, patient, caps, file, setFile, capture } =
    usePatientCapture(patients, params.showDisc);

  // Fetch the patient's asynchrony index and rolling mechanical power once
  // per patient selection, not on every capture switch. These are their own
  // effects, independent of the waveform fetch below, so a slow MP/AI
  // computation never holds up the waveform appearing -- each just shows
  // "loading…" (see MetadataPanel) until its own fetch resolves.
  useEffect(() => {
    if (!patientId) {
      setAsynchronyIndex(null);
      setMpStatus(null);
      setMpAboveThreshold(false);
      setAiLoading(false);
      setMpLoading(false);
      return;
    }
    let cancelled = false;
    setAiLoading(true);
    setMpLoading(true);
    api
      .asynchronyIndex(patientId)
      .then((d) => !cancelled && setAsynchronyIndex(d.asynchrony_index))
      .catch(() => !cancelled && setAsynchronyIndex(null))
      .finally(() => !cancelled && setAiLoading(false));
    api
      .mechanicalPower(patientId)
      .then((d) => {
        if (cancelled) return;
        setMpStatus(d.status);
        setMpAboveThreshold(!!d.above_threshold);
      })
      .catch(() => {
        if (cancelled) return;
        setMpStatus(null);
        setMpAboveThreshold(false);
      })
      .finally(() => !cancelled && setMpLoading(false));
    return () => {
      cancelled = true;
    };
  }, [patientId]);

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

  // --- fetch every asynchrony event for this capture, all detectors, all of it ---
  const dtOpts = useMemo(() => dtQuery(params), [params]);
  const ieOpts = useMemo(() => ieQuery(params), [params]);
  const apOpts = useMemo(() => apQuery(params), [params]);
  const fsOpts = useMemo(() => fsQuery(params), [params]);

  useEffect(() => {
    if (!file) {
      setAsyncEvents([]);
      setActiveEventIdx(-1);
      return;
    }
    let cancelled = false;
    api
      .asynchrony(file, { ...breathsOpts, ...dtOpts, ...ieOpts, ...apOpts, ...fsOpts })
      .then((d) => {
        if (cancelled) return;
        setAsyncEvents(d.events);
        setActiveEventIdx(-1);
      })
      .catch((e) => !cancelled && setStatus("error: " + e.message));
    return () => {
      cancelled = true;
    };
  }, [file, breathsOpts, dtOpts, ieOpts, apOpts, fsOpts]);

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

  // clicking a breath segment directly on any waveform chart selects it,
  // same as picking it from the Breath dropdown -- and clears any active
  // asynchrony highlight, since this is a plain manual pick, not a click
  // on a flagged event.
  function selectBreathAtTime(time) {
    const idx = breaths.findIndex((b) => time >= b.t_insp_start && time <= b.t_exp_end);
    if (idx < 0) return;
    setBreathIdx(idx);
    setActiveEventIdx(-1);
  }

  const highlights = useMemo(
    () =>
      asyncEvents.map((e, i) => ({
        t0: e.t0,
        t1: e.t1,
        active: i === activeEventIdx,
      })),
    [asyncEvents, activeEventIdx]
  );

  const sel = breathIdx >= 0 ? breaths[breathIdx] : null;
  const aiPct = asynchronyIndex != null ? asynchronyIndex * 100 : null;
  const aiFlagged = aiPct != null && aiPct > 10;
  const noticeFlagged = aiFlagged || mpAboveThreshold;

  return (
    <>
      {noticeFlagged && (
        <div
          style={{
            background: "rgba(220, 38, 38, 0.1)",
            borderBottom: "2px solid var(--alert)",
            color: "var(--alert)",
            padding: "10px 18px",
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          ⚠ Notice —{" "}
          {[
            aiFlagged && `Asynchrony index ${aiPct.toFixed(1)}% (>10%)`,
            mpAboveThreshold && mpStatus && `Mechanical power ${mpStatus.avg_mp_j_per_min.toFixed(1)} J/min (above threshold)`,
          ]
            .filter(Boolean)
            .join("  ·  ")}
        </div>
      )}
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
      </div>
      <p className="muted" style={{ margin: "0 18px 12px", fontSize: 12 }}>{status}</p>

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
            onSelectTime={selectBreathAtTime}
          />
          <WaveformChart
            title="Pressure (cmH2O)"
            color={COLORS.pressure}
            t={wf?.t_sec}
            y={wf?.pressure}
            breaths={breaths}
            sel={sel}
            highlights={highlights}
            onSelectTime={selectBreathAtTime}
          />
          <WaveformChart
            title="Volume (mL)"
            color={COLORS.volume}
            t={wf?.t_sec}
            y={wf?.volume}
            breaths={breaths}
            sel={sel}
            highlights={highlights}
            onSelectTime={selectBreathAtTime}
          />
        </div>
        <aside>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div>
              <h2>AI% / Mech. power</h2>
              <VitalsPanel
                asynchronyIndex={asynchronyIndex}
                aiLoading={aiLoading}
                mpStatus={mpStatus}
                mpLoading={mpLoading}
              />
            </div>
            <div>
              <h2>Asynchrony</h2>
              <AsynchronyPanel events={asyncEvents} activeIdx={activeEventIdx} onSelect={selectEvent} />
            </div>
          </div>
          <h2 style={{ marginTop: 16 }}>Metadata</h2>
          <MetadataPanel patient={patient} capture={capture} />
          <h2 style={{ marginTop: 16 }}>Breath</h2>
          <BreathPanel breath={sel} />
        </aside>
      </main>
    </>
  );
}
