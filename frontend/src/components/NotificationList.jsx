import { Link } from "react-router-dom";

// Human label per notification `type`. Only "double_trigger" exists today;
// add new asynchrony types here as they're detected server-side.
const TYPE_LABEL = { double_trigger: "Double triggering" };

// Build the Viewer deep-link for one notification: selects the same
// patient/capture, reproduces the exact segmentation that flagged it (so the
// breath boundaries match), pre-selects the first breath of the pair, and
// marks the flagged span so the chart highlights it on arrival.
function viewerLink(n) {
  const sp = new URLSearchParams({
    file: n.raw_data,
    breath: String(n.breath_idx_a),
    ...n.segmentation,
    hl0: String(n.t_insp_start_a),
    hl1: String(n.t_exp_end_b),
  });
  return `/?${sp.toString()}`;
}

export default function NotificationList({ notifications }) {
  if (!notifications.length) {
    return <p className="muted">No asynchrony notifications with the current settings.</p>;
  }
  return (
    <ul className="notif-list">
      {notifications.map((n, i) => (
        <li key={i}>
          <Link to={viewerLink(n)} className="notif-card">
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
