"""Shared I/O for centerline CSV files.

Canonical schema: a header row ``branch_id,component_id,x,y,z`` followed by
data rows.  The reader additionally accepts headerless files whose first three
columns are ``x, y, z``; ``branch_id``/``component_id`` then default to ``'0'``.
This consolidates the four previously duplicated parsers in
``transform_centerline.py``, ``centerline_bspline.py``,
``centerline_geojson.py`` and ``centerline_graph_simplify.py``.
"""

import csv
import math
import os
from collections import OrderedDict
from typing import Iterator, List, Tuple

Point = List[float]
BranchKey = Tuple[str, str]
PathMap = "OrderedDict[BranchKey, List[Point]]"

_REQUIRED_AXES = ("x", "y", "z")


def _is_finite_point(point: Point) -> bool:
    return all(math.isfinite(value) for value in point)


def read_centerline(input_csv: str) -> PathMap:
    """Read a centerline CSV into an ordered map ``{(branch_id, component_id): [[x,y,z], ...]}``.

    Accepts a header row (column names x/y/z, optionally branch_id/component_id)
    or a headerless file where the first three columns are x, y, z.  Empty
    branch_id/component_id cells normalize to ``'0'``.  Raises ``ValueError`` on
    empty or malformed input.
    """
    with open(input_csv, "r", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError(f"Centerline CSV {input_csv} is empty")

    header = [cell.strip().lower() for cell in rows[0]]
    if all(axis in header for axis in _REQUIRED_AXES):
        x_idx, y_idx, z_idx = (header.index(axis) for axis in _REQUIRED_AXES)
        branch_idx = header.index("branch_id") if "branch_id" in header else None
        component_idx = header.index("component_id") if "component_id" in header else None
        data_rows = rows[1:]
    else:
        x_idx, y_idx, z_idx = 0, 1, 2
        branch_idx = None
        component_idx = None
        data_rows = rows

    paths: "OrderedDict[BranchKey, List[Point]]" = OrderedDict()
    for row in data_rows:
        if len(row) <= max(x_idx, y_idx, z_idx):
            raise ValueError(f"Centerline CSV row has fewer than three coordinates: {row}")
        point = [float(row[x_idx]), float(row[y_idx]), float(row[z_idx])]
        if not _is_finite_point(point):
            raise ValueError("Centerline CSV contains a non-finite coordinate")
        branch_id = (row[branch_idx].strip() or "0") if branch_idx is not None else "0"
        component_id = (row[component_idx].strip() or "0") if component_idx is not None else "0"
        paths.setdefault((branch_id, component_id), []).append(point)
    if not paths:
        raise ValueError(f"Centerline CSV {input_csv} contains no points")
    return paths


def iter_points(input_csv: str) -> Iterator[Tuple[str, str, Point]]:
    """Yield ``(branch_id, component_id, [x,y,z])`` tuples in file order."""
    for (branch_id, component_id), points in read_centerline(input_csv).items():
        for point in points:
            yield branch_id, component_id, point


def write_centerline(output_csv: str, paths: PathMap) -> int:
    """Write the canonical ``branch_id,component_id,x,y,z`` CSV. Returns point count."""
    output_directory = os.path.dirname(output_csv)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)
    total = 0
    with open(output_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["branch_id", "component_id", "x", "y", "z"])
        for (branch_id, component_id), points in paths.items():
            for point in points:
                writer.writerow([branch_id, component_id, *point])
                total += 1
    return total
