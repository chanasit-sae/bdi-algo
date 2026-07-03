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
    """True if the flow has real breathing excursion (not a flat/disconnected trace)."""
    flow = load_waveform(data_dir / fname)["flow"]
    return float(flow.max() - flow.min()) >= MIN_FLOW_RANGE


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
    this one server process/instance, same as `_index`.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._index: dict | None = None
        self.notification_scans: dict = {}

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
