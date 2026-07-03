// Example second page. It exists to show the pattern for adding a page:
//   1. create this file under src/pages/
//   2. register it in src/routes.jsx
// That's the whole process — the nav link and route appear automatically.
export default function AboutPage() {
  return (
    <div className="page">
      <h2>About this app</h2>
      <p>
        A viewer for the SMART-ICU ventilator waveform dataset. It plots the
        Flow / Pressure / Volume channels for a chosen patient capture and runs
        the breath-segmentation algorithm to break the trace into individual
        breaths with derived respiratory-mechanics metrics.
      </p>

      <h3>Architecture</h3>
      <p>
        <strong>Frontend</strong> — React + Vite (this app). <strong>Backend</strong>{" "}
        — FastAPI serving JSON under <code>/api</code>, wrapping the existing
        numpy/pandas segmentation code unchanged.
      </p>

      <h3>Adding a page</h3>
      <pre>{`1. src/pages/MyPage.jsx   ->  export default function MyPage() { ... }
2. src/routes.jsx        ->  { path: "/my", label: "My Page", element: <MyPage /> }`}</pre>
      <p className="muted">
        The nav bar and router are both generated from <code>routes.jsx</code>,
        so nothing else needs editing.
      </p>

      <h3>Adding an API endpoint</h3>
      <pre>{`backend/server/routers/<name>.py   ->  router = APIRouter(prefix="/api"); @router.get(...)
backend/server/main.py             ->  app.include_router(<name>.router)`}</pre>
    </div>
  );
}
