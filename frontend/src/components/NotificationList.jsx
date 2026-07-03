import { Link } from "react-router-dom";

// Human label per notification `type`. Add new asynchrony types here as the
// backend gains new detectors — the card layout and viewer link already work
// off the generic t0/t1/detail fields, no other change needed.
const TYPE_LABEL = {
  double_trigger: "Double triggering",
  ineffective_effort: "Ineffective effort",
  auto_peep: "Auto-PEEP",
};

// Build the Viewer deep-link for one notification: selects the same
// patient/capture, reproduces the exact segmentation AND every detector's
// formula params that produced it, so the Viewer's own asynchrony scan is
// guaranteed to find this same event and highlight it.
function viewerLink(n, formula) {
  const { double_trigger: dt, ineffective_effort: ie, auto_peep: ap } = formula;
  const sp = new URLSearchParams({
    file: n.raw_data,
    breath: String(n.breath_idx_a),
    ...n.segmentation,
    ratio: String(dt.ratio),
    ti_ref: dt.ti_ref,
    require_stacking: String(dt.require_stacking),
    stack_ratio: String(dt.stack_ratio),
    flow_prominence: String(ie.flow_prominence),
    flow_prominence_max: String(ie.flow_prominence_max),
    pressure_prominence: String(ie.pressure_prominence),
    concurrent_tol_sec: String(ie.concurrent_tol_sec),
    bump_lookback_sec: String(ie.bump_lookback_sec),
    flow_frac: String(ap.flow_frac),
    flow_abs: String(ap.flow_abs),
    peep_min: String(ap.peep_min),
    require_pressure: String(ap.require_pressure),
  });
  return `/?${sp.toString()}`;
}

export default function NotificationList({ notifications, formula }) {
  if (!notifications.length) {
    return <p className="muted">No asynchrony notifications with the current settings.</p>;
  }
  return (
    <ul className="notif-list">
      {notifications.map((n, i) => (
        <li key={i}>
          <Link to={viewerLink(n, formula)} className="notif-card">
            <span className="notif-type">{TYPE_LABEL[n.type] || n.type}</span>
            <span className="notif-patient">{n.patient_id.slice(0, 8)}…</span>
            <span className="notif-capture">
              day {n.day} · {n.time}
            </span>
            <span className="notif-detail">
              breath {n.breath_idx_a}
              {n.breath_idx_b != null && ` → ${n.breath_idx_b}`} · {n.detail}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
