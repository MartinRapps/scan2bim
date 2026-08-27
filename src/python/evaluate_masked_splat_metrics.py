#!/usr/bin/env python3
"""Evaluate object-only Gaussian renders on a fixed frame split.

The evaluator deliberately has no full-frame mode. It computes PSNR, SSIM and
LPIPS only over the object mask, because the current STS/SuGaR models are
object-only Splats rather than full-scene reconstructions.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity


def read_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def read_mask(mask_root: Path, frame_name: str, level: str, shape: tuple[int, int]) -> np.ndarray:
    match = re.search(r"(\d+)$", Path(frame_name).stem)
    if match is None:
        raise ValueError(f"Could not derive frame id from {frame_name}")
    frame_id = int(match.group(1))
    candidates = [
        mask_root / f"frame_{frame_id:05d}" / f"{level}.png",
        mask_root / f"frame_{frame_id:05d}_obj_001.png",
    ]
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise FileNotFoundError(f"No {level} mask for {frame_name} under {mask_root}")
    with Image.open(path) as image:
        mask = np.asarray(image.convert("L"), dtype=np.uint8)
    if mask.shape != shape:
        mask = np.asarray(Image.fromarray(mask).resize((shape[1], shape[0]), Image.Resampling.NEAREST))
    return mask > 0


def bbox(mask: np.ndarray, padding: int) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return (
        max(0, int(xs.min()) - padding),
        max(0, int(ys.min()) - padding),
        min(mask.shape[1], int(xs.max()) + padding + 1),
        min(mask.shape[0], int(ys.max()) + padding + 1),
    )


def masked_psnr(render: np.ndarray, target: np.ndarray, mask: np.ndarray) -> float:
    squared_error = np.square(render - target).mean(axis=2)
    valid = squared_error[mask]
    if valid.size == 0:
        return float("nan")
    mse = float(valid.mean())
    # A finite sentinel keeps the JSON report standards-compliant. The exact
    # zero-error case is also recorded through the per-frame MSE below.
    return 99.0 if mse == 0.0 else float(-10.0 * math.log10(mse))


def masked_ssim(render: np.ndarray, target: np.ndarray, mask: np.ndarray) -> float:
    if min(render.shape[:2]) < 3:
        return float("nan")
    window = min(11, min(render.shape[:2]))
    if window % 2 == 0:
        window -= 1
    if window < 3:
        return float("nan")
    _, ssim_map = structural_similarity(
        render,
        target,
        channel_axis=2,
        data_range=1.0,
        win_size=window,
        full=True,
    )
    if ssim_map.ndim == 3:
        ssim_map = ssim_map.mean(axis=2)
    valid = ssim_map[mask]
    return float(valid.mean()) if valid.size else float("nan")


def prepare_lpips_inputs(
    render: np.ndarray, target: np.ndarray, mask: np.ndarray, padding: int
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]:
    region = bbox(mask, padding)
    if region is None:
        raise ValueError("Object mask is empty")
    x0, y0, x1, y1 = region
    crop_mask = mask[y0:y1, x0:x1]
    render_crop = render[y0:y1, x0:x1].copy()
    target_crop = target[y0:y1, x0:x1].copy()
    neutral = np.full(3, 0.5, dtype=np.float32)
    render_crop[~crop_mask] = neutral
    target_crop[~crop_mask] = neutral
    if min(render_crop.shape[:2]) < 64:
        height = max(64, render_crop.shape[0])
        width = max(64, render_crop.shape[1])
        render_crop = np.asarray(Image.fromarray(np.clip(render_crop * 255, 0, 255).astype(np.uint8)).resize((width, height), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
        target_crop = np.asarray(Image.fromarray(np.clip(target_crop * 255, 0, 255).astype(np.uint8)).resize((width, height), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
    return render_crop, target_crop, region


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renders-dir", type=Path, required=True)
    parser.add_argument("--ground-truth-dir", type=Path, required=True)
    parser.add_argument("--masks-dir", type=Path, required=True)
    parser.add_argument("--eval-frames", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mask-level", choices=["default", "middle", "small"], default="default")
    parser.add_argument("--lpips-net", choices=["vgg", "alex", "squeeze"], default="vgg")
    parser.add_argument("--lpips-padding", type=int, default=16)
    parser.add_argument(
        "--require-lpips",
        action="store_true",
        help="Fail instead of writing a partial report when LPIPS is unavailable.",
    )
    args = parser.parse_args()
    if args.lpips_padding < 0:
        parser.error("--lpips-padding must be non-negative")

    frame_names = [line.strip() for line in args.eval_frames.read_text(encoding="utf-8").splitlines() if line.strip()]
    render_paths = sorted(path for path in args.renders_dir.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"})
    gt_paths = sorted(path for path in args.ground_truth_dir.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if len(render_paths) != len(frame_names) or len(gt_paths) != len(frame_names):
        raise ValueError(
            f"Render/GT/eval count mismatch: renders={len(render_paths)}, "
            f"ground_truth={len(gt_paths)}, eval_frames={len(frame_names)}"
        )

    lpips_model = None
    lpips_error = None
    try:
        import lpips  # type: ignore
        import torch

        lpips_model = lpips.LPIPS(net=args.lpips_net).eval().cuda()
    except Exception as error:  # dependency or pretrained-weight failure is reported, not hidden
        lpips_error = f"LPIPS unavailable: {error}"
    if args.require_lpips and lpips_error:
        raise RuntimeError(lpips_error)

    per_frame: list[dict[str, object]] = []
    start = time.perf_counter()
    for frame_name, render_path, gt_path in zip(frame_names, render_paths, gt_paths):
        render = read_rgb(render_path)
        target = read_rgb(gt_path)
        if render.shape != target.shape:
            raise ValueError(f"Render/GT shape mismatch for {frame_name}: {render.shape} vs {target.shape}")
        mask = read_mask(args.masks_dir, frame_name, args.mask_level, render.shape[:2])
        valid_count = int(mask.sum())
        if valid_count == 0:
            raise ValueError(f"Empty evaluation mask for {frame_name}")

        render_crop, target_crop, crop_box = prepare_lpips_inputs(render, target, mask, args.lpips_padding)
        lpips_value = None
        if lpips_model is not None:
            import torch

            with torch.no_grad():
                render_tensor = torch.from_numpy(render_crop).permute(2, 0, 1).unsqueeze(0).mul(2).sub(1).cuda()
                target_tensor = torch.from_numpy(target_crop).permute(2, 0, 1).unsqueeze(0).mul(2).sub(1).cuda()
                lpips_value = float(lpips_model(render_tensor, target_tensor).item())

        mask_box = bbox(mask, 0)
        per_frame.append(
            {
                "frame": frame_name,
                "render": str(render_path),
                "ground_truth": str(gt_path),
                "psnr_masked": masked_psnr(render, target, mask),
                "mse_masked": float(np.square(render - target).mean(axis=2)[mask].mean()),
                "ssim_masked": masked_ssim(render, target, mask),
                "lpips_masked": lpips_value,
                "valid_pixel_count": valid_count,
                "mask_area_fraction": float(valid_count / mask.size),
                "mask_bbox": list(mask_box) if mask_box else None,
                "crop_bbox": list(crop_box),
            }
        )

    def mean_metric(key: str) -> float | None:
        values = [float(item[key]) for item in per_frame if item[key] is not None and math.isfinite(float(item[key]))]
        return float(np.mean(values)) if values else None

    result = {
        "evaluation_scope": "object_masked_only",
        "mask_level": args.mask_level,
        "evaluation_frame_count": len(per_frame),
        "evaluation_frames": frame_names,
        "psnr_masked": mean_metric("psnr_masked"),
        "ssim_masked": mean_metric("ssim_masked"),
        "lpips_masked": mean_metric("lpips_masked"),
        "valid_pixel_count_total": int(sum(int(item["valid_pixel_count"]) for item in per_frame)),
        "lpips_padding": args.lpips_padding,
        "lpips_error": lpips_error,
        "duration_seconds": time.perf_counter() - start,
        "per_frame": per_frame,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("psnr_masked", "ssim_masked", "lpips_masked", "evaluation_frame_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
