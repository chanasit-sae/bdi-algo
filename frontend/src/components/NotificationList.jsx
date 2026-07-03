import { Link } from "react-router-dom";

// Human label per notification `type`. Only "double_trigger" exists today;
// add new asynchrony types here as they're detected server-side.
const TYPE_LABEL = { double_trigger: "Double triggering" };

// Build the Viewer deep-link for one notification: selects the same
// patient/capture, reproduces the exact segmentation AND formula that flagged
// it (baseline/hysteresis/... plus ratio/ti_ref/stacking), so the Viewer's own
// asynchrony scan is guaranteed to find this same event and highlight it.
function viewerLink(n, formula) {
  const sp = new URLSearchParams({
    file: n.raw_data,
    breath: String(n.breath_idx_a),
    ...n.segmentation,
    ratio: String(formula.ratio),
    ti_ref: formula.ti_ref,
    require_stacking: String(formula.require_stacking),
    stack_ratio: String(formula.stack_ratio),
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
              breaths {n.breath_idx_a} → {n.breath_idx_b} · Te/Ti {n.te_ti_ratio.toFixed(2)}
            </span>
            {n.stacked && <span className="notif-badge">stacked</span>}
          </Link>
        </li>
      ))}
    </ul>
  );
}
