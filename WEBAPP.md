# Ventilator Waveform Web App

A frontend/backend split of the ventilator waveform viewer, so pages and API
endpoints can be added independently.

- **Frontend** — React + Vite (`frontend/`). Multi-page via `react-router`.
- **Backend** — FastAPI (`backend/server/`) serving JSON under `/api`, wrapping
  the existing numpy/pandas segmentation code (`parser.py`, `breath_segment.py`,
  `breath_metrics.py`) unchanged.

> The old single-file `backend/viz_server.py` (stdlib server with the whole UI
> baked into one HTML string) is superseded by this and kept only for reference.

## Prerequisites

- Python **3.12** (numpy/pandas are installed there — `py -3.12`)
- Node.js 18+ / npm

> **Windows / PowerShell users:** run one command per line — PowerShell (5.1)
> does **not** support `&&` chaining. Always launch the backend with the venv's
> Python via the `&` call operator (`& "..\.venv\Scripts\python.exe" ...`), not a
> bare `python` (that resolves to Python 3.14, which has no fastapi/numpy).

## First-time setup

PowerShell (run from the repo root):

```powershell
# Backend: virtualenv + deps (Python 3.12 — that's where numpy/pandas live)
py -3.12 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt

# Frontend: deps
cd frontend
npm install
cd ..
```

## Run in development (two terminals)

**Terminal 1 — API on :8000**

```powershell
cd "c:\Users\Ashira Sansoda\Desktop\bdi-algo\backend"
& "..\.venv\Scripts\python.exe" -m uvicorn server.main:app --reload --port 8000
```

**Terminal 2 — UI on :5173** (proxies `/api` to :8000)

```powershell
cd "c:\Users\Ashira Sansoda\Desktop\bdi-algo\frontend"
npm run dev
```

Open <http://localhost:5173>. Editing any file hot-reloads.

## Run as one server (production style)

Build the frontend, then the backend serves it from `frontend/dist` on a single
port — no separate UI server needed.

```powershell
cd "c:\Users\Ashira Sansoda\Desktop\bdi-algo\frontend"
npm run build
cd ..\backend
& "..\.venv\Scripts\python.exe" -m uvicorn server.main:app --port 8000
# open http://localhost:8000
```

The data directory defaults to `smart_icu_data/`; override with the
`SMART_ICU_DATA` environment variable.

## Project layout

```
backend/
  server/
    main.py            # FastAPI app: CORS, routers, static-serve of dist
    config.py          # data dir + paths
    dataset.py         # patient/capture index (cached at startup)
    deps.py            # shared FastAPI dependencies
    util.py            # require_valid / as_float (shared by routers)
    segmentation.py     # segment_from_params (shared breath-segmentation call)
    routers/
      waveform.py      # /api/index, /api/waveform, /api/breaths
      asynchrony.py    # /api/double-triggers (see docs/asynchrony.md)
  parser.py            # (unchanged) metadata + CSV loading
  breath_segment.py    # (unchanged) segmentation algorithm
  breath_metrics.py    # (unchanged) derived per-breath metrics
  asynchrony.py        # double-triggering detection formula
  requirements.txt
frontend/
  src/
    routes.jsx         # <-- register pages here (nav + router are generated)
    App.jsx            # app shell / nav
    pages/             # one file per page (ViewerPage, NotificationsPage, AboutPage, …)
    components/        # ControlsBar, WaveformChart, CaptureSelect, panels, …
    lib/api.js         # fetch helpers for /api
    lib/charts.js      # canvas waveform renderer (+ event-highlight bands)
    lib/usePatientCapture.js  # shared patient/capture selection state
    lib/segmentation.js       # shared segmentation-param defaults + query mapping
```

## Adding a page

1. Create `frontend/src/pages/MyPage.jsx` exporting a component.
2. Register it in `frontend/src/routes.jsx`:
   ```jsx
   { path: "/my", label: "My Page", element: <MyPage /> }
   ```

The nav link and route are generated from that array — nothing else to touch.
Use `nav: false` to add a route without a nav link.

## Adding an API endpoint

1. Create `backend/server/routers/<name>.py` with an `APIRouter(prefix="/api")`.
2. Include it in `backend/server/main.py`: `app.include_router(<name>.router)`.

Interactive API docs are available at <http://localhost:8000/docs>.
