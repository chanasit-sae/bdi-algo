"""Runtime configuration for the backend.

The data directory can be overridden with the SMART_ICU_DATA environment
variable; otherwise it defaults to the repo's `smart_icu_data/` folder.
"""

from __future__ import annotations

import os
from pathlib import Path

# backend/server/config.py -> repo root is two levels up from backend/
ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA = ROOT / "smart_icu_data"

DATA_DIR = Path(os.environ.get("SMART_ICU_DATA", DEFAULT_DATA))

# Built frontend (frontend/dist) — served in production when present.
FRONTEND_DIST = ROOT / "frontend" / "dist"
