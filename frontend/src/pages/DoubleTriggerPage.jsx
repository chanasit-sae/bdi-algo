import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api.js";
import { COLORS } from "../lib/charts.js";
import { usePatientCapture } from "../lib/usePatientCapture.js";
import { DEFAULT_SEGMENTATION_PARAMS, segmentationQuery } from "../lib/segmentation.js";
import CaptureSelect from "../components/CaptureSelect.jsx";
import ControlsBar from "../components/ControlsBar.jsx";
import DoubleTriggerControls from "../components/DoubleTriggerControls.jsx";
import WaveformChart from "../components/WaveformChart.jsx";
import DoubleTriggerTable from "../components/DoubleTriggerTable.jsx";

const DEFAULT_DT_PARAMS = {
  ...DEFAULT_SEGMENTATION_PARAMS,
  ratio: 0.5,
  tiRef: "pair",
  requireStacking: false,
  stackRatio: 1.5,
};

export default function DoubleTriggerPage() {
  const [patients, setPatients] = useState(null);
  const [params, setParams] = useState(DEFAULT_DT_PARAMS);
  const [wf, setWf] = useState(null);
  const [breaths, setBreaths] = useState([]);
  const [events, setEvents] = useState([]);
  const [formula, setFormula] = useState(null);
  const [activeIdx, setActiveIdx] = useState(-1);
  const [status, setStatus] = useState("");

  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    api
      .index()
      .then((d) => setPatients(d.patients))
      .catch((e) => setStatus("error: " + e.message));
  }, []);

  const { visiblePatients, patientId, setPatientId, caps, file, setFile } = usePatientCapture(
    patients,
    params.showDisc
  );

  const segOpts = useMemo(() => segmentationQuery(params), [params]);
  const dtOpts = useMemo(
    () => ({
      ...segOpts,
      ratio: params.ratio,
      ti_ref: params.tiRef,
      require_stacking: params.requireStacking,
      stack_ratio: params.stackRatio,
    }),
    [segOpts, params.ratio, params.tiRef, params.requireStacking, params.stackRatio]
  );

  useEffect(() => {
    if (!file) {
      setWf(null);
      setBreaths([]);
      setEvents([]);
      setFormula(null);
      return;
    }
    let cancelled = false;
    setStatus("loading " + file + " …");
    setActiveIdx(-1);
    Promise.all([api.waveform(file), api.breaths(file, segOpts), api.doubleTriggers(file, dtOpts)])
      .then(([wfData, brData, dtData]) => {
        if (cancelled) return;
        setWf(wfData);
        setBreaths(brData.breaths);
        setEvents(dtData.events);
        setFormula(dtData.formula);
        setStatus(
          `${brData.breaths.length} breaths · ${dtData.events.length} double-triggered pair(s)`
        );
      })
      .catch((e) => !cancelled && setStatus("error: " + e.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, segOpts, dtOpts]);

  const highlights = useMemo(
    () =>
      events.map((e, i) => ({
        t0: e.t_insp_start_a,
        t1: e.t_exp_end_b,
        active: i === activeIdx,
      })),
    [events, activeIdx]
  );

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
        <span className="muted">{status}</span>
      </div>

      <ControlsBar params={params} set={set} />
      <DoubleTriggerControls params={params} set={set} />

      <main className="viewer">
        <div className="charts">
          <WaveformChart
            title="Flow (L/min) — red band = flagged double-triggered pair"
            color={COLORS.flow}
            t={wf?.t_sec}
            y={wf?.flow}
            breaths={breaths}
            highlights={highlights}
          />
          <WaveformChart
            title="Volume (mL)"
            color={COLORS.volume}
            t={wf?.t_sec}
            y={wf?.volume}
            breaths={breaths}
            highlights={highlights}
          />
        </div>
        <aside>
          <h2>Formula</h2>
          <p style={{ fontSize: 13 }}>
            A breath pair is <strong>double-triggered</strong> when
          </p>
          <pre style={{ fontSize: 12, background: "#0b1119", border: "1px solid var(--line)", borderRadius: 6, padding: "8px 10px" }}>
            Te(i) &lt; ratio × Ti_ref
          </pre>
          <p className="muted" style={{ fontSize: 12 }}>
            Te(i) is the expiratory gap before the next breath starts. Ti_ref
            is the {params.tiRef === "pair" ? "pair's mean Ti" : params.tiRef === "capture" ? "capture's mean Ti" : "breath's own Ti"}.
            Default ratio 0.5, per Thille AW et al., <em>Intensive Care Med</em> 2006;32:1515–1522.
            {params.requireStacking && (
              <> Also requires combined Vt &gt; {params.stackRatio} × 2 × median Vt (volume stacking).</>
            )}
          </p>
          {formula && (
            <dl className="kv" style={{ marginTop: 10 }}>
              <dt>Breaths</dt>
              <dd>{breaths.length}</dd>
              <dt>Flagged pairs</dt>
              <dd>{events.length}</dd>
              <dt>ratio</dt>
              <dd>{formula.ratio}</dd>
              <dt>ti_ref</dt>
              <dd>{formula.ti_ref}</dd>
              <dt>stacking required</dt>
              <dd>{formula.require_stacking ? "yes" : "no"}</dd>
            </dl>
          )}
        </aside>
      </main>

      <div style={{ padding: "0 16px 16px" }}>
        <h2 style={{ fontSize: 13, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".5px" }}>
          Flagged pairs
        </h2>
        <DoubleTriggerTable events={events} activeIdx={activeIdx} onSelect={setActiveIdx} />
      </div>
    </>
  );
}
