import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import NotificationList from "../components/NotificationList.jsx";

const PAGE_SIZE = 10;

// Notification center: scans the dataset for asynchrony (double-triggering,
// ineffective effort) using fixed default settings and lists what it finds,
// most recent first, 10 at a time. No tunable controls here on purpose —
// that's what the Viewer's controls are for, once you've clicked through to
// a specific event.
export default function NotificationsPage() {
  const [page, setPage] = useState(1);
  const [notifications, setNotifications] = useState([]);
  const [formula, setFormula] = useState(null);
  const [totalPages, setTotalPages] = useState(1);
  const [status, setStatus] = useState("");

  useEffect(() => {
    let cancelled = false;
    setStatus("scanning …");
    api
      .notifications({ page, page_size: PAGE_SIZE })
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
  }, [page]);

  return (
    <>
      <div className="controls">
        <span className="muted">{status}</span>
      </div>

      <div className="page" style={{ maxWidth: "none", padding: 16 }}>
        <h2 style={{ fontSize: 13, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".5px" }}>
          Notifications
        </h2>
        <p className="muted" style={{ fontSize: 12, maxWidth: 760 }}>
          Detects <strong>double triggering</strong>, <strong>ineffective effort</strong>, and{" "}
          <strong>auto-PEEP</strong> across the dataset using fixed default settings. Click a
          notification to inspect the flagged breaths in the Viewer, where detection can be
          tuned. See <code>docs/asynchrony.md</code> for all three formulas.
        </p>

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
