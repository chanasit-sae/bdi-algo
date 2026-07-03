// Thin wrapper around the FastAPI backend. In dev, Vite proxies /api to :8000
// (see vite.config.js); in production the backend serves this app, so relative
// /api URLs work in both cases.

async function getJSON(path, params) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
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
  doubleTriggers: (file, opts) => getJSON("/double-triggers", { file, ...opts }),
};
