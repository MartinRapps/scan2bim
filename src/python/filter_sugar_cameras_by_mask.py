import argparse
import json
from pathlib import Path
from typing import Sequence, Tuple

from cameras_json import load_camera_records
from cli_utils import run_main
from mask_paths import find_mask, mask_nonempty


def camera_mask_status(mask_root: Path, image_name: str, levels: Sequence[str]) -> Tuple[bool, str]:
    for level in levels:
        mask_path = find_mask(mask_root, image_name, level)
        if mask_path is None:
            return False, f"missing {level}"
        if not mask_nonempty(mask_path):
            return False, f"empty {level}"
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Filter a private SuGaR cameras.json to cameras with usable semantic masks."
    )
    parser.add_argument("--input", required=True, type=Path, help="Source cameras.json")
    parser.add_argument("--output", required=True, type=Path, help="Filtered cameras.json")
    parser.add_argument("--masks-dir", required=True, type=Path, help="Semantic mask root")
    parser.add_argument(
        "--levels",
        nargs="+",
        choices=("default", "middle", "small"),
        required=True,
        help="Every retained camera must have a non-empty mask at each listed level.",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(f"Camera metadata does not exist: {args.input}")
    if not args.masks_dir.is_dir():
        raise FileNotFoundError(f"Mask directory does not exist: {args.masks_dir}")

    levels = list(dict.fromkeys(args.levels))
    cameras = load_camera_records(args.input)

    retained = []
    excluded = []
    for camera in cameras:
        image_name = str(camera.get("img_name", ""))
        if not image_name:
            raise ValueError("Camera metadata entry has no img_name")
        usable, reason = camera_mask_status(args.masks_dir, image_name, levels)
        if usable:
            retained.append(camera)
        else:
            excluded.append((image_name, reason))

    if not retained:
        raise RuntimeError(
            "No cameras with usable semantic masks remain. Please verify the SAM mask output."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = args.output.with_name(args.output.name + ".tmp")
    temporary_output.write_text(json.dumps(retained, indent=2), encoding="utf-8")
    temporary_output.replace(args.output)

    print(
        f"SuGaR camera filter: retained {len(retained)} of {len(cameras)} cameras "
        f"for mask levels: {', '.join(levels)}."
    )
    if excluded:
        preview = ", ".join(f"{name} ({reason})" for name, reason in excluded[:10])
        suffix = " ..." if len(excluded) > 10 else ""
        print(f"Excluded {len(excluded)} camera(s): {preview}{suffix}")
    return 0


if __name__ == "__main__":
    run_main(main, catch=(OSError, ValueError, RuntimeError))
