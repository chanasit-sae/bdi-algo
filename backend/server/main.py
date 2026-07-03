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
    """Pre-scan the dataset for the Notifications page's (fixed) default
    params in the background, off the startup path, so a slow/large dataset
    doesn't delay the whole app becoming reachable — just this one cache.
    Runs in a thread since the scan itself is sync CPU/IO-bound work.
    """
    try:
        await asyncio.to_thread(asynchrony.warmup_notifications, ds)
        print("notifications cache warmed")
    except Exception as e:  # non-fatal: the first real request will just fall back to computing + caching itself
        print(f"notifications warmup skipped (non-fatal): {e}")


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
