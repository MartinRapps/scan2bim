#!/usr/bin/env python3
"""Render a SuGaR coarse checkpoint on the shared fixed test split."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import torch
from torchvision.utils import save_image

# This helper is mounted from /app/src, while SuGaR itself lives below
# /opt/sugar in Container D. Executing a script by its absolute path does not
# add the current working directory to Python's import path, so make the
# mounted/bundled SuGaR root explicit before importing sugar_scene.
SUGAR_ROOT = os.environ.get("SUGAR_ROOT", "/opt/sugar")
if SUGAR_ROOT not in sys.path:
    sys.path.insert(0, SUGAR_ROOT)

from sugar_scene.gs_model import GaussianSplattingWrapper
from sugar_scene.sugar_model import SuGaR
from sugar_utils.spherical_harmonics import SH2RGB


def as_chw(image: torch.Tensor) -> torch.Tensor:
    """Normalize renderer output to torchvision's channel-first image layout."""
    image = image.squeeze()
    if image.ndim != 3:
        raise ValueError(f"Expected a 3D image tensor, got shape {tuple(image.shape)}")
    if image.shape[0] in (1, 3, 4):
        return image
    if image.shape[-1] in (1, 3, 4):
        return image.permute(2, 0, 1)
    raise ValueError(f"Could not infer image channel dimension from shape {tuple(image.shape)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-path", required=True)
    parser.add_argument("--checkpoint-path", required=True, help="Prepared high-opacity vanilla GS checkpoint root.")
    parser.add_argument("--coarse-model-path", required=True)
    parser.add_argument("--iteration", type=int, default=7000)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gpu", type=int, default=0)
    args = parser.parse_args()

    os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
    torch.cuda.set_device(args.gpu)
    nerfmodel = GaussianSplattingWrapper(
        source_path=args.scene_path,
        output_path=args.checkpoint_path,
        iteration_to_load=args.iteration,
        load_gt_images=True,
        eval_split=True,
        eval_split_interval=8,
    )
    checkpoint = torch.load(args.coarse_model_path, map_location=nerfmodel.device)
    state = checkpoint["state_dict"]
    sugar = SuGaR(
        nerfmodel=nerfmodel,
        points=state["_points"],
        colors=SH2RGB(state["_sh_coordinates_dc"][:, 0, :]),
        initialize=True,
        sh_levels=nerfmodel.gaussians.active_sh_degree + 1,
        keep_track_of_knn=False,
        knn_to_track=0,
        beta_mode="average",
        primitive_types="diamond",
        surface_mesh_to_bind=None,
    )
    sugar.load_state_dict(state)
    sugar.eval()

    cameras = nerfmodel.test_cameras
    if cameras is None or not cameras.gs_cameras:
        raise RuntimeError("No fixed test cameras available; check EVAL_FRAMES_PATH.")
    render_dir = args.output_dir / "renders"
    gt_dir = args.output_dir / "gt"
    render_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    with torch.no_grad():
        for index, camera in enumerate(cameras.gs_cameras):
            image = sugar.render_image_gaussian_rasterizer(
                nerf_cameras=cameras,
                camera_indices=index,
                bg_color=torch.zeros(3, device=sugar.device),
                sh_deg=0,
                compute_color_in_rasterizer=True,
                compute_covariance_in_rasterizer=True,
            ).clamp(0.0, 1.0)
            save_image(as_chw(image), str(render_dir / f"{index:05d}.png"))
            save_image(as_chw(camera.original_image[:3].clamp(0.0, 1.0)), str(gt_dir / f"{index:05d}.png"))

    print(f"Rendered {len(cameras.gs_cameras)} fixed-test views to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
