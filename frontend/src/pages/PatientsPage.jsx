import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api.js";

// The capture a card's click-through should land on -- most recent first,
// same ordering the backend uses for notifications, so "click a patient"
// and "click a notification" open the Viewer on a consistently-chosen capture.
function mostRecentCapture(p) {
  return [...p.captures].sort((a, b) => {
    const da = a.day ?? -1,
      db = b.day ?? -1;
    if (da !== db) return db - da;
    return (b.time || "").localeCompare(a.time || "");
  })[0];
}

// All patients, one block each, clickable through to that patient's Viewer.
// The patient list itself renders immediately (it's just /api/index, already
// cached) -- MP/AI are real per-patient computations and noticeably slower,
// so they're fetched separately, one patient at a time (not all at once --
// see ViewerPage's MP/AI fetch for why firing every patient's request
// concurrently is a real problem on a large dataset), and each card shows
// "loading…" for its own MP/AI until its turn comes up rather than the whole
// page waiting on every patient first.
export default function PatientsPage() {
  const [patients, setPatients] = useState(null);
  const [data, setData] = useState({}); // patient_id -> { ai, mp, loading }
  const [status, setStatus] = useState("loading patients …");
  const [query, setQuery] = useState("");

  useEffect(() => {
    api
      .index()
      .then((d) => {
        setPatients(d.patients);
        setStatus(`${d.patients.length} patients`);
      })
      .catch((e) => setStatus("error: " + e.message));
  }, []);

  useEffect(() => {
    if (!patients || !patients.length) return;
    let cancelled = false;
    setData(Object.fromEntries(patients.map((p) => [p.patient_id, { ai: null, mp: null, loading: true }])));
    (async () => {
      for (const p of patients) {
        if (cancelled) return;
        try {
          const [ai, mp] = await Promise.all([api.asynchronyIndex(p.patient_id), api.mechanicalPower(p.patient_id)]);
          if (cancelled) return;
          setData((prev) => ({
            ...prev,
            [p.patient_id]: { ai: ai.asynchrony_index, mp: mp.status ? mp.status.avg_mp_j_per_min : null, loading: false },
          }));
        } catch {
          if (cancelled) return;
          setData((prev) => ({ ...prev, [p.patient_id]: { ai: null, mp: null, loading: false } }));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [patients]);

  const filtered = patients
    ? patients.filter((p) => p.patient_id.toLowerCase().includes(query.trim().toLowerCase()))
    : null;

  return (
    <>
      <div className="controls">
        <div className="field">
          <label>Search</label>
          <input
            type="text"
            placeholder="patient ID…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <span className="muted">{status}</span>
      </div>

      <div className="page" style={{ maxWidth: "none", padding: 16 }}>
        <h2 style={{ fontSize: 13, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".5px" }}>
          Patients
        </h2>

        {!patients ? (
          <p className="muted">loading …</p>
        ) : filtered.length === 0 ? (
          <p className="muted">no patients match “{query}”</p>
        ) : (
          <div className="patient-grid">
            {filtered.map((p) => {
              const entry = data[p.patient_id];
              const loading = !entry || entry.loading;
              const pct = entry && entry.ai != null ? entry.ai * 100 : null;
              const aiColor = loading ? "var(--muted)" : pct != null && pct > 10 ? "var(--alert)" : "var(--accent)";
              const cap = mostRecentCapture(p);
              return (
                <Link
                  key={p.patient_id}
                  to={cap ? `/?file=${encodeURIComponent(cap.raw_data)}` : "/"}
                  className="patient-card"
                >
                  <div className="patient-card-id">{p.patient_id.slice(0, 8)}…</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                    <div>
                      <div className="patient-card-ai" style={{ color: aiColor }}>
                        {loading ? "loading…" : pct != null ? `${pct.toFixed(1)}%` : "—"}
                      </div>
                      <div className="patient-card-ai-label">Asynchrony index</div>
                    </div>
                    <div>
                      <div className="patient-card-mp">
                        {loading ? "loading…" : entry.mp != null ? entry.mp.toFixed(1) : "—"}
                      </div>
                      <div className="patient-card-ai-label">MP J/min</div>
                    </div>
                  </div>
                  <div className="patient-card-detail">
                    {p.sex || "?"} · {p.age ?? "?"} yr · {p.bw_kg ?? "—"} kg / {p.ht_cm ?? "—"} cm
                  </div>
                  <div className="patient-card-detail">Ventilator {p.ven ?? "—"}</div>
                  <div className="patient-card-detail">{p.captures.length} captures</div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
