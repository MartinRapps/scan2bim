"""Shared hierarchical mask utilities (default / middle / small).

Consolidates the morphology used by ``prep_sts_scene.py`` and
``extract_masks_notebook_flow.py``: from a binary base mask, ``middle`` is one
5x5 rectangular erosion and ``small`` is two erosions; ``default`` is the
unchanged base.  This three-level hierarchy feeds the curriculum learning of
Segment-then-Splat.
"""

from __future__ import annotations

from typing import Dict

import cv2
import numpy as np

LEVELS = ("default", "middle", "small")


def to_binary_mask(mask: np.ndarray) -> np.ndarray:
    """Normalise SAM outputs that may be 0/1 into strict 0/255 uint8 masks."""
    return np.where(mask > 0, 255, 0).astype(np.uint8)


def make_hierarchical_masks(base_mask: np.ndarray, kernel_size: int = 5) -> Dict[str, np.ndarray]:
    """Return ``{"default", "middle", "small"}`` masks from a binary base mask.

    ``middle`` = one rectangular erosion, ``small`` = two erosions,
    ``default`` = the binarised base mask unchanged.
    """
    base = to_binary_mask(base_mask)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    return {
        "default": base,
        "middle": cv2.erode(base, kernel, iterations=1),
        "small": cv2.erode(base, kernel, iterations=2),
    }
