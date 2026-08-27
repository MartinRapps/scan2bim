import argparse
import json
import os
import re
from pathlib import Path
from typing import List

import cv2
import numpy as np


def pick_sample_indices(num_frames: int) -> List[int]:
    if num_frames <= 1:
        return [0]

    candidates = [
        0,
        max(0, num_frames // 3),
        max(0, (2 * num_frames) // 3),
        num_frames - 1,
    ]

    ordered = []
    for index in candidates:
        if index not in ordered:
            ordered.append(index)
    return ordered


def extract_frame_id(frame_name: str, fallback_index: int) -> int:
    stem = os.path.splitext(frame_name)[0]
    match = re.search(r"(\d+)$", stem)
    if match is None:
        return fallback_index
    return int(match.group(1))


def load_mask(mask_root: str, frame_id: int, mask_name: str, height: int, width: int) -> np.ndarray:
    nested_path = os.path.join(mask_root, f"frame_{frame_id:05d}", f"{mask_name}.png")
    flat_path = os.path.join(mask_root, f"frame_{frame_id:05d}_obj_001.png")

    mask = None
    if os.path.exists(nested_path):
        mask = cv2.imread(nested_path, cv2.IMREAD_GRAYSCALE)
    elif os.path.exists(flat_path):
        mask = cv2.imread(flat_path, cv2.IMREAD_GRAYSCALE)

    if mask is None:
        return np.zeros((height, width), dtype=np.uint8)
    return np.where(mask > 0, 255, 0).astype(np.uint8)


def find_best_attempt_dir(mask_root: str) -> tuple[str | None, int]:
    attempts_root = os.path.join(mask_root, "_attempts")
    if not os.path.isdir(attempts_root):
        return None, 0

    best_dir = None
    best_nonempty = 0
    for candidate in sorted(os.listdir(attempts_root)):
        candidate_dir = os.path.join(attempts_root, candidate)
        if not os.path.isdir(candidate_dir):
            continue
        nonempty = 0
        for name in os.listdir(candidate_dir):
            if not name.startswith("frame_") or not name.endswith("_obj_001.png"):
                continue
            mask = cv2.imread(os.path.join(candidate_dir, name), cv2.IMREAD_GRAYSCALE)
            if mask is not None and np.count_nonzero(mask) > 0:
                nonempty += 1
        if nonempty > best_nonempty:
            best_nonempty = nonempty
            best_dir = candidate_dir
    return best_dir, best_nonempty


def load_attempt_mask(attempt_dir: str, frame_id: int, height: int, width: int) -> np.ndarray:
    path = os.path.join(attempt_dir, f"frame_{frame_id:05d}_obj_001.png")
    mask = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return np.zeros((height, width), dtype=np.uint8)
    return np.where(mask > 0, 255, 0).astype(np.uint8)


def draw_overlay(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    overlay = image.copy()
    color_mask = np.zeros_like(image)
    color_mask[:, :, 1] = mask
    overlay = cv2.addWeighted(overlay, 1.0, color_mask, 0.35, 0.0)

    contours, _ = cv2.findContours((mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(overlay, contours, -1, (0, 0, 255), 2)
    return overlay


def extract_cutout(image: np.ndarray, mask: np.ndarray, padding: int) -> np.ndarray:
    masked = cv2.bitwise_and(image, image, mask=mask)
    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        return masked

    x_min = max(0, int(xs.min()) - padding)
    x_max = min(image.shape[1], int(xs.max()) + padding)
    y_min = max(0, int(ys.min()) - padding)
    y_max = min(image.shape[0], int(ys.max()) + padding)
    return masked[y_min:y_max, x_min:x_max]


def build_panel(image: np.ndarray, overlay: np.ndarray, cutout: np.ndarray) -> np.ndarray:
    target_height = image.shape[0]
    if cutout.shape[0] == 0 or cutout.shape[1] == 0:
        cutout = np.zeros_like(image)
    else:
        scale = target_height / float(cutout.shape[0])
        target_width = max(1, int(round(cutout.shape[1] * scale)))
        cutout = cv2.resize(cutout, (target_width, target_height), interpolation=cv2.INTER_AREA)

    return np.concatenate([image, overlay, cutout], axis=1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export review samples for manual mask edge inspection.")
    parser.add_argument("--frames-dir", default="/data/02_frames", help="Directory with extracted frames")
    parser.add_argument("--masks-dir", default="/data/03_masks", help="Directory with flat and hierarchical masks")
    parser.add_argument("--mask-name", default="middle", choices=["default", "middle", "small"], help="Which hierarchical mask to review")
    parser.add_argument("--output-dir", default="/data/03_masks/_review_samples", help="Where to store review panels")
    parser.add_argument("--padding", type=int, default=24, help="Padding in pixels around the cropped mask region")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use deterministic default/explicit indices without reading stdin.",
    )
    parser.add_argument(
        "--indices",
        default=None,
        help="Comma-separated frame indices, for example 0,80,160.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="export_all",
        help="Export every frame instead of the standard review subset.",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Optional JSON manifest path; defaults to <output-dir>/review_manifest.json.",
    )
    args = parser.parse_args()

    frame_files = sorted(
        name for name in os.listdir(args.frames_dir)
        if name.lower().endswith((".jpg", ".jpeg", ".png"))
    )
    if not frame_files:
        raise FileNotFoundError(f"No frames found in {args.frames_dir}")

    os.makedirs(args.output_dir, exist_ok=True)

    # Interaktive Abfrage für spezielle Frames. Matrix runs use the explicit
    # non-interactive branch so a PTY can never block on stdin.
    indices = []
    if args.indices:
        try:
            indices = sorted({int(value.strip()) for value in args.indices.split(",") if value.strip()})
        except ValueError as error:
            raise ValueError(f"Invalid --indices value: {args.indices}") from error
        indices = [index for index in indices if 0 <= index < len(frame_files)]
    elif args.export_all:
        indices = list(range(len(frame_files)))
    elif args.non_interactive:
        indices = pick_sample_indices(len(frame_files))
    else:
        print("Möchten Sie spezielle Frames exportieren? (j/n) [Standard: n]: ", end="", flush=True)
        try:
            choice = input().strip().lower()
        except (KeyboardInterrupt, EOFError):
            choice = "n"

        if choice in ["j", "ja", "y", "yes"]:
            print("Sollen ein oder mehrere Frames exportiert werden? (einzeln/mehrere) [e/m]: ", end="", flush=True)
            try:
                type_choice = input().strip().lower()
            except (KeyboardInterrupt, EOFError):
                type_choice = "e"

            if type_choice in ["m", "mehrere", "multiple", "bereich"]:
                try:
                    print("Start-Frame (Index, z.B. 10): ", end="", flush=True)
                    start_frame = int(input().strip())
                    print("End-Frame (Index inkl., z.B. 20): ", end="", flush=True)
                    end_frame = int(input().strip())
                    if start_frame <= end_frame:
                        indices = [
                            idx
                            for idx in range(start_frame, end_frame + 1)
                            if 0 <= idx < len(frame_files)
                        ]
                        if not indices:
                            print("Keine gültigen Indizes im angegebenen Bereich gefunden.")
                    else:
                        print("Start-Frame ist größer als der End-Frame.")
                except (ValueError, KeyboardInterrupt, EOFError):
                    print("Ungültige Eingabe. Verwende Standard-Verteilung.")
            else:
                try:
                    print("Welcher Frame-Index soll exportiert werden? (z.B. 15): ", end="", flush=True)
                    frame_idx = int(input().strip())
                    if 0 <= frame_idx < len(frame_files):
                        indices = [frame_idx]
                    else:
                        print(
                            f"Index {frame_idx} liegt außerhalb des gültigen Bereichs "
                            f"(0 bis {len(frame_files)-1})."
                        )
                except (ValueError, KeyboardInterrupt, EOFError):
                    print("Ungültige Eingabe. Verwende Standard-Verteilung.")

    if not indices:
        indices = pick_sample_indices(len(frame_files))
        print(f"Exportiere Standard-Review-Frames für Indizes: {indices}")
    else:
        print(f"Exportiere angeforderte Review-Frames für Indizes: {indices}")

    best_attempt_dir, best_attempt_nonempty = find_best_attempt_dir(args.masks_dir)
    if best_attempt_dir is not None and best_attempt_nonempty > 0:
        print(
            f"Fallback available: {best_attempt_dir} with {best_attempt_nonempty} non-empty masks "
            "(used if hierarchical mask is empty for a sample frame)."
        )

    exported_files: list[str] = []
    empty_masks = 0
    resolutions: set[tuple[int, int]] = set()

    for frame_index in indices:
        frame_name = frame_files[frame_index]
        frame_path = os.path.join(args.frames_dir, frame_name)
        image = cv2.imread(frame_path, cv2.IMREAD_COLOR)
        if image is None:
            print(f"Skipping unreadable frame: {frame_path}")
            continue
        resolutions.add((int(image.shape[1]), int(image.shape[0])))

        frame_id = extract_frame_id(frame_name, frame_index)
        mask = load_mask(args.masks_dir, frame_id, args.mask_name, image.shape[0], image.shape[1])
        if np.count_nonzero(mask) == 0 and best_attempt_dir is not None and best_attempt_nonempty > 0:
            mask = load_attempt_mask(best_attempt_dir, frame_id, image.shape[0], image.shape[1])
        if np.count_nonzero(mask) == 0:
            empty_masks += 1
        overlay = draw_overlay(image, mask)
        cutout = extract_cutout(image, mask, args.padding)
        panel = build_panel(image, overlay, cutout)

        # Neue Verzeichnisstruktur unterhalb von args.output_dir:
        # 1. Panels (Dreifach-Kombination aus Original, Overlay und Cutout)
        panel_dir = os.path.join(args.output_dir, "panels")
        # 2. Grundlagen (Cutouts und Overlays zur Einzelanalyse)
        elements_dir = os.path.join(args.output_dir, "grundlagen")
        
        os.makedirs(panel_dir, exist_ok=True)
        os.makedirs(elements_dir, exist_ok=True)

        base_name = f"frame_{frame_id:05d}_{args.mask_name}"
        output_files = [
            os.path.join(elements_dir, f"{base_name}_overlay.png"),
            os.path.join(elements_dir, f"{base_name}_cutout.png"),
            os.path.join(panel_dir, f"{base_name}_panel.png"),
        ]
        cv2.imwrite(output_files[0], overlay)
        cv2.imwrite(output_files[1], cutout)
        cv2.imwrite(output_files[2], panel)
        exported_files.extend(output_files)

    print(f"Review samples written to {args.output_dir}")
    manifest_path = Path(args.manifest or os.path.join(args.output_dir, "review_manifest.json"))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "frames_dir": args.frames_dir,
                "masks_dir": args.masks_dir,
                "mask_name": args.mask_name,
                "requested_indices": indices,
                "exported_file_count": len(exported_files),
                "empty_mask_count": empty_masks,
                "resolutions": [{"width": width, "height": height} for width, height in sorted(resolutions)],
                "files": exported_files,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Review manifest written to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
