import argparse
from sugar_utils.general_utils import str2bool
from sugar_extractors.coarse_mesh import extract_mesh_from_coarse_sugar

if __name__ == "__main__":
    # Parser
    parser = argparse.ArgumentParser(description='Script to extract a mesh from a coarse SuGaR scene.')
    parser.add_argument('-s', '--scene_path',
                        type=str, 
                        help='path to the scene data to use.')
    parser.add_argument('-c', '--checkpoint_path', 
                        type=str, 
                        help='path to the vanilla 3D Gaussian Splatting Checkpoint to load.')
    parser.add_argument('-i', '--iteration_to_load', 
                        type=int, default=7000, 
                        help='iteration to load.')
    
    parser.add_argument('-m', '--coarse_model_path', type=str, default=None, help='')
    
    parser.add_argument('-l', '--surface_level', type=float, default=None, 
                        help='Surface level to extract the mesh at. If None, will extract levels 0.1, 0.3 and 0.5')
    parser.add_argument('-d', '--decimation_target', type=int, default=None, 
                        help='Target number of vertices to decimate the mesh to. If None, will decimate to 200_000 and 1_000_000.')
    parser.add_argument('--project_mesh_on_surface_points', type=str2bool, default=True, 
                        help='If True, project decimated vertices to their nearest sampled surface points.')
    parser.add_argument('--surface-sample-count', type=int, default=10_000_000,
                        help='Total camera-derived surface samples before Poisson reconstruction.')
    parser.add_argument('--poisson-depth', type=int, default=10,
                        help='Poisson octree depth; higher values retain finer detail and cost more memory/time.')
    parser.add_argument('--vertices-density-quantile', type=float, default=0.1,
                        help='Remove mesh vertices below this Poisson-density quantile; use 0 to disable.')
    parser.add_argument('--low-opacity-gaussian-threshold', type=float, default=0.5,
                        help='Discard coarse Gaussians with sigmoid opacity at or below this value before surface sampling.')
    parser.add_argument('--surface-sample-seed', type=int, default=None,
                        help='Optional seed for reproducible camera-based surface sampling.')
    parser.add_argument('--include-background-mesh', type=str2bool, default=True,
                        help='Include the separately reconstructed background mesh in the exported mesh.')
    parser.add_argument('--use-gaussian-depth', type=str2bool, default=False,
                        help='Use the Gaussian rasterizer depth directly instead of the projected diamond-mesh z-buffer.')
    
    parser.add_argument('-o', '--mesh_output_dir',
                        type=str, default=None, 
                        help='path to the output directory.')
    
    parser.add_argument('-b', '--bboxmin', type=str, default=None, help='Min coordinates to use for foreground.')
    parser.add_argument('-B', '--bboxmax', type=str, default=None, help='Max coordinates to use for foreground.')
    parser.add_argument('--center_bbox', type=str2bool, default=True, help='If True, center the bounding box. Default is True.')
    
    parser.add_argument('--gpu', type=int, default=0, help='Index of GPU device to use.')
    
    parser.add_argument('--eval', type=str2bool, default=True, help='Use eval split.')
    parser.add_argument('--use_centers_to_extract_mesh', type=str2bool, default=False, 
                        help='If True, just use centers of the gaussians to extract mesh.')
    parser.add_argument('--use_marching_cubes', type=str2bool, default=False, 
                        help='If True, use marching cubes to extract mesh.')
    parser.add_argument('--use_vanilla_3dgs', type=str2bool, default=False, 
                        help='If True, use vanilla 3DGS to extract mesh.')
    
    args = parser.parse_args()
    if args.surface_sample_count < 1:
        parser.error('--surface-sample-count must be a positive integer.')
    if args.poisson_depth < 1:
        parser.error('--poisson-depth must be a positive integer.')
    if not 0.0 <= args.vertices_density_quantile < 1.0:
        parser.error('--vertices-density-quantile must be in the interval [0, 1).')
    if not 0.0 <= args.low_opacity_gaussian_threshold < 1.0:
        parser.error('--low-opacity-gaussian-threshold must be in the interval [0, 1).')
    if args.surface_sample_seed is not None and args.surface_sample_seed < 0:
        parser.error('--surface-sample-seed must be non-negative.')
    
    # Call function
    extract_mesh_from_coarse_sugar(args)
    