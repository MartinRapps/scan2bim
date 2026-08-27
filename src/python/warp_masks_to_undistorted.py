#!/usr/bin/env python3
"""Warp raw-frame masks into COLMAP's ideal STS image domain.

COLMAP estimates the camera model on the raw frames and ``image_undistorter``
creates a new ideal PINHOLE image domain.  This utility applies the matching
inverse pixel map to binary masks so the STS images and masks describe the same
pixels.  It intentionally uses nearest-neighbour interpolation.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class Camera:
    camera_id: int
    model: str
    width: int
    height: int
    params: tuple[float, ...]


def _non_comment_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def read_cameras(path: Path) -> dict[int, Camera]:
    cameras: dict[int, Camera] = {}
    for line in _non_comment_lines(path):
        fields = line.split()
        if len(fields) < 5:
            continue
        camera_id = int(fields[0])
        cameras[camera_id] = Camera(
            camera_id=camera_id,
            model=fields[1],
            width=int(fields[2]),
            height=int(fields[3]),
            params=tuple(float(value) for value in fields[4:]),
        )
    if not cameras:
        raise ValueError(f"No cameras found in {path}")
    return cameras


def read_image_camera_ids(path: Path) -> dict[str, int]:
    lines = _non_comment_lines(path)
    result: dict[str, int] = {}
    # COLMAP images.txt stores one image record followed by one observation line.
    for line in lines:
        fields = line.split(maxsplit=9)
        if len(fields) < 10:
            continue
        try:
            image_id = int(fields[0])
            camera_id = int(fields[8])
        except ValueError:
            continue
        if image_id <= 0:
            continue
        result[fields[9]] = camera_id
    if not result:
        raise ValueError(f"No image records found in {path}")
    return result


def _intrinsics(camera: Camera) -> tuple[float, float, float, float]:
    if camera.model == "SIMPLE_PINHOLE":
        focal, cx, cy = camera.params[:3]
        return focal, focal, cx, cy
    if camera.model == "PINHOLE":
        fx, fy, cx, cy = camera.params[:4]
        return fx, fy, cx, cy
    if camera.model == "SIMPLE_RADIAL":
        focal, cx, cy = camera.params[:3]
        return focal, focal, cx, cy
    if camera.model in {"OPENCV", "FULL_OPENCV"}:
        fx, fy, cx, cy = camera.params[:4]
        return fx, fy, cx, cy
    raise ValueError(f"Unsupported COLMAP camera model: {camera.model}")


def _distort_normalized(x: np.ndarray, y: np.ndarray, camera: Camera) -> tuple[np.ndarray, np.ndarray]:
    if camera.model in {"PINHOLE", "SIMPLE_PINHOLE"}:
        return x, y

    if camera.model == "SIMPLE_RADIAL":
        k1 = camera.params[3]
        radius_squared = x * x + y * y
        factor = 1.0 + k1 * radius_squared
        return x * factor, y * factor

    if camera.model in {"OPENCV", "FULL_OPENCV"}:
        k1, k2, p1, p2 = camera.params[4:8]
        radius_squared = x * x + y * y
        radial = 1.0 + k1 * radius_squared + k2 * radius_squared * radius_squared
        x_distorted = x * radial + 2.0 * p1 * x * y + p2 * (radius_squared + 2.0 * x * x)
        y_distorted = y * radial + p1 * (radius_squared + 2.0 * y * y) + 2.0 * p2 * x * y
        if camera.model == "FULL_OPENCV" and len(camera.params) >= 11:
            k3, k4, k5, k6 = camera.params[8:12]
            denominator = 1.0 + k4 * radius_squared + k5 * radius_squared**2 + k6 * radius_squared**3
            x_distorted = x_distorted / denominator + k3 * x * radius_squared**2
            y_distorted = y_distorted / denominator + k3 * y * radius_squared**2
        return x_distorted, y_distorted

    raise ValueError(f"Unsupported distortion model: {camera.model}")


def build_inverse_map(raw_camera: Camera, ideal_camera: Camera, output_width: int, output_height: int) -> tuple[np.ndarray, np.ndarray]:
    raw_fx, raw_fy, raw_cx, raw_cy = _intrinsics(raw_camera)
    ideal_fx, ideal_fy, ideal_cx, ideal_cy = _intrinsics(ideal_camera)

    grid_x, grid_y = np.meshgrid(
        np.arange(output_width, dtype=np.float32),
        np.arange(output_height, dtype=np.float32),
    )
    ideal_x = (grid_x - ideal_cx) / ideal_fx
    ideal_y = (grid_y - ideal_cy) / ideal_fy
    raw_x, raw_y = _distort_normalized(ideal_x, ideal_y, raw_camera)
    map_x = raw_fx * raw_x + raw_cx
    map_y = raw_fy * raw_y + raw_cy
    return map_x.astype(np.float32), map_y.astype(np.float32)


def frame_id_from_name(name: str) -> int | None:
    match = re.search(r"(\d+)(?:_obj_\d+)?$", Path(name).stem)
    return int(match.group(1)) if match else None


def find_raw_mask(raw_root: Path, relative_path: Path, frame_id: int | None, level: str) -> Path | None:
    direct = raw_root / relative_path
    if direct.is_file():
        return direct
    if frame_id is None:
        return None
    candidates = [
        raw_root / f"frame_{frame_id:05d}" / f"{level}.png",
        raw_root / f"frame_{frame_id:05d}_obj_001.png",
    ]
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def iter_mask_files(raw_root: Path, levels: tuple[str, ...]) -> list[tuple[Path, str]]:
    nested: list[tuple[Path, str]] = []
    for frame_dir in sorted(raw_root.glob("frame_*")):
        if not frame_dir.is_dir():
            continue
        for level in levels:
            path = frame_dir / f"{level}.png"
            if path.is_file():
                nested.append((path, level))
    if nested:
        return nested
    return [
        (path, "default")
        for path in sorted(raw_root.glob("frame_*_obj_001.png"))
        if path.is_file()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-masks-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--raw-sfm-txt", type=Path, required=True)
    parser.add_argument("--ideal-sfm-txt", type=Path, required=True)
    parser.add_argument("--raw-images-dir", type=Path, required=True)
    parser.add_argument("--ideal-images-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--levels", nargs="+", default=["default", "middle", "small"])
    args = parser.parse_args()

    raw_cameras = read_cameras(args.raw_sfm_txt / "cameras.txt")
    ideal_cameras = read_cameras(args.ideal_sfm_txt / "cameras.txt")
    image_camera_ids = read_image_camera_ids(args.raw_sfm_txt / "images.txt")
    ideal_image_camera_ids = read_image_camera_ids(args.ideal_sfm_txt / "images.txt")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    map_cache: dict[tuple[int, int, int, int], tuple[np.ndarray, np.ndarray]] = {}
    exported = 0
    empty = 0
    resolutions: set[tuple[int, int]] = set()
    records: list[dict[str, object]] = []

    for ideal_image_path in sorted(args.ideal_images_dir.iterdir()):
        if ideal_image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        image_name = ideal_image_path.name
        raw_camera_id = image_camera_ids.get(image_name)
        ideal_camera_id = ideal_image_camera_ids.get(image_name, raw_camera_id)
        if raw_camera_id not in raw_cameras or ideal_camera_id not in ideal_cameras:
            raise KeyError(f"No camera mapping for ideal image {image_name}")

        ideal_image = cv2.imread(str(ideal_image_path), cv2.IMREAD_GRAYSCALE)
        if ideal_image is None:
            raise ValueError(f"Could not read ideal image {ideal_image_path}")
        output_height, output_width = ideal_image.shape[:2]
        resolutions.add((output_width, output_height))
        cache_key = (raw_camera_id, ideal_camera_id, output_width, output_height)
        if cache_key not in map_cache:
            map_cache[cache_key] = build_inverse_map(
                raw_cameras[raw_camera_id], ideal_cameras[ideal_camera_id], output_width, output_height
            )

        frame_id = frame_id_from_name(image_name)
        image_records = 0
        for raw_mask_path, level in iter_mask_files(args.raw_masks_dir, tuple(args.levels)):
            raw_frame_id = frame_id_from_name(raw_mask_path.parent.name)
            if raw_frame_id is None:
                raw_frame_id = frame_id_from_name(raw_mask_path.name)
            if raw_frame_id != frame_id:
                continue
            raw_mask = cv2.imread(str(raw_mask_path), cv2.IMREAD_GRAYSCALE)
            if raw_mask is None:
                continue
            map_x, map_y = map_cache[cache_key]
            warped = cv2.remap(raw_mask, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            warped = np.where(warped > 0, 255, 0).astype(np.uint8)
            output_frame_dir = args.output_dir / f"frame_{frame_id:05d}"
            output_frame_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_frame_dir / f"{level}.png"
            cv2.imwrite(str(output_path), warped)
            nonempty = bool(np.count_nonzero(warped))
            empty += int(not nonempty)
            exported += 1
            image_records += 1
            records.append({
                "image": image_name,
                "frame_id": frame_id,
                "level": level,
                "output": str(output_path),
                "width": output_width,
                "height": output_height,
                "nonempty": nonempty,
                "area_fraction": float(np.count_nonzero(warped) / warped.size),
            })
        if image_records == 0:
            raise FileNotFoundError(f"No raw mask found for ideal image {image_name}")

    report = {
        "raw_masks_dir": str(args.raw_masks_dir),
        "output_dir": str(args.output_dir),
        "raw_camera_models": sorted({camera.model for camera in raw_cameras.values()}),
        "ideal_camera_models": sorted({camera.model for camera in ideal_cameras.values()}),
        "image_count": len({record["image"] for record in records}),
        "mask_count": exported,
        "empty_mask_count": empty,
        "resolutions": [{"width": width, "height": height} for width, height in sorted(resolutions)],
        "records": records,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("image_count", "mask_count", "empty_mask_count", "resolutions")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
