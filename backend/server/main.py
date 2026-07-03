"""FastAPI application entrypoint.

    cd backend
    uvicorn server.main:app --reload --port 8000

In development the React app runs on Vite (port 5173) and proxies /api here.
In production, build the frontend (`npm run build`) and this server will also
serve the static files from frontend/dist, so the whole app runs on one port.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse

from .config import DATA_DIR, FRONTEND_DIST
from .dataset import Dataset
from .routers import waveform, asynchrony


class SPAStaticFiles(StaticFiles):
    """Static files with single-page-app fallback: unknown paths return
    index.html so client-side routes (e.g. /about) survive a hard refresh."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # Unknown /api/* paths stay real 404s; only app routes fall back.
            if exc.status_code == 404 and not path.startswith("api"):
                return FileResponse(Path(self.directory) / "index.html")
            raise


async def _warmup_notifications(ds: Dataset) -> None:
    """Advance the Notifications page's default asynchrony scan toward
    completion in the background, off the startup path — a slow/huge dataset
    then delays only this one (self-healing) cache, not the whole app's
    availability. Runs in a thread since the scan itself is sync CPU/IO work;
    live requests race the same shared scan state and cooperate with it (see
    NotificationScan in dataset.py), so nothing here is wasted duplicate work.
    """
    try:
        await asyncio.to_thread(asynchrony.warmup_notifications, ds)
        print("notifications scan complete (background warmup)")
    except Exception as e:  # non-fatal: live requests still advance the same scan themselves
        print(f"notifications warmup stopped early (non-fatal): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the (potentially slow) dataset index once at startup.
    ds = Dataset(DATA_DIR)
    _ = ds.index  # force the build so the first request is fast
    app.state.dataset = ds
    print(f"loaded {len(ds.patients)} patients, {ds.n_captures()} captures from {DATA_DIR}")
    asyncio.create_task(_warmup_notifications(ds))
    yield


app = FastAPI(title="SMART-ICU Ventilator API", version="1.0.0", lifespan=lifespan)

# Allow the Vite dev server to call the API cross-origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# --- API routes ---------------------------------------------------------------
# To add a new API area, create backend/server/routers/<name>.py with an
# APIRouter and include it here.
app.include_router(waveform.router)
app.include_router(asynchrony.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# --- Built frontend (production) ---------------------------------------------
# When frontend/dist exists (after `npm run build`), serve it so the app is
# reachable on this single port. In dev this folder is absent and Vite serves
# the UI instead — that's expected.
if FRONTEND_DIST.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
