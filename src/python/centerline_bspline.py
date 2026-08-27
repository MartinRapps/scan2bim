import argparse
import math
from collections import OrderedDict

from centerline_io import read_centerline, write_centerline
from cli_utils import run_main


def keep_largest_components(paths, keep_top_components):
    if keep_top_components <= 0:
        return paths

    component_counts = {}
    for (_, component_id), points in paths.items():
        component_counts[component_id] = component_counts.get(component_id, 0) + len(points)

    ranked_components = sorted(
        component_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    keep_ids = {component_id for component_id, _ in ranked_components[:keep_top_components]}

    filtered = OrderedDict()
    for key, points in paths.items():
        if key[1] in keep_ids:
            filtered[key] = points

    if not filtered:
        raise ValueError(
            "Component filtering removed all branches. Lower --keep-top-components or disable it."
        )
    return filtered


def remove_consecutive_duplicates(points):
    unique = []
    for point in points:
        if not unique or any(abs(point[index] - unique[-1][index]) > 1e-12 for index in range(3)):
            unique.append(point)
    return unique


def linear_point(first, second, fraction):
    return [first[index] + (second[index] - first[index]) * fraction for index in range(3)]


def uniform_bspline_point(control_points, offset, degree, fraction):
    """Evaluate one segment of a clamped uniform B-spline of the given degree
    with the de Boor algorithm. With integer uniform knots the knot values
    cancel out, so only the local segment fraction enters the weights."""
    points = [list(control_points[offset + index]) for index in range(degree + 1)]
    for r in range(1, degree + 1):
        for j in range(degree, r - 1, -1):
            alpha = (degree + fraction - j) / (degree + 1.0 - r)
            points[j] = [
                (1.0 - alpha) * points[j - 1][axis] + alpha * points[j][axis]
                for axis in range(3)
            ]
    return points[degree]


def find_corners(points, window, min_angle_degrees):
    """Return indices of real direction changes. A sliding window suppresses
    the 45-degree staircase noise of voxel skeleton paths."""
    corners = []
    if len(points) < 2 * window + 1:
        return corners
    angles = []
    for index in range(window, len(points) - window):
        first = [points[index][axis] - points[index - window][axis] for axis in range(3)]
        second = [points[index + window][axis] - points[index][axis] for axis in range(3)]
        norm_first = math.sqrt(sum(component * component for component in first))
        norm_second = math.sqrt(sum(component * component for component in second))
        if norm_first < 1e-12 or norm_second < 1e-12:
            angles.append((index, 0.0))
            continue
        cosine = sum(first[axis] * second[axis] for axis in range(3)) / (norm_first * norm_second)
        cosine = max(-1.0, min(1.0, cosine))
        angles.append((index, math.degrees(math.acos(cosine))))
    for position, (index, angle) in enumerate(angles):
        if angle < min_angle_degrees:
            continue
        lower = max(0, position - window)
        upper = min(len(angles), position + window + 1)
        if not all(angle >= angles[other][1] for other in range(lower, upper)):
            continue
        if corners and index - corners[-1] <= window:
            continue
        corners.append(index)
    return corners


def segment_path(points, window, min_angle_degrees):
    """Split a path at its corners; corner points belong to both neighbours."""
    corners = find_corners(points, window, min_angle_degrees)
    if not corners:
        return [points]
    bounds = [0] + corners + [len(points) - 1]
    return [
        points[bounds[index]:bounds[index + 1] + 1]
        for index in range(len(bounds) - 1)
    ]


def bspline(points, samples_per_segment, degree):
    points = remove_consecutive_duplicates(points)
    if len(points) < 2:
        raise ValueError('Each centerline branch requires at least two distinct points')
    if len(points) <= degree:
        result = []
        for index in range(len(points) - 1):
            for sample in range(samples_per_segment):
                candidate = linear_point(
                    points[index], points[index + 1], sample / samples_per_segment
                )
                if not result or candidate != result[-1]:
                    result.append(candidate)
        result.append(points[-1])
        return result

    controls = [points[0]] * degree + points + [points[-1]] * degree
    result = [points[0]]
    for offset in range(len(controls) - degree):
        for sample in range(samples_per_segment):
            candidate = uniform_bspline_point(
                controls, offset, degree, sample / samples_per_segment
            )
            if not result or any(
                abs(candidate[axis] - result[-1][axis]) > 1e-12 for axis in range(3)
            ):
                result.append(candidate)
    result.append(points[-1])
    return result


def write_paths(output_csv, paths, samples_per_segment, segment_corners,
                corner_window, corner_min_angle, degree):
    output_paths = OrderedDict()
    next_branch_id = 0
    for (branch_id, component_id), points in paths.items():
        if segment_corners:
            segments = segment_path(points, corner_window, corner_min_angle)
        else:
            segments = [points]
        for segment in segments:
            if segment_corners:
                branch_id = str(next_branch_id)
                next_branch_id += 1
            smoothed = bspline(segment, samples_per_segment, degree)
            output_paths.setdefault((branch_id, component_id), []).extend(smoothed)
    total_points = write_centerline(output_csv, output_paths)
    if total_points < 2:
        raise IOError(f"B-spline output contains fewer than two points: {output_csv}")
    return next_branch_id if segment_corners else len(paths), total_points


def main():
    parser = argparse.ArgumentParser(
        description='Fit clamped uniform B-spline curves (degree >= 1) '
        'independently to centerline branches.'
    )
    parser.add_argument('--input_csv', required=True)
    parser.add_argument('--output_csv', required=True)
    parser.add_argument('--samples-per-segment', type=int, default=4)
    parser.add_argument('--degree', type=int, default=10,
                        help='B-spline degree; the current Alurohr default is 10')
    parser.add_argument('--keep-top-components', type=int, default=0)
    parser.add_argument('--segment-corners', action='store_true',
                        help='split each branch at real direction changes first')
    parser.add_argument('--corner-window', type=int, default=4,
                        help='sliding window size for corner detection')
    parser.add_argument('--corner-min-angle', type=float, default=30.0,
                        help='minimum direction change in degrees to count as a corner')
    args = parser.parse_args()
    if args.samples_per_segment < 1:
        parser.error('--samples-per-segment must be at least 1')
    if args.degree < 1:
        parser.error('--degree must be at least 1')
    if args.keep_top_components < 0:
        parser.error('--keep-top-components must be at least 0')
    if args.corner_window < 1:
        parser.error('--corner-window must be at least 1')
    if not 0.0 < args.corner_min_angle < 180.0:
        parser.error('--corner-min-angle must be between 0 and 180 degrees')

    paths = read_centerline(args.input_csv)
    paths = keep_largest_components(paths, args.keep_top_components)
    branch_count, point_count = write_paths(
        args.output_csv, paths, args.samples_per_segment,
        args.segment_corners, args.corner_window, args.corner_min_angle,
        args.degree)
    print(f"Wrote {branch_count} degree-{args.degree} B-spline branches and "
          f"{point_count} points to {args.output_csv}")


if __name__ == '__main__':
    run_main(main)
