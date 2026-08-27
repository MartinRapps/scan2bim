"""Mask loading and mask-aware photometric losses for project-specific SuGaR runs.

The upstream project intentionally has no precomputed-mask support.  This
module keeps the extension opt-in: callers create a :class:`SemanticMaskProvider`
only when a masks directory was supplied.  The provider resolves masks by the
same ``GSCamera.image_name`` used to load RGB supervision.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageFilter

from sugar_utils.loss_utils import create_window


_FRAME_ID_PATTERN = re.compile(r"(\d+)$")


def _frame_id(image_name: str) -> int | None:
    match = _FRAME_ID_PATTERN.search(Path(image_name).stem)
    return int(match.group(1)) if match else None


def _mask_candidates(mask_root: Path, image_name: str, level: str) -> Iterable[Path]:
    stem = Path(image_name).stem
    frame_id = _frame_id(stem)
    if frame_id is not None:
        frame_name = f"frame_{frame_id:05d}"
        yield mask_root / frame_name / f"{level}.png"
        yield mask_root / "000" / f"{frame_id:05d}.png"
        if level == "default":
            yield mask_root / f"{frame_name}_obj_001.png"
    yield mask_root / f"{stem}.png"
    yield mask_root / "000" / f"{stem}.png"


class SemanticMaskProvider:
    """Resolve and lazily cache binary masks for SuGaR training cameras."""

    def __init__(
        self,
        mask_root: str | Path,
        level: str,
        dilation_px: int = 0,
    ) -> None:
        self.mask_root = Path(mask_root)
        self.level = level
        self.dilation_px = dilation_px
        self._cache: dict[tuple[str, int, int], torch.Tensor] = {}

        if level not in {"default", "middle", "small"}:
            raise ValueError(f"Unsupported mask level: {level}")
        if dilation_px < 0:
            raise ValueError("Mask dilation must not be negative")
        if not self.mask_root.is_dir():
            raise FileNotFoundError(f"Mask directory does not exist: {self.mask_root}")

    def find_path(self, image_name: str) -> Path | None:
        return next(
            (path for path in _mask_candidates(self.mask_root, image_name, self.level) if path.is_file()),
            None,
        )

    def validate_cameras(self, cameras: Sequence[object]) -> None:
        """Fail early when a training camera has no usable semantic mask."""

        missing: list[str] = []
        empty: list[str] = []
        for camera in cameras:
            image_name = str(camera.image_name)
            path = self.find_path(image_name)
            if path is None:
                missing.append(image_name)
                continue
            with Image.open(path) as image:
                if image.convert("L").getbbox() is None:
                    empty.append(image_name)

        if missing:
            preview = ", ".join(missing[:10])
            suffix = " ..." if len(missing) > 10 else ""
            raise FileNotFoundError(
                f"No {self.level!r} mask found for {len(missing)} training camera(s): "
                f"{preview}{suffix}"
            )
        if empty:
            preview = ", ".join(empty[:10])
            suffix = " ..." if len(empty) > 10 else ""
            raise ValueError(
                f"The {self.level!r} mask is empty for {len(empty)} training camera(s): "
                f"{preview}{suffix}"
            )

    def _load_cpu_mask(self, image_name: str, height: int, width: int) -> torch.Tensor:
        cache_key = (image_name, height, width)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        path = self.find_path(image_name)
        if path is None:
            raise FileNotFoundError(
                f"No {self.level!r} mask found for training image {image_name!r} "
                f"under {self.mask_root}"
            )

        with Image.open(path) as image:
            mask_image = image.convert("L")
            if mask_image.size != (width, height):
                mask_image = mask_image.resize((width, height), Image.Resampling.NEAREST)
            if self.dilation_px > 0:
                mask_image = mask_image.filter(
                    ImageFilter.MaxFilter(size=2 * self.dilation_px + 1)
                )
            mask = np.asarray(mask_image, dtype=np.uint8) > 0

        if not np.any(mask):
            raise ValueError(
                f"Mask for training image {image_name!r} is empty: {path}. "
                "An empty object mask must not silently become background supervision."
            )

        cached = torch.from_numpy(np.ascontiguousarray(mask[None, ...]))
        self._cache[cache_key] = cached
        return cached

    def for_camera(
        self,
        camera: object,
        device: torch.device | str,
        dtype: torch.dtype,
    ) -> torch.Tensor:
        """Return shape ``[1, 1, H, W]`` mask for a ``GSCamera`` instance."""

        image_name = str(camera.image_name)
        height = int(camera.image_height)
        width = int(camera.image_width)
        mask = self._load_cpu_mask(image_name, height, width)
        return mask.unsqueeze(0).to(device=device, dtype=dtype, non_blocking=False)


def _validate_mask(mask: torch.Tensor, reference: torch.Tensor) -> torch.Tensor:
    if reference.ndim != 4:
        raise ValueError("Expected reconstruction tensors with shape [N, C, H, W]")
    if mask.ndim == 3:
        mask = mask.unsqueeze(1)
    if mask.ndim != 4 or mask.shape[1] != 1:
        raise ValueError("Mask must have shape [N, 1, H, W]")
    if mask.shape[0] not in (1, reference.shape[0]) or mask.shape[-2:] != reference.shape[-2:]:
        raise ValueError(
            f"Mask shape {tuple(mask.shape)} is incompatible with image shape {tuple(reference.shape)}"
        )
    if mask.shape[0] == 1 and reference.shape[0] > 1:
        mask = mask.expand(reference.shape[0], -1, -1, -1)
    mask = mask.to(device=reference.device, dtype=reference.dtype)
    if mask.numel() == 0:
        raise ValueError("A reconstruction mask must not be empty")
    return mask


def masked_l1_loss(prediction: torch.Tensor, target: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Compute mean absolute RGB error only over semantic foreground pixels."""

    mask = _validate_mask(mask, prediction)
    per_pixel_error = (prediction - target).abs().mean(dim=1, keepdim=True)
    return (per_pixel_error * mask).sum() / mask.sum().clamp_min(1.0)


def masked_l2_loss(prediction: torch.Tensor, target: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Compute mean squared RGB error only over semantic foreground pixels."""

    mask = _validate_mask(mask, prediction)
    per_pixel_error = (prediction - target).square().mean(dim=1, keepdim=True)
    return (per_pixel_error * mask).sum() / mask.sum().clamp_min(1.0)


def masked_ssim(
    prediction: torch.Tensor,
    target: torch.Tensor,
    mask: torch.Tensor,
    window_size: int = 11,
) -> torch.Tensor:
    """Compute SSIM with foreground-weighted local moments and foreground averaging.

    Blackening the background before ordinary SSIM would still make it part of
    the local statistics.  Here every local mean and variance is normalized by
    the Gaussian window's mask weight, so pixels outside the object contribute
    neither supervision nor local context.
    """

    if window_size < 3 or window_size % 2 == 0:
        raise ValueError("SSIM window size must be an odd integer of at least three")
    mask = _validate_mask(mask, prediction)
    if prediction.shape != target.shape:
        raise ValueError("Prediction and target must have identical shapes")

    channels = prediction.shape[1]
    window = create_window(window_size, channels).to(
        device=prediction.device, dtype=prediction.dtype
    )
    padding = window_size // 2
    weighted_mask = mask.expand(-1, channels, -1, -1)
    normalization = F.conv2d(mask, window[:1], padding=padding).clamp_min(1e-6)

    def local_mean(image: torch.Tensor) -> torch.Tensor:
        return F.conv2d(image * weighted_mask, window, padding=padding, groups=channels) / normalization

    mean_prediction = local_mean(prediction)
    mean_target = local_mean(target)
    variance_prediction = local_mean(prediction.square()) - mean_prediction.square()
    variance_target = local_mean(target.square()) - mean_target.square()
    covariance = local_mean(prediction * target) - mean_prediction * mean_target

    c1 = 0.01**2
    c2 = 0.03**2
    ssim_map = (
        (2.0 * mean_prediction * mean_target + c1) * (2.0 * covariance + c2)
    ) / (
        (mean_prediction.square() + mean_target.square() + c1)
        * (variance_prediction + variance_target + c2)
    )
    foreground_ssim = ssim_map.mean(dim=1, keepdim=True)
    return (foreground_ssim * mask).sum() / mask.sum().clamp_min(1.0)


def masked_reconstruction_loss(
    prediction: torch.Tensor,
    target: torch.Tensor,
    mask: torch.Tensor,
    loss_function: str,
    dssim_factor: float = 0.2,
    ssim_window_size: int = 11,
) -> torch.Tensor:
    """Apply a SuGaR-compatible photometric loss inside a semantic mask."""

    if loss_function == "l1":
        return masked_l1_loss(prediction, target, mask)
    if loss_function == "l2":
        return masked_l2_loss(prediction, target, mask)
    if loss_function == "l1+dssim":
        return (1.0 - dssim_factor) * masked_l1_loss(
            prediction, target, mask
        ) + dssim_factor * (1.0 - masked_ssim(
            prediction, target, mask, window_size=ssim_window_size
        ))
    raise ValueError(f"Unsupported reconstruction loss: {loss_function}")