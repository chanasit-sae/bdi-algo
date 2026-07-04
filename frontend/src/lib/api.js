// Thin wrapper around the FastAPI backend. In dev, Vite proxies /api to :8000
// (see vite.config.js); in production the backend serves this app, so relative
// /api URLs work in both cases.

function buildQs(params) {
  if (!params) return "";
  // Built manually (not `new URLSearchParams(params)`) so array values
  // (e.g. notifications' `types`) become repeated keys (?types=a&types=b),
  // which is what FastAPI's `list[str]` query params expect — the object
  // shortcut would instead comma-join them into a single "a,b" value.
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) v.forEach((item) => sp.append(k, item));
    else sp.append(k, v);
  }
  return "?" + sp.toString();
}

async function getJSON(path, params) {
  const res = await fetch(`/api${path}${buildQs(params)}`);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.json();
}

// Cached GET, for endpoints whose response is deterministic for the life of
// this browser session (the dataset doesn't change while the server is
// running) -- keyed on the full request URL, in a module-level Map so it
// survives page components mounting/unmounting as the user navigates (e.g.
// Patients -> Viewer -> back to Patients no longer re-fetches every
// patient's MP/AI from scratch). Caches the in-flight *promise*, not just
// the resolved value, so concurrent identical requests (the per-patient
// MP/AI loops in PatientsPage/ViewerPage) are deduped too, not just repeated
// on a second call. A failed request is evicted so it can be retried.
//
// NOT used for /api/notifications: that endpoint intentionally returns
// progressively more complete results as its background scan advances
// (`scan_complete` flips from false to true over time) -- caching it would
// freeze the Notifications page on whatever partial answer it first saw.
const cache = new Map();
function cachedGetJSON(path, params) {
  const url = `/api${path}${buildQs(params)}`;
  if (cache.has(url)) return cache.get(url);
  const promise = getJSON(path, params).catch((err) => {
    cache.delete(url);
    throw err;
  });
  cache.set(url, promise);
  return promise;
}

export const api = {
  index: () => cachedGetJSON("/index"),
  waveform: (file) => cachedGetJSON("/waveform", { file }),
  breaths: (file, opts) => cachedGetJSON("/breaths", { file, ...opts }),
  asynchrony: (file, opts) => cachedGetJSON("/asynchrony", { file, ...opts }),
  notifications: (opts) => getJSON("/notifications", opts),
  asynchronyIndex: (patientId) => cachedGetJSON("/asynchrony-index", patientId ? { patient_id: patientId } : undefined),
  mechanicalPower: (patientId) => cachedGetJSON("/mechanical-power", patientId ? { patient_id: patientId } : undefined),
};
