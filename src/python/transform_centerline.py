import argparse
import math
import os
from collections import OrderedDict

from centerline_io import iter_points, write_centerline
from cli_utils import run_main


def load_matrix(matrix_path):
    """Load a 4x4 matrix written with commas or whitespace."""
    with open(matrix_path, 'r', encoding='utf-8') as matrix_file:
        values = []
        for line in matrix_file:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                values.extend(float(value) for value in stripped.replace(',', ' ').split())
    if len(values) != 16 or not all(math.isfinite(value) for value in values):
        raise ValueError(f"Matrix in {matrix_path} must contain exactly 16 finite values")
    matrix = [values[row * 4:(row + 1) * 4] for row in range(4)]
    if abs(matrix[3][3]) <= 1e-12 or any(abs(matrix[3][column]) > 1e-9 for column in range(3)):
        raise ValueError(f"Matrix in {matrix_path} is not an affine 4x4 transformation")
    return matrix

def load_anchor(anchor_path):
    """Load three finite anchor coordinates."""
    with open(anchor_path, 'r', encoding='utf-8') as anchor_file:
        parts = anchor_file.read().replace(',', ' ').split()
    if len(parts) != 3:
        raise ValueError(f"Anchor in {anchor_path} must contain exactly 3 coordinates")
    anchor = [float(part) for part in parts]
    if not all(math.isfinite(value) for value in anchor):
        raise ValueError(f"Anchor in {anchor_path} contains a non-finite coordinate")
    return anchor


def transform_point(point, matrix, anchor):
    homogeneous = point + [1.0]
    transformed = [sum(matrix[row][column] * homogeneous[column] for column in range(4))
                   for row in range(4)]
    if not math.isfinite(transformed[3]) or abs(transformed[3]) <= 1e-12:
        raise ValueError("Transformation produced an invalid homogeneous coordinate")
    if abs(transformed[3] - 1.0) > 1e-12:
        transformed = [value / transformed[3] for value in transformed]
    result = [transformed[index] + anchor[index] for index in range(3)]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("Transformation produced a non-finite global coordinate")
    return result


def main():
    parser = argparse.ArgumentParser(description="Transform local centerline coordinates to global UTM using 4x4 matrix and anchor.")
    parser.add_argument("--input_csv", default="/data/07_centerline/centerline_local.csv", help="Path to local centerline CSV")
    parser.add_argument("--matrix", default="/data/04_sfm/matrix.txt", help="Path to CloudCompare 4x4 matrix")
    parser.add_argument("--anchor_txt", default="/data/01_raw/anchor.txt", help="Path to anchor coordinates text file")
    parser.add_argument("--output_csv", default="/data/07_centerline/centerline_utm.csv", help="Path to output georeferenced CSV")

    args = parser.parse_args()

    required_paths = {
        'local centerline': args.input_csv,
        'transformation matrix': args.matrix,
        'anchor': args.anchor_txt,
    }
    missing = [label for label, path in required_paths.items() if not os.path.isfile(path)]
    if missing:
        raise FileNotFoundError('Missing ' + ', '.join(missing))

    points_local = list(iter_points(args.input_csv))
    if len(points_local) < 2:
        raise ValueError("Centerline must contain at least two points")
    matrix = load_matrix(args.matrix)
    anchor = load_anchor(args.anchor_txt)
    paths_global = OrderedDict()
    for branch_id, component_id, point in points_local:
        paths_global.setdefault((branch_id, component_id), []).append(
            transform_point(point, matrix, anchor)
        )
    total = write_centerline(args.output_csv, paths_global)
    if not os.path.isfile(args.output_csv) or os.path.getsize(args.output_csv) == 0:
        raise IOError(f"Georeferenced output was not written: {args.output_csv}")
    print(f"Successfully georeferenced {total} centerline points to {args.output_csv}")


if __name__ == '__main__':
    run_main(main)
