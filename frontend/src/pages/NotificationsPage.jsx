import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api.js";
import {
  DEFAULT_SEGMENTATION_PARAMS,
  segmentationQuery,
  DEFAULT_ASYNCHRONY_PARAMS,
  asynchronyQuery,
} from "../lib/segmentation.js";
import ControlsBar from "../components/ControlsBar.jsx";
import DoubleTriggerControls from "../components/DoubleTriggerControls.jsx";
import NotificationList from "../components/NotificationList.jsx";

const DEFAULT_PARAMS = { ...DEFAULT_SEGMENTATION_PARAMS, ...DEFAULT_ASYNCHRONY_PARAMS };

// Notification center: scans the dataset for asynchrony and lists what it
// finds. Only double-triggering exists today; other asynchrony types can be
// added on the backend (/api/notifications) and will show up here for free,
// since each notification already carries a `type` field.
export default function NotificationsPage() {
  const [patients, setPatients] = useState(null);
  const [patientFilter, setPatientFilter] = useState("");
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [notifications, setNotifications] = useState([]);
  const [formula, setFormula] = useState(DEFAULT_ASYNCHRONY_PARAMS);
  const [status, setStatus] = useState("");

  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  useEffect(() => {
    api
      .index()
      .then((d) => setPatients(d.patients))
      .catch((e) => setStatus("error: " + e.message));
  }, []);

  const segOpts = useMemo(() => segmentationQuery(params), [params]);
  const opts = useMemo(
    () => ({
      ...segOpts,
      ...asynchronyQuery(params),
      include_disconnected: params.showDisc,
      ...(patientFilter ? { patient_id: patientFilter } : {}),
    }),
    [segOpts, params.ratio, params.tiRef, params.requireStacking, params.stackRatio, params.showDisc, patientFilter]
  );

  useEffect(() => {
    let cancelled = false;
    setStatus("scanning …");
    api
      .notifications(opts)
      .then((d) => {
        if (cancelled) return;
        setNotifications(d.notifications);
        setFormula(d.formula);
        setStatus(`${d.notifications.length} notification(s) across ${d.scanned_captures} captures scanned`);
      })
      .catch((e) => !cancelled && setStatus("error: " + e.message));
    return () => {
      cancelled = true;
    };
  }, [opts]);

  return (
    <>
      <div className="controls">
        <div className="field">
          <label title="restrict the scan to one patient">Patient</label>
          <select value={patientFilter} onChange={(e) => setPatientFilter(e.target.value)}>
            <option value="">— all patients —</option>
            {(patients || []).map((p) => (
              <option key={p.patient_id} value={p.patient_id}>
                {p.patient_id.slice(0, 8)}…
              </option>
            ))}
          </select>
        </div>
        <span className="muted">{status}</span>
      </div>

      <ControlsBar params={params} set={set} />
      <DoubleTriggerControls params={params} set={set} />

      <div className="page" style={{ maxWidth: "none", padding: 16 }}>
        <h2 style={{ fontSize: 13, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".5px" }}>
          Notifications
        </h2>
        <p className="muted" style={{ fontSize: 12, maxWidth: 760 }}>
          Currently detects <strong>double triggering</strong> (Te &lt; ratio × Ti_ref, per
          Thille et al. 2006 — see the Viewer's segmentation controls above and{" "}
          <code>docs/asynchrony.md</code> for the formula). More asynchrony types can be added
          here later. Click a notification to inspect the flagged breaths in the Viewer.
        </p>
        <NotificationList notifications={notifications} formula={formula} />
      </div>
    </>
  );
}
