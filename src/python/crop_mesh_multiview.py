#!/usr/bin/env python3
"""Semantically crop a mesh by multi-view mask consensus.

The script uses the registered SuGaR/COLMAP cameras in ``cameras.json`` and
binary masks with matching frame names.  For every camera, Open3D ray casting
generates an occlusion-aware face-ID image.  A triangle is retained only when
enough visible views support it as part of the segmented object.

The default is deliberately conservative: faces that have not been sampled in
enough views are retained rather than destructively removed.  Increase
``--render-scale`` for a denser final pass, or use ``--remove-underobserved``
only after inspecting a conservative result.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import open3d as o3d

from mask_paths import load_mask


@dataclass(frozen=True)
class Camera:
    """Camera parameters in the SuGaR ``cameras.json`` convention."""

    image_name: str
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    world_to_camera_rotation: np.ndarray
    world_to_camera_translation: np.ndarray

    @property
    def center(self) -> np.ndarray:
        """Return the camera center in world coordinates."""

        return -(self.world_to_camera_rotation.T @ self.world_to_camera_translation)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Crop a SuGaR mesh with an occlusion-aware consensus over all "
            "registered semantic masks."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input-mesh", type=Path, required=True, help="Input PLY or OBJ mesh")
    parser.add_argument(
        "--output-mesh",
        type=Path,
        required=True,
        help="Cropped PLY or OBJ mesh. OBJ output preserves the original UV faces and texture assets.",
    )
    parser.add_argument(
        "--cameras-json",
        type=Path,
        default=Path("/data/05_3dgs/output/cameras.json"),
        help="SuGaR/3DGS camera metadata",
    )
    parser.add_argument(
        "--masks-dir",
        type=Path,
        default=Path("/data/03_masks"),
        help="Root of hierarchical masks or an STS multiview-mask directory",
    )
    parser.add_argument(
        "--mask-level",
        choices=("default", "middle", "small"),
        default="default",
        help="Hierarchical mask level; default preserves thin glasses parts best",
    )
    parser.add_argument(
        "--mask-dilation-px",
        type=int,
        default=2,
        help="Dilate each source mask before sampling to tolerate silhouette uncertainty",
    )
    parser.add_argument(
        "--render-scale",
        type=float,
        default=0.25,
        help="Raycast resolution relative to the source image; use 0.5 for a denser final pass",
    )
    parser.add_argument(
        "--min-visible-views",
        type=int,
        default=3,
        help="Minimum reliable camera observations before a triangle can be removed",
    )
    parser.add_argument(
        "--min-visible-pixels",
        type=int,
        default=2,
        help="Minimum sampled pixels for a face to count as a view observation",
    )
    parser.add_argument(
        "--min-view-mask-fraction",
        type=float,
        default=0.5,
        help="Foreground pixel fraction required for one camera to support a face",
    )
    parser.add_argument(
        "--min-support-ratio",
        type=float,
        default=0.6,
        help="Fraction of valid camera views that must support a face",
    )
    parser.add_argument(
        "--camera-stride",
        type=int,
        default=1,
        help="Use every Nth camera after sorting by image name",
    )
    parser.add_argument(
        "--max-cameras",
        type=int,
        default=None,
        help="Optional cap after camera stride; useful for a fast dry run",
    )
    parser.add_argument(
        "--remove-underobserved",
        action="store_true",
        help="Also remove faces with fewer than --min-visible-views observations (destructive)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="JSON summary path; defaults next to --output-mesh",
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute votes and write only the report")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing output mesh")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not args.input_mesh.is_file():
        raise FileNotFoundError(f"Input mesh does not exist: {args.input_mesh}")
    if not args.cameras_json.is_file():
        raise FileNotFoundError(f"Camera metadata does not exist: {args.cameras_json}")
    if not args.masks_dir.is_dir():
        raise FileNotFoundError(f"Mask directory does not exist: {args.masks_dir}")
    if not 0.0 < args.render_scale <= 1.0:
        raise ValueError("--render-scale must be in the interval (0, 1]")
    if args.mask_dilation_px < 0:
        raise ValueError("--mask-dilation-px must not be negative")
    if args.min_visible_views < 1 or args.min_visible_pixels < 1:
        raise ValueError("Minimum view and pixel counts must be at least one")
    if args.camera_stride < 1:
        raise ValueError("--camera-stride must be at least one")
    for value, option in (
        (args.min_view_mask_fraction, "--min-view-mask-fraction"),
        (args.min_support_ratio, "--min-support-ratio"),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{option} must be in the interval [0, 1]")
    if args.max_cameras is not None and args.max_cameras < 1:
        raise ValueError("--max-cameras must be positive when supplied")
    if args.output_mesh.exists() and not args.overwrite and not args.dry_run:
        raise FileExistsError(
            f"Output already exists: {args.output_mesh}. Use --overwrite to replace it."
        )


def _camera_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        frames = payload.get("frames")
        if isinstance(frames, list):
            return frames
    raise ValueError("cameras.json must contain a list or an object with a 'frames' list")


def load_cameras(path: Path) -> list[Camera]:
    with path.open("r", encoding="utf-8") as handle:
        records = _camera_records(json.load(handle))

    cameras: list[Camera] = []
    seen_names: set[str] = set()
    for index, record in enumerate(records):
        raw_name = record.get("img_name") or record.get("image_name") or record.get("file_path")
        if raw_name is None:
            raise ValueError(f"Camera entry {index} has no image name")
        image_name = Path(str(raw_name)).stem
        if image_name in seen_names:
            raise ValueError(f"Duplicate camera image name in metadata: {image_name}")
        seen_names.add(image_name)

        try:
            width = int(record["width"])
            height = int(record["height"])
            fx = float(record["fx"])
            fy = float(record["fy"])
            rotation = np.asarray(record["rotation"], dtype=np.float64)
            translation = np.asarray(record["position"], dtype=np.float64)
        except KeyError as exc:
            raise ValueError(f"Camera entry {index} misses required key {exc.args[0]!r}") from exc

        if width < 1 or height < 1 or fx <= 0.0 or fy <= 0.0:
            raise ValueError(f"Camera entry {index} has invalid intrinsics")
        if rotation.shape != (3, 3) or translation.shape != (3,):
            raise ValueError(
                f"Camera entry {index} must contain a 3x3 rotation and a length-3 position"
            )

        cameras.append(
            Camera(
                image_name=image_name,
                width=width,
                height=height,
                fx=fx,
                fy=fy,
                cx=float(record.get("cx", width / 2.0)),
                cy=float(record.get("cy", height / 2.0)),
                world_to_camera_rotation=rotation,
                world_to_camera_translation=translation,
            )
        )

    return sorted(cameras, key=lambda camera: camera.image_name)


def build_rays_and_mask_samples(
    camera: Camera,
    mask: np.ndarray,
    render_scale: float,
) -> tuple[o3d.core.Tensor, np.ndarray]:
    """Create world-space rays and aligned mask samples for one camera."""

    render_width = max(1, int(round(camera.width * render_scale)))
    render_height = max(1, int(round(camera.height * render_scale)))
    pixel_x = (np.arange(render_width, dtype=np.float64) + 0.5) * camera.width / render_width
    pixel_y = (np.arange(render_height, dtype=np.float64) + 0.5) * camera.height / render_height
    grid_x, grid_y = np.meshgrid(pixel_x, pixel_y, indexing="xy")

    directions_camera = np.stack(
        (
            (grid_x - camera.cx) / camera.fx,
            (grid_y - camera.cy) / camera.fy,
            np.ones_like(grid_x),
        ),
        axis=-1,
    ).reshape(-1, 3)
    directions_world = directions_camera @ camera.world_to_camera_rotation
    origins = np.broadcast_to(camera.center, directions_world.shape)
    rays = np.ascontiguousarray(np.concatenate((origins, directions_world), axis=1), dtype=np.float32)

    mask_height, mask_width = mask.shape
    mask_x = np.clip((grid_x * mask_width / camera.width).astype(np.int64), 0, mask_width - 1)
    mask_y = np.clip((grid_y * mask_height / camera.height).astype(np.int64), 0, mask_height - 1)
    mask_samples = np.ascontiguousarray(mask[mask_y, mask_x].reshape(-1))
    return o3d.core.Tensor(rays), mask_samples


def accumulate_face_votes(
    primitive_ids: np.ndarray,
    mask_samples: np.ndarray,
    visible_pixel_counts: np.ndarray,
    supported_pixel_counts: np.ndarray,
    visible_view_counts: np.ndarray,
    supported_view_counts: np.ndarray,
    min_visible_pixels: int,
    min_view_mask_fraction: float,
) -> tuple[int, int]:
    """Add one camera's face-ID and mask observations to global vote arrays."""

    invalid_id = np.iinfo(primitive_ids.dtype).max
    hit_mask = primitive_ids != invalid_id
    if not np.any(hit_mask):
        return 0, 0

    hit_ids = primitive_ids[hit_mask].astype(np.int64, copy=False)
    face_ids, inverse, per_face_pixels = np.unique(hit_ids, return_inverse=True, return_counts=True)
    np.add.at(visible_pixel_counts, face_ids, per_face_pixels)

    foreground_mask = mask_samples[hit_mask]
    foreground_ids = hit_ids[foreground_mask]
    foreground_per_face = np.zeros(face_ids.shape[0], dtype=np.int64)
    if foreground_ids.size:
        foreground_face_ids, foreground_counts = np.unique(foreground_ids, return_counts=True)
        foreground_positions = np.searchsorted(face_ids, foreground_face_ids)
        foreground_per_face[foreground_positions] = foreground_counts
        np.add.at(supported_pixel_counts, foreground_face_ids, foreground_counts)

    sufficiently_sampled = per_face_pixels >= min_visible_pixels
    observed_faces = face_ids[sufficiently_sampled]
    visible_view_counts[observed_faces] += 1

    per_face_fraction = foreground_per_face / per_face_pixels
    supported_faces = face_ids[
        sufficiently_sampled & (per_face_fraction >= min_view_mask_fraction)
    ]
    supported_view_counts[supported_faces] += 1
    return int(hit_ids.size), int(foreground_ids.size)


def mesh_from_path(path: Path) -> o3d.geometry.TriangleMesh:
    """Load geometry while working around Open3D's unterminated-OBJ edge case."""

    normalized_path: Path | None = None
    if path.suffix.lower() == ".obj" and path.stat().st_size > 0:
        with path.open("rb") as source:
            source.seek(-1, 2)
            has_terminal_newline = source.read(1) in {b"\n", b"\r"}
        if not has_terminal_newline:
            # Open3D/Assimp can silently omit an otherwise valid final face when
            # the OBJ does not end in a newline. Keep the original mesh immutable
            # and normalize only a temporary geometry-loading copy.
            with tempfile.NamedTemporaryFile(
                suffix=".obj", dir=path.parent, delete=False
            ) as temporary:
                normalized_path = Path(temporary.name)
                with path.open("rb") as source:
                    shutil.copyfileobj(source, temporary)
                temporary.write(b"\n")
            print(
                "Warning: input OBJ had no terminal newline; using a temporary "
                "normalized copy for ray casting."
            )

    try:
        mesh = o3d.io.read_triangle_mesh(str(normalized_path or path))
    finally:
        if normalized_path is not None:
            normalized_path.unlink(missing_ok=True)
    if mesh.is_empty():
        raise ValueError(f"Could not load a non-empty triangle mesh from {path}")
    if not mesh.has_triangles() or not mesh.has_vertices():
        raise ValueError(f"Input does not contain triangle geometry: {path}")
    return mesh


def copy_obj_material_assets(source_obj: Path, output_dir: Path) -> list[str]:
    """Copy MTL files and their simple map references beside a filtered OBJ."""

    copied: list[str] = []
    material_files: list[Path] = []
    with source_obj.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0] == "mtllib":
                material_files.append(source_obj.parent / parts[1])

    for material_path in material_files:
        if not material_path.is_file():
            print(f"Warning: referenced material file is missing: {material_path}", file=sys.stderr)
            continue
        destination = output_dir / material_path.name
        if material_path.resolve() != destination.resolve():
            shutil.copy2(material_path, destination)
        copied.append(str(destination))

        with material_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.strip().split()
                if len(parts) < 2 or not parts[0].lower().startswith("map_"):
                    continue
                texture_path = material_path.parent / parts[-1]
                if not texture_path.is_file():
                    continue
                texture_destination = output_dir / texture_path.name
                if texture_path.resolve() != texture_destination.resolve():
                    shutil.copy2(texture_path, texture_destination)
                copied.append(str(texture_destination))
    return copied


def _resolve_obj_index(raw_index: str, count: int, kind: str, line_number: int) -> int:
    """Resolve a positive or relative OBJ index to its one-based absolute form."""

    try:
        index = int(raw_index)
    except ValueError as error:
        raise ValueError(f"Invalid {kind} index on OBJ line {line_number}: {raw_index!r}") from error
    if index == 0:
        raise ValueError(f"OBJ {kind} index must not be zero on line {line_number}")
    index = index if index > 0 else count + index + 1
    if not 1 <= index <= count:
        raise ValueError(f"OBJ {kind} index is out of range on line {line_number}: {raw_index!r}")
    return index


def write_filtered_obj(source_obj: Path, destination: Path, keep_faces: np.ndarray) -> list[str]:
    """Write a compact textured OBJ with remapped vertex and UV indices.

    Filtering only ``f`` records leaves every original vertex and UV entry in
    the file.  SuGaR assigns nearly unique UVs per triangle, so that approach
    barely reduces file size even when most faces are removed.  This writer
    keeps only geometry referenced by retained faces while preserving the atlas
    and material directives.
    """

    vertices = [""]
    texture_coordinates = [""]
    normals = [""]
    directives: list[str] = []
    faces: list[tuple[int, list[str]]] = []

    with source_obj.open("r", encoding="utf-8", errors="replace") as source:
        for line_number, line in enumerate(source, start=1):
            normalized_line = line if line.endswith(("\n", "\r")) else f"{line}\n"
            if line.startswith("v "):
                vertices.append(normalized_line)
            elif line.startswith("vt "):
                texture_coordinates.append(normalized_line)
            elif line.startswith("vn "):
                normals.append(normalized_line)
            elif line.startswith("f "):
                tokens = line.split()[1:]
                if len(tokens) != 3:
                    raise ValueError(
                        f"Only triangular OBJ faces are supported (line {line_number})."
                    )
                faces.append((line_number, tokens))
            else:
                directives.append(normalized_line)

    if len(faces) != len(keep_faces):
        raise ValueError(
            "OBJ face records do not match Open3D triangle ordering "
            f"({len(faces)} OBJ faces versus {len(keep_faces)} triangles). "
            "Write a .ply output instead."
        )

    selected_faces = [face for face, keep in zip(faces, keep_faces) if keep]
    used_vertices: set[int] = set()
    used_texture_coordinates: set[int] = set()
    used_normals: set[int] = set()
    parsed_faces: list[tuple[int, list[tuple[int, int | None, int | None]]]] = []

    for line_number, tokens in selected_faces:
        parsed_face: list[tuple[int, int | None, int | None]] = []
        for token in tokens:
            fields = token.split("/")
            vertex_index = _resolve_obj_index(fields[0], len(vertices) - 1, "vertex", line_number)
            texture_index = None
            normal_index = None
            if len(fields) > 1 and fields[1]:
                texture_index = _resolve_obj_index(
                    fields[1], len(texture_coordinates) - 1, "texture", line_number
                )
            if len(fields) > 2 and fields[2]:
                normal_index = _resolve_obj_index(fields[2], len(normals) - 1, "normal", line_number)
            if len(fields) > 3:
                raise ValueError(f"Invalid OBJ face record on line {line_number}: {token!r}")
            used_vertices.add(vertex_index)
            if texture_index is not None:
                used_texture_coordinates.add(texture_index)
            if normal_index is not None:
                used_normals.add(normal_index)
            parsed_face.append((vertex_index, texture_index, normal_index))
        parsed_faces.append((line_number, parsed_face))

    vertex_map = {old: new for new, old in enumerate(sorted(used_vertices), start=1)}
    texture_map = {
        old: new for new, old in enumerate(sorted(used_texture_coordinates), start=1)
    }
    normal_map = {old: new for new, old in enumerate(sorted(used_normals), start=1)}

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as output:
        output.writelines(directives)
        output.writelines(vertices[index] for index in sorted(used_vertices))
        output.writelines(texture_coordinates[index] for index in sorted(used_texture_coordinates))
        output.writelines(normals[index] for index in sorted(used_normals))
        for _, face in parsed_faces:
            face_tokens: list[str] = []
            for vertex_index, texture_index, normal_index in face:
                token = str(vertex_map[vertex_index])
                if texture_index is not None or normal_index is not None:
                    token += "/"
                    if texture_index is not None:
                        token += str(texture_map[texture_index])
                    if normal_index is not None:
                        token += f"/{normal_map[normal_index]}"
                face_tokens.append(token)
            output.write(f"f {' '.join(face_tokens)}\n")
    return copy_obj_material_assets(source_obj, destination.parent)


def write_filtered_ply(
    source_mesh: o3d.geometry.TriangleMesh,
    destination: Path,
    keep_faces: np.ndarray,
) -> None:
    """Write a compact geometry-only PLY containing retained triangles."""

    filtered_mesh = o3d.geometry.TriangleMesh(source_mesh)
    filtered_mesh.remove_triangles_by_mask(~keep_faces)
    filtered_mesh.remove_unreferenced_vertices()
    filtered_mesh.remove_degenerate_triangles()
    if not filtered_mesh.has_vertex_normals():
        filtered_mesh.compute_vertex_normals()

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(
        str(destination),
        filtered_mesh,
        write_ascii=False,
        compressed=True,
        write_vertex_normals=True,
        write_vertex_colors=True,
    ):
        raise RuntimeError(f"Failed to write cropped PLY: {destination}")


def default_report_path(output_mesh: Path) -> Path:
    return output_mesh.with_name(f"{output_mesh.stem}_consensus_report.json")


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    args = parse_args()
    validate_args(args)
    started_at = time.monotonic()

    mesh = mesh_from_path(args.input_mesh)
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    n_faces = len(triangles)
    if n_faces == 0:
        raise ValueError("Input mesh has no faces")

    cameras = load_cameras(args.cameras_json)
    selected_cameras = cameras[:: args.camera_stride]
    if args.max_cameras is not None:
        selected_cameras = selected_cameras[: args.max_cameras]
    if not selected_cameras:
        raise ValueError("No cameras selected")

    print("=== Multi-view semantic mesh crop ===")
    print(f"Input mesh: {args.input_mesh}")
    print(f"Mesh: {len(vertices):,} vertices, {n_faces:,} triangles")
    print(f"Cameras: {len(selected_cameras):,} selected of {len(cameras):,}")
    print(
        "Voting: "
        f"{args.min_visible_views} visible views, "
        f"{args.min_support_ratio:.0%} consensus, "
        f"render scale {args.render_scale:g}"
    )

    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(
        o3d.core.Tensor(np.ascontiguousarray(vertices, dtype=np.float32)),
        o3d.core.Tensor(np.ascontiguousarray(triangles, dtype=np.uint32)),
    )

    visible_pixel_counts = np.zeros(n_faces, dtype=np.uint64)
    supported_pixel_counts = np.zeros(n_faces, dtype=np.uint64)
    visible_view_counts = np.zeros(n_faces, dtype=np.uint16)
    supported_view_counts = np.zeros(n_faces, dtype=np.uint16)

    missing_masks: list[str] = []
    empty_masks: list[str] = []
    used_masks: list[dict[str, str]] = []
    resolution_mismatches: list[str] = []
    total_hit_pixels = 0
    total_supported_pixels = 0

    for camera_index, camera in enumerate(selected_cameras, start=1):
        mask, mask_path = load_mask(
            masks_dir=args.masks_dir,
            image_name=camera.image_name,
            level=args.mask_level,
            dilation_px=args.mask_dilation_px,
        )
        if mask is None or mask_path is None:
            missing_masks.append(camera.image_name)
            continue
        if not np.any(mask):
            empty_masks.append(camera.image_name)
            continue
        if mask.shape != (camera.height, camera.width):
            resolution_mismatches.append(
                f"{camera.image_name}: camera={camera.width}x{camera.height}, "
                f"mask={mask.shape[1]}x{mask.shape[0]}"
            )

        rays, mask_samples = build_rays_and_mask_samples(camera, mask, args.render_scale)
        raycast_result = scene.cast_rays(rays)
        primitive_ids = raycast_result["primitive_ids"].numpy().reshape(-1)
        hit_pixels, supported_pixels = accumulate_face_votes(
            primitive_ids=primitive_ids,
            mask_samples=mask_samples,
            visible_pixel_counts=visible_pixel_counts,
            supported_pixel_counts=supported_pixel_counts,
            visible_view_counts=visible_view_counts,
            supported_view_counts=supported_view_counts,
            min_visible_pixels=args.min_visible_pixels,
            min_view_mask_fraction=args.min_view_mask_fraction,
        )
        total_hit_pixels += hit_pixels
        total_supported_pixels += supported_pixels
        used_masks.append({"image_name": camera.image_name, "mask": str(mask_path)})

        if camera_index == 1 or camera_index % 25 == 0 or camera_index == len(selected_cameras):
            print(
                f"Processed camera {camera_index}/{len(selected_cameras)}: "
                f"{camera.image_name} ({hit_pixels:,} mesh hits, {supported_pixels:,} mask hits)"
            )

    if len(used_masks) < args.min_visible_views:
        raise RuntimeError(
            f"Only {len(used_masks)} usable masks were found; at least "
            f"{args.min_visible_views} are required for the requested consensus."
        )

    observed = visible_view_counts >= args.min_visible_views
    support_ratio = np.divide(
        supported_view_counts,
        visible_view_counts,
        out=np.zeros(n_faces, dtype=np.float64),
        where=visible_view_counts > 0,
    )
    supported = observed & (support_ratio >= args.min_support_ratio)
    keep_faces = supported.copy()
    if not args.remove_underobserved:
        keep_faces |= ~observed

    if not np.any(keep_faces):
        raise RuntimeError("Consensus would remove every face; verify camera and mask alignment.")

    observed_ratios = support_ratio[observed]
    report_path = args.report or default_report_path(args.output_mesh)
    report: dict[str, Any] = {
        "input_mesh": str(args.input_mesh),
        "output_mesh": str(args.output_mesh),
        "cameras_json": str(args.cameras_json),
        "masks_dir": str(args.masks_dir),
        "mask_level": args.mask_level,
        "mask_dilation_px": args.mask_dilation_px,
        "render_scale": args.render_scale,
        "camera_count": {
            "available": len(cameras),
            "selected": len(selected_cameras),
            "usable": len(used_masks),
            "missing_mask": len(missing_masks),
            "empty_mask": len(empty_masks),
        },
        "thresholds": {
            "min_visible_views": args.min_visible_views,
            "min_visible_pixels": args.min_visible_pixels,
            "min_view_mask_fraction": args.min_view_mask_fraction,
            "min_support_ratio": args.min_support_ratio,
            "remove_underobserved": args.remove_underobserved,
        },
        "faces": {
            "total": int(n_faces),
            "observed": int(observed.sum()),
            "supported_by_consensus": int(supported.sum()),
            "kept_underobserved": int((keep_faces & ~observed).sum()),
            "kept": int(keep_faces.sum()),
            "removed": int((~keep_faces).sum()),
        },
        "raycast_pixels": {
            "mesh_hits": int(total_hit_pixels),
            "mask_hits": int(total_supported_pixels),
        },
        "observed_face_support_ratio": {
            "min": float(observed_ratios.min()) if observed_ratios.size else None,
            "median": float(np.median(observed_ratios)) if observed_ratios.size else None,
            "max": float(observed_ratios.max()) if observed_ratios.size else None,
        },
        "missing_masks": missing_masks,
        "empty_masks": empty_masks,
        "resolution_mismatches": resolution_mismatches,
        "used_masks": used_masks,
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
        "dry_run": args.dry_run,
    }

    copied_assets: list[str] = []
    if not args.dry_run:
        input_suffix = args.input_mesh.suffix.lower()
        output_suffix = args.output_mesh.suffix.lower()
        if output_suffix == ".obj":
            if input_suffix != ".obj":
                raise ValueError("Textured OBJ output requires an OBJ input; use a .ply output otherwise.")
            copied_assets = write_filtered_obj(args.input_mesh, args.output_mesh, keep_faces)
        elif output_suffix == ".ply":
            write_filtered_ply(mesh, args.output_mesh, keep_faces)
        else:
            raise ValueError("--output-mesh must end in .obj or .ply")
        report["copied_assets"] = copied_assets

    report["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
    write_report(report_path, report)

    print("--- Result ---")
    print(f"Consensus-supported faces: {supported.sum():,}")
    print(f"Kept under-observed faces: {(keep_faces & ~observed).sum():,}")
    print(f"Removed faces: {(~keep_faces).sum():,} / {n_faces:,}")
    if missing_masks:
        print(f"Warning: {len(missing_masks)} selected cameras had no matching mask.", file=sys.stderr)
    if empty_masks:
        print(f"Warning: {len(empty_masks)} selected cameras had an empty mask and were skipped.", file=sys.stderr)
    if resolution_mismatches:
        print(
            f"Warning: {len(resolution_mismatches)} masks were sampled after coordinate scaling; "
            "inspect the report.",
            file=sys.stderr,
        )
    if args.dry_run:
        print("Dry run complete; no mesh was written.")
    else:
        print(f"Cropped mesh: {args.output_mesh}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2) from error