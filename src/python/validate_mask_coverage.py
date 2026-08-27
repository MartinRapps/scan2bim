#!/usr/bin/env python3
"""Validate that a frame sequence has sufficiently complete object masks."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np


def frame_id(name: str) -> int | None:
    match = re.search(r"(\d+)$", Path(name).stem)
    return int(match.group(1)) if match else None


def mask_path(root: Path, frame_number: int, level: str) -> Path | None:
    candidates = [
        root / f"frame_{frame_number:05d}" / f"{level}.png",
        root / f"frame_{frame_number:05d}_obj_001.png",
    ]
    return next((path for path in candidates if path.is_file()), None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--masks-dir", type=Path, required=True)
    parser.add_argument("--mask-name", choices=["default", "middle", "small"], default="middle")
    parser.add_argument("--max-empty-fraction", type=float, default=0.30)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not 0.0 <= args.max_empty_fraction < 1.0:
        parser.error("--max-empty-fraction must be in [0, 1)")

    frames = sorted(
        path for path in args.frames_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if not frames:
        raise FileNotFoundError(f"No frames found in {args.frames_dir}")

    empty_frames: list[str] = []
    missing_masks: list[str] = []
    nonempty_count = 0
    for frame in frames:
        number = frame_id(frame.name)
        if number is None:
            missing_masks.append(frame.name)
            continue
        path = mask_path(args.masks_dir, number, args.mask_name)
        if path is None:
            missing_masks.append(frame.name)
            empty_frames.append(frame.name)
            continue
        mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if mask is None or not np.any(mask > 0):
            empty_frames.append(frame.name)
        else:
            nonempty_count += 1

    total = len(frames)
    empty_fraction = len(empty_frames) / total
    report = {
        "frames_dir": str(args.frames_dir),
        "masks_dir": str(args.masks_dir),
        "mask_name": args.mask_name,
        "total_frames": total,
        "nonempty_frames": nonempty_count,
        "empty_frames": len(empty_frames),
        "missing_masks": len(missing_masks),
        "empty_fraction": empty_fraction,
        "max_empty_fraction": args.max_empty_fraction,
        "status": "failed" if empty_fraction >= args.max_empty_fraction else "ok",
        "empty_frame_names": empty_frames,
        "missing_mask_names": missing_masks,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total_frames", "nonempty_frames", "empty_frames", "empty_fraction", "status")}))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
