"""Shared mask-path resolution and loading.

Consolidates the duplicated mask helpers in ``crop_mesh_multiview.py`` and
``filter_sugar_cameras_by_mask.py``.  Masks are organised per frame as
``<masks_dir>/frame_#####/<level>.png`` (levels: default/middle/small), with
legacy fallbacks to ``<masks_dir>/000/<frame_id>.png`` and
``<masks_dir>/<stem>.png``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

FRAME_ID_PATTERN = re.compile(r"(\d+)$")


def frame_id_from_image_name(image_name: str) -> Optional[int]:
    """Return the trailing integer of an image name (e.g. ``frame_00012`` -> 12)."""
    match = FRAME_ID_PATTERN.search(Path(image_name).stem)
    return int(match.group(1)) if match else None


def iter_mask_candidates(masks_dir: Path, image_name: str, level: str) -> Iterable[Path]:
    """Yield supported mask locations in priority order."""
    stem = Path(image_name).stem
    fid = frame_id_from_image_name(stem)
    if fid is not None:
        frame_name = f"frame_{fid:05d}"
        yield masks_dir / frame_name / f"{level}.png"
        yield masks_dir / "000" / f"{fid:05d}.png"
        if level == "default":
            yield masks_dir / f"{frame_name}_obj_001.png"
    yield masks_dir / f"{stem}.png"
    yield masks_dir / "000" / f"{stem}.png"


def find_mask(masks_dir: Path, image_name: str, level: str) -> Optional[Path]:
    """Return the first existing mask candidate path, or ``None``."""
    return next((path for path in iter_mask_candidates(masks_dir, image_name, level) if path.is_file()), None)


def load_mask(
    masks_dir: Path,
    image_name: str,
    level: str,
    dilation_px: int = 0,
) -> Tuple[Optional[np.ndarray], Optional[Path]]:
    """Load a binary mask for ``image_name``/``level``.

    Returns ``(mask_array, mask_path)`` with a bool ``np.ndarray`` (contiguous)
    or ``(None, None)`` if no mask file exists.  ``dilation_px > 0`` applies a
    symmetric PIL MaxFilter of width ``2*dilation_px+1`` (morphological dilation)
    before binarisation.
    """
    mask_path = find_mask(masks_dir, image_name, level)
    if mask_path is None:
        return None, None
    with Image.open(mask_path) as image:
        mask_image = image.convert("L")
        if dilation_px > 0:
            mask_image = mask_image.filter(ImageFilter.MaxFilter(size=2 * dilation_px + 1))
        mask = np.asarray(mask_image, dtype=np.uint8) > 0
    return np.ascontiguousarray(mask), mask_path


def mask_nonempty(mask_path: Path) -> bool:
    """Return ``True`` if the mask has any non-zero pixel."""
    with Image.open(mask_path) as image:
        return image.convert("L").getbbox() is not None
