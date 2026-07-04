import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import NotificationList, { TYPE_LABEL } from "../components/NotificationList.jsx";

const PAGE_SIZE = 16; // 4x4 card grid
const ALL_TYPES = Object.keys(TYPE_LABEL);

// Notification center: scans the dataset for asynchrony using fixed default
// settings and shows what it finds as a 4x4 grid of cards, most recent
// first, 16 at a time. No tunable controls here on purpose — that's what
// the Viewer's controls are for, once you've clicked through to a specific
// event. The one filter that IS available is by notification type (which
// detector flagged it), since that's just picking which already-found
// results to show, not a detection-formula setting. See the About page for
// what each notification type means.
export default function NotificationsPage() {
  const [page, setPage] = useState(1);
  const [enabledTypes, setEnabledTypes] = useState(() => new Set(ALL_TYPES));
  const [notifications, setNotifications] = useState([]);
  const [formula, setFormula] = useState(null);
  const [totalPages, setTotalPages] = useState(1);
  const [status, setStatus] = useState("");

  function toggleType(t) {
    setEnabledTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
    setPage(1);
  }

  useEffect(() => {
    let cancelled = false;
    if (enabledTypes.size === 0) {
      setNotifications([]);
      setTotalPages(1);
      setStatus("no types selected");
      return;
    }
    setStatus("scanning …");
    const opts = { page, page_size: PAGE_SIZE };
    if (enabledTypes.size < ALL_TYPES.length) opts.types = [...enabledTypes];
    api
      .notifications(opts)
      .then((d) => {
        if (cancelled) return;
        setNotifications(d.notifications);
        setFormula(d.formula);
        setTotalPages(d.total_pages);
        const found = `${d.total} found across ${d.scanned_captures} captures scanned`;
        setStatus(d.scan_complete ? found : `${found} (still scanning older captures…)`);
      })
      .catch((e) => !cancelled && setStatus("error: " + e.message));
    return () => {
      cancelled = true;
    };
  }, [page, enabledTypes]);

  return (
    <>
      <div className="controls">
        <span className="muted">{status}</span>
      </div>

      <div className="page" style={{ maxWidth: "none", padding: 16 }}>
        <h2 style={{ fontSize: 13, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".5px" }}>
          Notifications
        </h2>

        <div className="field" style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 12 }}>
          {ALL_TYPES.map((t) => (
            <label key={t} style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 4 }}>
              <input
                type="checkbox"
                checked={enabledTypes.has(t)}
                onChange={() => toggleType(t)}
              />
              {TYPE_LABEL[t]}
            </label>
          ))}
        </div>

        {formula && <NotificationList notifications={notifications} formula={formula} />}

        <div className="pagination">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            ‹ Prev
          </button>
          <span className="muted">
            Page {page} of {totalPages}
          </span>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Next ›
          </button>
        </div>
      </div>
    </>
  );
}
