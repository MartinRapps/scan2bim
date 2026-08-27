import argparse
import os
from sugar_utils.general_utils import str2bool
from sugar_trainers.coarse_density import coarse_training_with_density_regularization
from sugar_trainers.coarse_sdf import coarse_training_with_sdf_regularization
from sugar_trainers.coarse_density_and_dn_consistency import coarse_training_with_density_regularization_and_dn_consistency
from sugar_extractors.coarse_mesh import extract_mesh_from_coarse_sugar
from sugar_trainers.refine import refined_training
from sugar_extractors.refined_mesh import extract_mesh_and_texture_from_refined_sugar


class AttrDict(dict):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.__dict__ = self


if __name__ == "__main__":
    # ----- Parser -----
    parser = argparse.ArgumentParser(description='Script to optimize a full SuGaR model.')
    
    # Data and vanilla 3DGS checkpoint
    parser.add_argument('-s', '--scene_path',
                        type=str, 
                        help='(Required) path to the scene data to use.')  
    parser.add_argument('-c', '--checkpoint_path',
                        type=str, 
                        help='(Required) path to the vanilla 3D Gaussian Splatting Checkpoint to load.')
    parser.add_argument('-i', '--iteration_to_load', 
                        type=int, default=7000, 
                        help='iteration to load.')
    
    # Regularization for coarse SuGaR
    parser.add_argument('-r', '--regularization_type', type=str,
                        help='(Required) Type of regularization to use for coarse SuGaR. Can be "sdf", "density" or "dn_consistency". ' 
                        'We recommend using "dn_consistency" for the best mesh quality.')
    parser.add_argument('--coarse-iterations', type=int, default=None,
                        help='Optional final coarse counter for dn_consistency; c9000 is the segmented-object default, values above 9000 additionally activate DN/SDF terms.')
    
    # Extract mesh
    parser.add_argument('-l', '--surface_level', type=float, default=0.3, 
                        help='Surface level to extract the mesh at. Default is 0.3')
    parser.add_argument('-v', '--n_vertices_in_mesh', type=int, default=1_000_000, 
                        help='Number of vertices in the extracted mesh.')
    parser.add_argument('--project_mesh_on_surface_points', type=str2bool, default=True, 
                        help='If True, project the mesh on the surface points for better details.')
    parser.add_argument('--surface-sample-count', type=int, default=10_000_000,
                        help='Total camera-derived surface samples before Poisson reconstruction.')
    parser.add_argument('--stop-after-coarse-mesh', type=str2bool, default=False,
                        help='Exit successfully after extracting the coarse mesh, before refinement and UV baking.')
    parser.add_argument('-b', '--bboxmin', type=str, default=None, 
                        help='Min coordinates to use for foreground.')  
    parser.add_argument('-B', '--bboxmax', type=str, default=None, 
                        help='Max coordinates to use for foreground.')
    parser.add_argument('--center_bbox', type=str2bool, default=True, 
                        help='If True, center the bbox. Default is False.')
    
    # Parameters for refined SuGaR
    parser.add_argument('-g', '--gaussians_per_triangle', type=int, default=1, 
                        help='Number of gaussians per triangle.')
    parser.add_argument('-f', '--refinement_iterations', type=int, default=15_000, 
                        help='Number of refinement iterations.')
    
    # (Optional) Parameters for textured mesh extraction
    parser.add_argument('-t', '--export_uv_textured_mesh', type=str2bool, default=True, 
                        help='If True, will export a textured mesh as an .obj file from the refined SuGaR model. '
                        'Computing a traditional colored UV texture should take less than 10 minutes.')
    parser.add_argument('--square_size',
                        default=8, type=int, help='Size of the square to use for the UV texture.')
    parser.add_argument('--postprocess_mesh', type=str2bool, default=False, 
                        help='If True, postprocess the mesh by removing border triangles with low-density. '
                        'This step takes a few minutes and is not needed in general, as it can also be risky. '
                        'However, it increases the quality of the mesh in some cases, especially when an object is visible only from one side.')
    parser.add_argument('--postprocess_density_threshold', type=float, default=0.1,
                        help='Threshold to use for postprocessing the mesh.')
    parser.add_argument('--postprocess_iterations', type=int, default=5,
                        help='Number of iterations to use for postprocessing the mesh.')
    
    # (Optional) PLY file export
    parser.add_argument('--export_ply', type=str2bool, default=True,
                        help='If True, export a ply file with the refined 3D Gaussians at the end of the training. '
                        'This file can be large (+/- 500MB), but is needed for using the dedicated viewer. Default is True.')
    
    # (Optional) Default configurations
    parser.add_argument('--low_poly', type=str2bool, default=False, 
                        help='Use standard config for a low poly mesh, with 200k vertices and 6 Gaussians per triangle.')
    parser.add_argument('--high_poly', type=str2bool, default=False,
                        help='Use standard config for a high poly mesh, with 1M vertices and 1 Gaussians per triangle.')
    parser.add_argument('--refinement_time', type=str, default=None, 
                        help="Default configs for time to spend on refinement. Can be 'short', 'medium' or 'long'.")
      
    # Evaluation split
    parser.add_argument('--eval', type=str2bool, default=True, help='Use eval split.')

    # GPU
    parser.add_argument('--gpu', type=int, default=0, help='Index of GPU device to use.')
    parser.add_argument('--white_background', type=str2bool, default=False, help='Use a white background instead of black.')

    # Optional semantic-mask supervision.  Leaving --masks-dir unset retains
    # upstream SuGaR behaviour exactly.
    parser.add_argument(
        '--masks-dir',
        type=str,
        default=None,
        help='Directory containing masks matched to cameras by image name.',
    )
    parser.add_argument(
        '--mask-level',
        choices=['default', 'middle', 'small'],
        default='default',
        help='Mask hierarchy used by RGB reconstruction supervision.',
    )
    parser.add_argument(
        '--normal-mask-level',
        choices=['default', 'middle', 'small'],
        default='middle',
        help='Conservative mask hierarchy used by depth-normal supervision.',
    )
    parser.add_argument(
        '--mask-dilation-px',
        type=int,
        default=2,
        help='Foreground dilation for RGB supervision, in source-image pixels.',
    )
    parser.add_argument(
        '--texture-mask-level',
        choices=['default', 'middle', 'small'],
        default='default',
        help='Mask hierarchy used while baking UV colors.',
    )
    parser.add_argument(
        '--texture-mask-dilation-px',
        type=int,
        default=2,
        help='Foreground dilation for UV color accumulation.',
    )
    parser.add_argument(
        '--mask-dssim-factor',
        type=float,
        default=0.2,
        help='DSSIM contribution inside the masked RGB loss.',
    )
    parser.add_argument(
        '--mask-ssim-window',
        type=int,
        default=11,
        help='Odd local SSIM window size for masked RGB supervision.',
    )
    parser.add_argument(
        '--output-root',
        type=str,
        default='./output',
        help='Root directory for all coarse, mesh, refined, and textured outputs.',
    )

    # Parse arguments
    args = parser.parse_args()
    if args.coarse_iterations is not None:
        if args.coarse_iterations <= 6_999:
            parser.error('--coarse-iterations must exceed the loaded STS counter 6999.')
        if args.regularization_type != 'dn_consistency':
            parser.error('--coarse-iterations is currently supported only with dn_consistency.')
    if args.surface_sample_count < 1:
        parser.error('--surface-sample-count must be a positive integer.')
    if args.mask_dilation_px < 0 or args.texture_mask_dilation_px < 0:
        parser.error('Mask dilation values must not be negative.')
    if not 0.0 <= args.mask_dssim_factor <= 1.0:
        parser.error('--mask-dssim-factor must be in the interval [0, 1].')
    if args.mask_ssim_window < 3 or args.mask_ssim_window % 2 == 0:
        parser.error('--mask-ssim-window must be an odd integer of at least 3.')
    if args.low_poly:
        args.n_vertices_in_mesh = 200_000
        args.gaussians_per_triangle = 6
        print('Using low poly config.')
    if args.high_poly:
        args.n_vertices_in_mesh = 1_000_000
        args.gaussians_per_triangle = 1
        print('Using high poly config.')
    if args.refinement_time == 'short':
        args.refinement_iterations = 2_000
        print('Using short refinement time.')
    if args.refinement_time == 'medium':
        args.refinement_iterations = 7_000
        print('Using medium refinement time.')
    if args.refinement_time == 'long':
        args.refinement_iterations = 15_000
        print('Using long refinement time.')
    if args.export_uv_textured_mesh:
        print('Will export a UV-textured mesh as an .obj file.')
    if args.export_ply:
        print('Will export a ply file with the refined 3D Gaussians at the end of the training.')
    if args.masks_dir:
        print(
            'Using semantic mask supervision: '
            f'RGB={args.mask_level}, DN={args.normal_mask_level}, '
            f'UV={args.texture_mask_level}.'
        )

    scene_name = os.path.basename(os.path.normpath(args.scene_path))
    coarse_output_dir = os.path.join(args.output_root, 'coarse', scene_name)
    coarse_mesh_output_dir = os.path.join(args.output_root, 'coarse_mesh', scene_name)
    refined_output_dir = os.path.join(args.output_root, 'refined', scene_name)
    refined_mesh_output_dir = os.path.join(args.output_root, 'refined_mesh', scene_name)
    
    # ----- Optimize coarse SuGaR -----
    coarse_args = AttrDict({
        'checkpoint_path': args.checkpoint_path,
        'scene_path': args.scene_path,
        'iteration_to_load': args.iteration_to_load,
        'output_dir': coarse_output_dir,
        'eval': args.eval,
        'estimation_factor': 0.2,
        'normal_factor': 0.2,
        'gpu': args.gpu,
        'white_background': args.white_background,
        'masks_dir': args.masks_dir,
        'mask_level': args.mask_level,
        'normal_mask_level': args.normal_mask_level,
        'mask_dilation_px': args.mask_dilation_px,
        'mask_dssim_factor': args.mask_dssim_factor,
        'mask_ssim_window': args.mask_ssim_window,
        'coarse_iterations': args.coarse_iterations,
    })
    if args.regularization_type == 'sdf':
        coarse_sugar_path = coarse_training_with_sdf_regularization(coarse_args)
    elif args.regularization_type == 'density':
        coarse_sugar_path = coarse_training_with_density_regularization(coarse_args)
    elif args.regularization_type == 'dn_consistency':
        coarse_sugar_path = coarse_training_with_density_regularization_and_dn_consistency(coarse_args)
    else:
        raise ValueError(f'Unknown regularization type: {args.regularization_type}')
    
    
    # ----- Extract mesh from coarse SuGaR -----
    coarse_mesh_args = AttrDict({
        'scene_path': args.scene_path,
        'checkpoint_path': args.checkpoint_path,
        'iteration_to_load': args.iteration_to_load,
        'coarse_model_path': coarse_sugar_path,
        'surface_level': args.surface_level,
        'decimation_target': args.n_vertices_in_mesh,
        'project_mesh_on_surface_points': args.project_mesh_on_surface_points,
        'surface_sample_count': args.surface_sample_count,
        'mesh_output_dir': coarse_mesh_output_dir,
        'bboxmin': args.bboxmin,
        'bboxmax': args.bboxmax,
        'center_bbox': args.center_bbox,
        'gpu': args.gpu,
        'eval': args.eval,
        'use_centers_to_extract_mesh': False,
        'use_marching_cubes': False,
        'use_vanilla_3dgs': False,
    })
    coarse_mesh_path = extract_mesh_from_coarse_sugar(coarse_mesh_args)[0]
    if args.stop_after_coarse_mesh:
        print('Stopping after coarse mesh as requested; refinement and UV baking are skipped.')
        raise SystemExit(0)
    
    
    # ----- Refine SuGaR -----
    refined_args = AttrDict({
        'scene_path': args.scene_path,
        'checkpoint_path': args.checkpoint_path,
        'mesh_path': coarse_mesh_path,      
        'output_dir': refined_output_dir,
        'iteration_to_load': args.iteration_to_load,
        'normal_consistency_factor': 0.1,    
        'gaussians_per_triangle': args.gaussians_per_triangle,        
        'n_vertices_in_fg': args.n_vertices_in_mesh,
        'refinement_iterations': args.refinement_iterations,
        'bboxmin': args.bboxmin,
        'bboxmax': args.bboxmax,
        'export_ply': args.export_ply,
        'eval': args.eval,
        'gpu': args.gpu,
        'white_background': args.white_background,
        'masks_dir': args.masks_dir,
        'mask_level': args.mask_level,
        'mask_dilation_px': args.mask_dilation_px,
        'mask_dssim_factor': args.mask_dssim_factor,
        'mask_ssim_window': args.mask_ssim_window,
    })
    refined_sugar_path = refined_training(refined_args)
    
    
    # ----- Extract mesh and texture from refined SuGaR -----
    if args.export_uv_textured_mesh:
        refined_mesh_args = AttrDict({
            'scene_path': args.scene_path,
            'iteration_to_load': args.iteration_to_load,
            'checkpoint_path': args.checkpoint_path,
            'refined_model_path': refined_sugar_path,
            'mesh_output_dir': refined_mesh_output_dir,
            'coarse_mesh_path': coarse_mesh_path,
            'n_gaussians_per_surface_triangle': args.gaussians_per_triangle,
            'square_size': args.square_size,
            'eval': args.eval,
            'gpu': args.gpu,
            'postprocess_mesh': args.postprocess_mesh,
            'postprocess_density_threshold': args.postprocess_density_threshold,
            'postprocess_iterations': args.postprocess_iterations,
            'masks_dir': args.masks_dir,
            'mask_level': args.mask_level,
            'mask_dilation_px': args.mask_dilation_px,
            'texture_mask_level': args.texture_mask_level,
            'texture_mask_dilation_px': args.texture_mask_dilation_px,
        })
        refined_mesh_path = extract_mesh_and_texture_from_refined_sugar(refined_mesh_args)
