"""Dataset loading and the in-memory index shared by the API routes.

Moved out of the old single-file `viz_server.py`. `build_index` flattens the
patient metadata into the shape the frontend consumes and tags each capture as
connected / disconnected. The index is built once at startup and cached.
"""

from __future__ import annotations

import math
import threading
from pathlib import Path

from parser import load_dataset, metadata_frame, load_waveform

MIN_FLOW_RANGE = 5.0  # L/min; below this the flow is flat -> ventilator not on a patient
MIN_VOLUME_RANGE = 10.0  # mL; disconnected captures measured at exactly 0.0, real ones in the hundreds


def denan(obj):
    """Recursively replace float NaN with None so output is valid JSON.

    pandas leaves NaN in numeric columns even after .where(); browsers'
    JSON.parse rejects the bare `NaN` token that json.dumps would emit.
    """
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: denan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [denan(v) for v in obj]
    return obj


def _is_connected(data_dir: Path, fname: str) -> bool:
    """True if both flow and volume show real breathing excursion. Volume
    alone is the more reliable signal -- disconnected captures measure at
    exactly 0.0 range, while a few have enough noise in flow to clear
    MIN_FLOW_RANGE on its own despite delivering no actual tidal volume."""
    wf = load_waveform(data_dir / fname)
    flow_range = float(wf["flow"].max() - wf["flow"].min())
    volume_range = float(wf["volume"].max() - wf["volume"].min())
    return flow_range >= MIN_FLOW_RANGE and volume_range >= MIN_VOLUME_RANGE


def build_index(data_dir: Path) -> dict:
    """Flattened metadata grouped by patient, plus the set of valid CSV names.

    Every capture is included; captures whose flow is flat (no breathing,
    ventilator not connected to a patient) are tagged connected=False so the
    frontend can hide them by default and reveal them on demand.
    """
    records = load_dataset(data_dir)
    df = metadata_frame(records)
    captures = df.dropna(subset=["raw_data"]).where(df.notna(), None)
    rows = captures.to_dict(orient="records")
    connected = {r["raw_data"]: _is_connected(data_dir, r["raw_data"]) for r in rows}
    valid = {r["raw_data"] for r in rows}
    patients: dict[str, dict] = {}
    for r in rows:
        pid = r["patient_id"]
        p = patients.setdefault(
            pid,
            {
                "patient_id": pid,
                "age": r["age"],
                "sex": r["sex"],
                "bw_kg": r["bw_kg"],
                "ht_cm": r["ht_cm"],
                "bmi": r["bmi"],
                "ven": r["ven"],
                "captures": [],
            },
        )
        p["captures"].append(
            {
                "raw_data": r["raw_data"],
                "day": r["day"],
                "time": r["capture_time"],
                "pdx": r["pdx"],
                "pdx_icd": r["pdx_icd"],
                "sdx": r["sdx"],
                "sdx_icd": r["sdx_icd"],
                "operation": r["operation"],
                "connected": connected[r["raw_data"]],
            }
        )
    return {"patients": list(patients.values()), "valid": valid}


class NotificationScan:
    """Incrementally-built asynchrony scan for one parameter combination.

    `pending` is every (patient, capture) pair this scan covers, sorted
    most-recent-first *once* up front (cheap — metadata only, no waveform
    loading). Captures are then claimed and processed one at a time by
    whichever caller needs more: a request only advances far enough to
    fill the page it asked for, and a found event is appended straight to
    `results` and never recomputed. The background startup warmup and live
    page requests share and advance the exact same state, so whichever
    finishes a capture first is credited — no duplicate work either way.
    """

    def __init__(self, pending: list[tuple[dict, dict]]):
        self.pending = pending
        self.cursor = 0
        self.results: list[dict] = []
        self.scanned = 0
        self.complete = not pending
        self.lock = threading.Lock()

    def claim_next(self) -> tuple[dict, dict] | None:
        """Atomically take the next unclaimed (patient, capture) pair, or
        None once every pair has been claimed (marks the scan complete)."""
        with self.lock:
            if self.cursor >= len(self.pending):
                self.complete = True
                return None
            item = self.pending[self.cursor]
            self.cursor += 1
            return item

    def add_result(self, notification: dict) -> None:
        with self.lock:
            self.results.append(notification)

    def mark_scanned(self) -> None:
        with self.lock:
            self.scanned += 1


class Dataset:
    """Lazily-built, cached dataset index for the running server.

    `notification_scans` holds one NotificationScan per distinct set of
    detection params the asynchrony router has ever been asked for — owned
    here (rather than module-level in the router) so it lives and dies with
    this one server process/instance, same as `_index`. Mechanical power gets
    two caches: `mp_scans` is another NotificationScan (reused as-is — its
    claim/add/mark logic doesn't care what a "pending item" is), one per
    patient this time instead of one per capture, advanced with the same
    bounded-per-request pattern so a page request never waits on every
    patient's rolling window either. `mp_cache` sits underneath that: each
    patient's own rolling-average computation (see mechanical_power.py),
    keyed by (patient_id, segmentation, window_hours) -- NOT by threshold, so
    the same number is reused whether it's being checked against 17.0 J/min
    via /api/notifications or a different threshold via /api/mechanical-power.
    `ai_scans`/`asynchrony_index_cache` are the same pair of ideas again for
    the per-patient asynchrony index (see _patient_asynchrony_index).
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._index: dict | None = None
        self.notification_scans: dict = {}
        self.mp_scans: dict = {}
        self.mp_cache: dict = {}
        self.ai_scans: dict = {}
        self.asynchrony_index_cache: dict = {}

    @property
    def index(self) -> dict:
        if self._index is None:
            self._index = build_index(self.data_dir)
        return self._index

    @property
    def patients(self) -> list[dict]:
        return self.index["patients"]

    @property
    def valid(self) -> set[str]:
        return self.index["valid"]

    def n_captures(self) -> int:
        return sum(len(p["captures"]) for p in self.patients)
