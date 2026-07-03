// Thin wrapper around the FastAPI backend. In dev, Vite proxies /api to :8000
// (see vite.config.js); in production the backend serves this app, so relative
// /api URLs work in both cases.

async function getJSON(path, params) {
  let qs = "";
  if (params) {
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
    qs = "?" + sp.toString();
  }
  const res = await fetch(`/api${path}${qs}`);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.json();
}

export const api = {
  index: () => getJSON("/index"),
  waveform: (file) => getJSON("/waveform", { file }),
  breaths: (file, opts) => getJSON("/breaths", { file, ...opts }),
  asynchrony: (file, opts) => getJSON("/asynchrony", { file, ...opts }),
  notifications: (opts) => getJSON("/notifications", opts),
  asynchronyIndex: (patientId) => getJSON("/asynchrony-index", patientId ? { patient_id: patientId } : undefined),
  mechanicalPower: (patientId) => getJSON("/mechanical-power", patientId ? { patient_id: patientId } : undefined),
};
