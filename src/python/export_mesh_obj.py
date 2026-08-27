#!/usr/bin/env python3
"""Convert a triangle mesh PLY into an OBJ consumable by Container E."""

from __future__ import annotations

import argparse
from pathlib import Path

import open3d as o3d


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a triangle mesh PLY to a local OBJ mesh."
    )
    parser.add_argument("--input", type=Path, required=True, help="Input triangle mesh.")
    parser.add_argument("--output", type=Path, required=True, help="Output OBJ path.")
    args = parser.parse_args()

    if not args.input.is_file() or args.input.stat().st_size == 0:
        raise FileNotFoundError(f"Input mesh is missing or empty: {args.input}")

    mesh = o3d.io.read_triangle_mesh(str(args.input))
    if mesh.is_empty() or not mesh.has_vertices() or not mesh.has_triangles():
        raise ValueError(f"Input does not contain a non-empty triangle mesh: {args.input}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(
        str(args.output),
        mesh,
        write_vertex_normals=True,
        write_vertex_colors=mesh.has_vertex_colors(),
        write_triangle_uvs=False,
    ):
        raise RuntimeError(f"Open3D could not write OBJ: {args.output}")

    # DGtal and some importers are sensitive to an unterminated final OBJ line.
    with args.output.open("r+b") as handle:
        handle.seek(-1, 2)
        if handle.read(1) not in {b"\n", b"\r"}:
            handle.write(b"\n")

    print(
        f"OBJ written: {args.output} "
        f"({len(mesh.vertices)} vertices, {len(mesh.triangles)} triangles)"
    )


if __name__ == "__main__":
    main()
