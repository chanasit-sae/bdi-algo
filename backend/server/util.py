"""Small helpers shared by more than one router."""

from __future__ import annotations

from fastapi import HTTPException

from .dataset import Dataset


def require_valid(ds: Dataset, file: str) -> None:
    if file not in ds.valid:  # guard against path traversal / unknown files
        raise HTTPException(status_code=404, detail="unknown file")


def as_float(text: str, default: float) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default
