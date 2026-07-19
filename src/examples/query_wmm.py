from __future__ import annotations

import os
from pathlib import Path

import magerr_native as magerr


wmm_root = os.environ.get("MAGERR_WMM2025_ROOT", "")
coefficient_dir = str(Path(wmm_root) / "src" / "wmm2025") if wmm_root else ""

field = magerr.wmm_main_field(
    latitude=32.0,
    longitude=16.0,
    altitude_km=0.0,
    time_utc="2026-07-18T00:00:00Z",
    coefficient_dir=coefficient_dir,
)

print(field)
