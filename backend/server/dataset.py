"""Dataset loading and the in-memory index shared by the API routes.

Moved out of the old single-file `viz_server.py`. `build_index` flattens the
patient metadata into the shape the frontend consumes and tags each capture as
connected / disconnected. The index is built once at startup and cached.
"""

from __future__ import annotations

import math
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


class Dataset:
    """Lazily-built, cached dataset index for the running server."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._index: dict | None = None

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
