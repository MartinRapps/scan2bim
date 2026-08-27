import argparse
import math
import os
import sys
from collections import defaultdict, OrderedDict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "python"))
from centerline_io import read_centerline, write_centerline
from cli_utils import run_main


def parse_edges(input_csv):
    paths = read_centerline(input_csv)
    edges = {}
    for (branch_id_str, component_id), points in paths.items():
        branch_id = int(branch_id_str)
        if branch_id not in edges:
            edges[branch_id] = (component_id, [])
        edges[branch_id][1].extend(tuple(point) for point in points)
    return [(component_id, points) for component_id, points in edges.values()]


def polyline_length(points):
    return sum(
        math.dist(points[index], points[index + 1])
        for index in range(len(points) - 1)
    )


def build_incidence(edges):
    incidence = defaultdict(dict)
    for index, (_, points) in enumerate(edges):
        first, last = points[0], points[-1]
        incidence[first][index] = last
        incidence[last][index] = first
    return incidence


def prune_spurs(edges, min_length):
    """Iteratively drop branches that end at a degree-1 node and are shorter
    than min_length (skeleton noise twigs on tube surfaces)."""
    alive = set(range(len(edges)))
    incidence = build_incidence(edges)
    changed = True
    while changed:
        changed = False
        for node, neighbours in list(incidence.items()):
            live = {index: other for index, other in neighbours.items() if index in alive}
            if len(live) != 1:
                continue
            index = next(iter(live))
            if polyline_length(edges[index][1]) < min_length:
                alive.discard(index)
                changed = True
        incidence = build_incidence([edges[index] for index in sorted(alive)])
    return [edges[index] for index in sorted(alive)]


def cluster_junctions(edges, radius):
    """Union-find over junction nodes (degree >= 3); junctions closer than
    radius merge transitively into one super-node (collapses sheet blobs)."""
    incidence = build_incidence(edges)
    junctions = [node for node, neighbours in incidence.items() if len(neighbours) >= 3]
    parent = {node: node for node in junctions}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for first in range(len(junctions)):
        for second in range(first + 1, len(junctions)):
            if math.dist(junctions[first], junctions[second]) < radius:
                root_first, root_second = find(junctions[first]), find(junctions[second])
                if root_first != root_second:
                    parent[root_second] = root_first

    def label(node):
        if node in parent:
            return find(node)
        return node

    return label


def contract_degree2(edges, label):
    """Merge chains at degree-2 nodes (after junction clustering), keeping
    polylines oriented correctly. Self-loops are kept as closed branches."""
    contracted = {}
    for index, (component_id, points) in enumerate(edges):
        first, last = label(points[0]), label(points[-1])
        if first == last:
            continue  # intra-cluster edge: part of the junction blob
        contracted[index] = [first, last, component_id, points]

    incidence = defaultdict(set)
    for index, (first, last, _, _) in contracted.items():
        incidence[first].add(index)
        incidence[last].add(index)

    def orient(points, start_label, end_label):
        if label(points[0]) == start_label and label(points[-1]) == end_label:
            return points
        if label(points[0]) == end_label and label(points[-1]) == start_label:
            return points[::-1]
        raise ValueError('Edge endpoints do not match its node labels')

    changed = True
    while changed:
        changed = False
        for node in list(incidence.keys()):
            incident = sorted(incidence[node])
            if len(incident) != 2:
                continue
            first_index, second_index = incident
            first = contracted[first_index]
            second = contracted[second_index]
            other_first = first[1] if first[0] == node else first[0]
            other_second = second[1] if second[0] == node else second[0]
            if other_first == node or other_second == node:
                # self-loop touching the node: do not contract further
                continue
            if other_first == other_second:
                # two edges forming a closed ring: keep as closed branch
                incidence[node] = set()
                continue
            points_first = orient(first[3], other_first, node)
            points_second = orient(second[3], node, other_second)
            merged_points = points_first + points_second[1:]
            contracted[first_index] = [
                other_first, other_second, first[2], merged_points,
            ]
            incidence[other_first].discard(first_index)
            incidence[other_second].discard(second_index)
            incidence[other_first].add(first_index)
            incidence[other_second].add(first_index)
            del contracted[second_index]
            del incidence[node]
            changed = True
            break
    return [(component_id, points) for _, _, component_id, points in contracted.values()]


def write_edges(output_csv, edges):
    paths = OrderedDict()
    for branch_id, (component_id, points) in enumerate(edges):
        paths[(str(branch_id), component_id)] = [list(point) for point in points]
    total_points = write_centerline(output_csv, paths)
    if total_points < 2:
        raise IOError(f"Simplified centerline contains fewer than two points: {output_csv}")
    return total_points


def main():
    parser = argparse.ArgumentParser(
        description='Simplify a voxel skeleton graph: prune short spurs, '
        'cluster junction blobs, and merge degree-2 chains into structural branches.'
    )
    parser.add_argument('--input_csv', required=True)
    parser.add_argument('--output_csv', required=True)
    parser.add_argument('--min-path-length', type=float, default=0.75)
    parser.add_argument('--junction-cluster-radius', type=float, default=0.35)
    args = parser.parse_args()
    if args.min_path_length < 0:
        parser.error('--min-path-length must not be negative')
    if args.junction_cluster_radius < 0:
        parser.error('--junction-cluster-radius must not be negative')

    edges = parse_edges(args.input_csv)
    edges = prune_spurs(edges, args.min_path_length)
    label = cluster_junctions(edges, args.junction_cluster_radius)
    edges = contract_degree2(edges, label)
    edges = [
        (component_id, points)
        for component_id, points in edges
        if polyline_length(points) >= args.min_path_length
    ]
    point_count = write_edges(args.output_csv, edges)
    print(f"Wrote {len(edges)} simplified branches and {point_count} points to {args.output_csv}")


if __name__ == '__main__':
    run_main(main)
