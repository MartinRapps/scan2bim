from plyfile import PlyData, PlyElement
import numpy as np
import os
import argparse
import re
import torch


def _resolve_iteration_from_path(input_ply):
    match = re.search(r"iteration_(\d+)", input_ply)
    if match:
        return int(match.group(1))
    return None


def _id_pth_path(iteration, level):
    level_to_file = {
        "s": "small_object_id",
        "m": "middle_object_id",
        "l": "default_object_id",
    }
    base_name = level_to_file[level]
    return f"/data/05_3dgs/output/{base_name}_{iteration}.pth"

def main():
    parser = argparse.ArgumentParser(description="Filter background and optional quality defects from the Segment-then-Splat point cloud.")
    parser.add_argument("--input_ply", default="/data/05_3dgs/output/point_cloud/iteration_15000/point_cloud.ply", help="Path to raw Point Cloud from STS")
    parser.add_argument("--output_ply", default="/data/05_3dgs/output/point_cloud/iteration_15000/point_cloud_filtered.ply", help="Path to save filtered Point Cloud")
    parser.add_argument("--level", default="m", choices=["s", "m", "l"], help="Granularity level: s, m, l")
    parser.add_argument("--object_id", type=int, default=0, help="The target object ID to retain (default is 0 for single segment)")
    parser.add_argument("--min_opacity", type=float, default=0.0, help="Minimum sigmoid opacity threshold; 0 disables opacity-based rejection")
    parser.add_argument("--black_threshold", type=float, default=0.08, help="Threshold below which R, G, B are all considered too dark (black splats)")
    args = parser.parse_args()

    if not 0.0 <= args.min_opacity < 1.0:
        parser.error("--min_opacity must be in the interval [0, 1).")
    if not 0.0 <= args.black_threshold <= 1.0:
        parser.error("--black_threshold must be in the interval [0, 1].")

    if not os.path.exists(args.input_ply):
         # Try automatic resolve of point_cloud.ply if iteration was not 15000
         # i.e., scan directories inside iteration_*
         print(f"Specified point cloud path {args.input_ply} not found. Scanning automatically...")
         base_dir = "/data/05_3dgs/output/point_cloud"
         subdirs = sorted(os.listdir(base_dir)) if os.path.exists(base_dir) else []
         found_ply = None
         for subdir in reversed(subdirs):
             candidate = os.path.join(base_dir, subdir, "point_cloud.ply")
             if os.path.exists(candidate):
                 found_ply = candidate
                 args.input_ply = candidate
                 args.output_ply = os.path.join(base_dir, subdir, "point_cloud_filtered.ply")
                 break
         
         if not found_ply:
             print("Error: Could not find any point_cloud.ply in /data/05_3dgs/output/point_cloud/*")
             return

    print(f"Reading point cloud {args.input_ply}...")
    plydata = PlyData.read(args.input_ply)
    vertex_element = plydata['vertex']
    
    data_array = vertex_element.data
    prop_name = f"obj_id_{args.level}"
    labels = None

    label_source_name = prop_name
    if prop_name in [p.name for p in vertex_element.properties]:
        labels = data_array[prop_name]
        print(f"Using object IDs from PLY property '{prop_name}'.")
    else:
        print(f"Warning: Property {prop_name} not found in PLY. Trying STS object-id .pth files...")
        iteration = _resolve_iteration_from_path(args.input_ply)
        if iteration is None:
            print("Error: Could not infer iteration number from input_ply path.")
            return

        pth_path = _id_pth_path(iteration, args.level)
        if not os.path.exists(pth_path):
            print(f"Error: Expected STS object-id file not found: {pth_path}")
            return

        labels_tensor = torch.load(pth_path, map_location="cpu")
        labels = labels_tensor.numpy() if hasattr(labels_tensor, "numpy") else np.asarray(labels_tensor)

        if labels.shape[0] != len(data_array):
            print(
                f"Error: Label count mismatch. pth has {labels.shape[0]} entries, "
                f"but PLY has {len(data_array)} vertices."
            )
            return

        print(f"Using object IDs from {pth_path}.")
        label_source_name = os.path.basename(pth_path)

    # Inspect counts
    unique_vals, counts = np.unique(labels, return_counts=True)
    print(f"Point distribution for '{label_source_name}':")
    for val, count in zip(unique_vals, counts):
        print(f" - Value: {val}, Count: {count} points")

    # Filter out points
    print(f"Filtering points: retaining only those with value={args.object_id}...")
    mask = labels == args.object_id
    filtered_data = data_array[mask]
    
    if len(filtered_data) == 0:
        print(f"Warning: After filtering with requested object_id={args.object_id}, 0 points remain.")

        # STS commonly uses 255 for invalid/unassigned points.
        valid_ids = [int(v) for v in unique_vals.tolist() if int(v) != 255]
        if len(valid_ids) > 0:
            count_map = {int(v): int(c) for v, c in zip(unique_vals, counts)}
            best_id = max(valid_ids, key=lambda vid: count_map.get(vid, 0))
            print(
                f"Requested ID {args.object_id} not present. "
                f"Auto-selecting most frequent valid ID={best_id}."
            )
            mask = labels == best_id
            filtered_data = data_array[mask]
            print(f"Auto-selection retained {len(filtered_data)} points.")
        else:
            print("No valid object IDs found (all labels are 255). Writing original file instead.")
            filtered_data = data_array

    initial_filtered_count = len(filtered_data)
    print(f"Points after segment filter: {initial_filtered_count}")

    keep_mask = np.ones(len(filtered_data), dtype=bool)
    opacity_mask = np.ones(len(filtered_data), dtype=bool)
    black_mask = np.ones(len(filtered_data), dtype=bool)

    # 1. Opacity filtering
    if 'opacity' in filtered_data.dtype.names:
        op = np.asarray(filtered_data['opacity'])
        if args.min_opacity == 0.0:
            opacity_mask = np.ones(len(filtered_data), dtype=bool)
            print(" - Opacity filter disabled (min_opacity=0.0): retained all segment-specific points")
        else:
            sig_op = 1.0 / (1.0 + np.exp(-op))
            opacity_mask = sig_op >= args.min_opacity
            removed_opacity = np.count_nonzero(~opacity_mask)
            print(f" - Opacity filter (sigmoid_opacity >= {args.min_opacity}): removed {removed_opacity} points")
        keep_mask &= opacity_mask
    else:
        print(" - Opacity filter skipped: 'opacity' property not found in point cloud data")

    # 2. Black/dark point filtering (using Spherical Harmonics f_dc_0, f_dc_1, f_dc_2)
    if all(name in filtered_data.dtype.names for name in ['f_dc_0', 'f_dc_1', 'f_dc_2']):
        # Convert SH (f_dc_0, f_dc_1, f_dc_2) to linear RGB
        sh_dc = np.vstack([filtered_data['f_dc_0'], filtered_data['f_dc_1'], filtered_data['f_dc_2']]).T
        colors_rgb = 0.5 + sh_dc * 0.28209479177387814
        
        # Point is black if all channels are below threshold
        is_too_dark = (colors_rgb < args.black_threshold).all(axis=1)
        black_mask = ~is_too_dark
        keep_mask &= black_mask
        removed_black = np.count_nonzero(is_too_dark)
        print(f" - Black filter (RGB channels >= {args.black_threshold}): removed {removed_black} black/dark points")
    else:
        print(" - Black filter skipped: 'f_dc_0', 'f_dc_1', 'f_dc_2' properties not found in point cloud data")

    retained_after_opacity = np.count_nonzero(opacity_mask)
    retained_after_black = np.count_nonzero(black_mask)
    retained_after_both = np.count_nonzero(keep_mask)
    print(
        " - Retained by opacity / color / both: "
        f"{retained_after_opacity} / {retained_after_black} / {retained_after_both}"
    )

    if len(filtered_data[keep_mask]) == 0:
        print("Warning: Advanced quality filtering (opacity and black filters) would remove ALL points!")
        print("To prevent downstream crashes in meshing step (SuGaR), we skip advanced quality filters.")
        # Do not apply advanced filters
    else:
        filtered_data = filtered_data[keep_mask]
        print(f"Retained {len(filtered_data)} / {initial_filtered_count} segment-specific points after advanced quality filtering.")

    # Create new PlyData structure and write out
    new_vertex_element = PlyElement.describe(filtered_data, 'vertex')
    
    # Preserve other elements (such as face or normals if they exist)
    other_elements = [el for el in plydata.elements if el.name != 'vertex']
    
    new_elements = [new_vertex_element] + other_elements
    print(f"Writing filtered point cloud to {args.output_ply}...")
    PlyData(new_elements, text=plydata.text, byte_order=plydata.byte_order).write(args.output_ply)
    print("Filtered point cloud saved successfully.")

if __name__ == "__main__":
    main()
