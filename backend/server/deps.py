"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from .dataset import Dataset


def get_dataset(request: Request) -> Dataset:
    """The process-wide dataset index, built once at startup (see main.py)."""
    return request.app.state.dataset
