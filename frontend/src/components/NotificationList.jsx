import { Link } from "react-router-dom";

// Human label per notification `type`.
const TYPE_LABEL = { double_trigger: "Double triggering", auto_peep: "Auto-PEEP" };

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

// Per-type one-line detail + optional badge, so each asynchrony type shows the
// numbers that matter for it without the others crashing on missing fields.
function detailFor(n) {
  if (n.type === "auto_peep") {
    return {
      detail: `breath ${n.breath_idx_a} · residual ${(n.flow_residual_frac * 100).toFixed(0)}% · +${n.peep_delta.toFixed(1)} cmH₂O`,
      badge: n.pressure_flag ? "flow+pressure" : "flow only",
    };
  }
  return {
    detail: `breaths ${n.breath_idx_a} → ${n.breath_idx_b} · Te/Ti ${n.te_ti_ratio.toFixed(2)}`,
    badge: n.stacked ? "stacked" : null,
  };
}

export default function NotificationList({ notifications, formula }) {
  if (!notifications.length) {
    return <p className="muted">No asynchrony notifications with the current settings.</p>;
  }
  return (
    <ul className="notif-list">
      {notifications.map((n, i) => {
        const { detail, badge } = detailFor(n);
        return (
          <li key={i}>
            <Link to={viewerLink(n, formula)} className="notif-card">
              <span className="notif-type">{TYPE_LABEL[n.type] || n.type}</span>
              <span className="notif-patient">{n.patient_id.slice(0, 8)}…</span>
              <span className="notif-capture">
                day {n.day} · {n.time}
              </span>
              <span className="notif-detail">{detail}</span>
              {badge && <span className="notif-badge">{badge}</span>}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
