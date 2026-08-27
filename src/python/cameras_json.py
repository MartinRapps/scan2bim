"""Shared loader for SuGaR/COLMAP ``cameras.json`` metadata.

Accepts either a bare JSON list of camera records or an object wrapping the
list under a ``frames`` or ``cameras`` key (both variants occur across 3DGS /
SuGaR exports).  Returns a plain list of dictionaries for downstream consumers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def load_camera_records(path: "str | Path") -> List[Dict[str, Any]]:
    """Load cameras.json into a list of camera-record dicts."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = data.get("frames") or data.get("cameras") or []
    else:
        records = []
    if not isinstance(records, list):
        raise ValueError(
            f"Camera metadata in {path} is neither a list nor a 'frames'/'cameras' object"
        )
    return records
