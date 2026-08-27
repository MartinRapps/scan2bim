#!/usr/bin/env python3
"""Create one deterministic evaluation-frame list for all model stages."""

from __future__ import annotations

import argparse
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stride", type=int, default=8)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument(
        "--masks-dir",
        type=Path,
        help="Optional mask root; only frames with a non-empty mask are eligible.",
    )
    parser.add_argument(
        "--mask-name",
        choices=("default", "middle", "small"),
        default="middle",
        help="Mask level used with --masks-dir.",
    )
    args = parser.parse_args()
    if args.stride <= 0 or args.offset < 0:
        parser.error("--stride must be positive and --offset must be non-negative")

    images = sorted(
        path.name
        for path in args.images_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    if not images:
        raise FileNotFoundError(f"No images found in {args.images_dir}")
    eligible_images = images
    if args.masks_dir is not None:
        from mask_paths import find_mask, mask_nonempty

        if not args.masks_dir.is_dir():
            raise FileNotFoundError(f"Mask directory not found: {args.masks_dir}")
        eligible_images = []
        for name in images:
            mask_path = find_mask(args.masks_dir, name, args.mask_name)
            if mask_path is not None and mask_nonempty(mask_path):
                eligible_images.append(name)
        if not eligible_images:
            raise ValueError(
                f"No non-empty {args.mask_name} masks found under {args.masks_dir}"
            )
    selected = [
        name for index, name in enumerate(eligible_images) if index % args.stride == args.offset
    ]
    if not selected:
        raise ValueError("The evaluation split is empty")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(selected) + "\n", encoding="utf-8")
    if args.masks_dir is None:
        print(f"Evaluation split: {len(selected)} of {len(images)} images -> {args.output}")
    else:
        print(
            f"Evaluation split: {len(selected)} of {len(eligible_images)} eligible "
            f"({len(images)} total) images using non-empty {args.mask_name} masks -> {args.output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
