import os
import glob
import shutil
import cv2
import numpy as np

from hierarchical_masks import make_hierarchical_masks, to_binary_mask


def count_nonempty_hierarchical_masks(masks_dir: str, level: str = "middle") -> int:
    count = 0
    for path in sorted(glob.glob(os.path.join(masks_dir, "frame_*", f"{level}.png"))):
        m = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if m is not None and np.count_nonzero(m) > 0:
            count += 1
    return count


def find_best_attempt_dir(masks_dir: str) -> tuple[str | None, int]:
    attempt_root = os.path.join(masks_dir, "_attempts")
    if not os.path.isdir(attempt_root):
        return None, 0

    best_dir = None
    best_nonempty = 0
    for candidate in sorted(glob.glob(os.path.join(attempt_root, "*"))):
        if not os.path.isdir(candidate):
            continue
        nonempty = 0
        for path in sorted(glob.glob(os.path.join(candidate, "frame_*_obj_001.png"))):
            m = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if m is not None and np.count_nonzero(m) > 0:
                nonempty += 1
        if nonempty > best_nonempty:
            best_nonempty = nonempty
            best_dir = candidate
    return best_dir, best_nonempty

def find_best_sparse_model(sfm_sparse_dir: str) -> str:
    if not os.path.exists(sfm_sparse_dir):
        return sfm_sparse_dir

    # Falls der Ordner direkt points3D enthält, nutzen wir ihn
    if os.path.isfile(os.path.join(sfm_sparse_dir, "points3D.bin")) or os.path.isfile(os.path.join(sfm_sparse_dir, "points3D.txt")):
        return sfm_sparse_dir

    subdirs = [d for d in os.listdir(sfm_sparse_dir) if os.path.isdir(os.path.join(sfm_sparse_dir, d))]
    if not subdirs:
        return sfm_sparse_dir

    best_dir = None
    max_size = -1
    for subdir in subdirs:
        candidate_path = os.path.join(sfm_sparse_dir, subdir)
        p3d_bin = os.path.join(candidate_path, "points3D.bin")
        p3d_txt = os.path.join(candidate_path, "points3D.txt")
        size = 0
        if os.path.exists(p3d_bin):
            size = os.path.getsize(p3d_bin)
        elif os.path.exists(p3d_txt):
            size = os.path.getsize(p3d_txt)
        
        if size > max_size:
            max_size = size
            best_dir = candidate_path

    if best_dir is not None:
        print(f"Auto-selected best COLMAP sparse model subdirectory: {best_dir} (size: {max_size} bytes)")
        return best_dir
    return os.path.join(sfm_sparse_dir, "0")

def clean_and_create_dir(path):
    if os.path.islink(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)

def main():
    print("=== Preparing Segment-then-Splat (STS) Scene Structure ===")
    
    scene_root = "/data/05_3dgs"
    frames_dir = os.environ.get("STS_IMAGES_DIR", "/data/04_sfm/undistorted/images")
    masks_dir = os.environ.get("STS_MASKS_DIR", "/data/03_masks")
    sfm_dir = os.environ.get("STS_SFM_DIR", "/data/04_sfm/undistorted")
    eval_frames_path = os.environ.get("EVAL_FRAMES_PATH", "")

    # STS accepts only ideal PINHOLE/SIMPLE_PINHOLE cameras. run_sfm.sh creates
    # the downstream scene at this path either by undistorting a
    # distortion-bearing COLMAP model or by passing through an already ideal
    # PINHOLE/SIMPLE_PINHOLE scene. Older replays may not have that derived
    # scene yet, so retain a clear fallback for already compatible inputs and
    # let STS report the model mismatch otherwise.
    if not os.path.isdir(frames_dir) or not os.path.isdir(os.path.join(sfm_dir, "sparse")):
        frames_dir = "/data/02_frames"
        sfm_dir = "/data/04_sfm"
    print(f"STS image input: {frames_dir}")
    print(f"STS COLMAP input: {sfm_dir}")
    print(f"STS mask input: {masks_dir}")
    print(f"STS evaluation split: {eval_frames_path or 'legacy every tenth frame'}")
    
    # 1. Clean and setup directories
    print("Setting up directory structure under /data/05_3dgs...")
    os.makedirs(scene_root, exist_ok=True)
    
    # Images symlink/copy (using a symlink is fast and works inside Docker)
    images_link = os.path.join(scene_root, "images")
    if os.path.islink(images_link):
        os.unlink(images_link)
    elif os.path.exists(images_link):
        shutil.rmtree(images_link)
    
    os.symlink(frames_dir, images_link)
    print(f"Created symlink to input images: {images_link} -> {frames_dir}")
    
    # Sparse COLMAP model directory
    sparse_target_parent = os.path.join(scene_root, "sparse")
    os.makedirs(sparse_target_parent, exist_ok=True)
    
    sparse_link = os.path.join(sparse_target_parent, "0")
    if os.path.islink(sparse_link):
        os.unlink(sparse_link)
    elif os.path.exists(sparse_link):
        shutil.rmtree(sparse_link)
        
    sfm_sparse_src = find_best_sparse_model(os.path.join(sfm_dir, "sparse"))
    if not os.path.exists(sfm_sparse_src) or sfm_sparse_src == os.path.join(sfm_dir, "sparse"):
        sfm_sparse_src = os.path.join(sfm_dir, "sparse/0")
        if not os.path.exists(sfm_sparse_src):
            sfm_sparse_src = os.path.join(sfm_dir, "sparse")
        
    shutil.copytree(sfm_sparse_src, sparse_link)
    print(f"Copied sparse model to workspace: {sparse_link} From {sfm_sparse_src}")
    
    # Setup masks directories (we assume object ID 000 for our tracked segment)
    mask_levels = ["default", "middle", "small"]
    for lvl in mask_levels:
        lvl_dir = os.path.join(scene_root, f"multiview_masks_{lvl}")
        clean_and_create_dir(lvl_dir)
        os.makedirs(os.path.join(lvl_dir, "000"), exist_ok=True)

    # 2. Get and sort frames
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")) + 
                    glob.glob(os.path.join(frames_dir, "*.jpeg")) + 
                    glob.glob(os.path.join(frames_dir, "*.png")))
    num_frames = len(frames)
    print(f"Found {num_frames} frames in {frames_dir}.")
    
    if num_frames == 0:
        print("Error: No frames found to process.")
        return

    # 3. Process train/test split files
    train_txt_path = os.path.join(scene_root, "train.txt")
    test_txt_path = os.path.join(scene_root, "test.txt")
    
    train_frames = []
    test_frames = []
    fixed_eval_frames = set()
    if eval_frames_path and os.path.isfile(eval_frames_path):
        with open(eval_frames_path, encoding="utf-8") as handle:
            fixed_eval_frames = {line.strip() for line in handle if line.strip()}
        missing_eval_frames = fixed_eval_frames.difference({os.path.basename(path) for path in frames})
        if missing_eval_frames:
            raise ValueError(
                f"Evaluation split contains {len(missing_eval_frames)} images not present in STS input: "
                f"{sorted(missing_eval_frames)[:5]}"
            )
    
    for idx, frame_path in enumerate(frames):
        basename = os.path.basename(frame_path)
        if fixed_eval_frames:
            if basename in fixed_eval_frames:
                test_frames.append(basename)
            else:
                train_frames.append(basename)
        elif num_frames < 20:
            # Short video sequence: put everything in train and test
            train_frames.append(basename)
            test_frames.append(basename)
        else:
            # Hold out every 10th frame for validation
            if idx % 10 == 0:
                test_frames.append(basename)
            else:
                train_frames.append(basename)
                
    with open(train_txt_path, "w") as f:
        f.write("\n".join(train_frames) + "\n")
        
    with open(test_txt_path, "w") as f:
        f.write("\n".join(test_frames) + "\n")
        
    print(f"Split completed: written {len(train_frames)} to train.txt, {len(test_frames)} to test.txt")

    # 4. Copy and resize/format multi-level masks
    print("Formatting hierarchical masks for STS loader requirements...")
    hierarchical_nonempty = count_nonempty_hierarchical_masks(masks_dir, level="middle")
    best_attempt_dir, best_attempt_nonempty = find_best_attempt_dir(masks_dir)

    use_attempt_masks = hierarchical_nonempty == 0 and best_attempt_dir is not None and best_attempt_nonempty > 0
    if use_attempt_masks:
        print(
            f"Warning: Hierarchical masks appear empty in {masks_dir}. "
            f"Using best attempt fallback: {best_attempt_dir} ({best_attempt_nonempty} non-empty frames)."
        )

    for idx, frame_path in enumerate(frames):
        frame_name = os.path.basename(frame_path)
        image_stem = os.path.splitext(frame_name)[0]
        
        # Frame index corresponds to the subdirectory name structure (padded to 5 digits)
        frame_subdir = os.path.join(masks_dir, f"frame_{idx:05d}")
        
        if use_attempt_masks:
            flat_png = os.path.join(best_attempt_dir, f"frame_{idx:05d}_obj_001.png")
            if os.path.exists(flat_png):
                base_mask = cv2.imread(flat_png, cv2.IMREAD_GRAYSCALE)
            else:
                base_mask = None

            if base_mask is None:
                frame_img = cv2.imread(frame_path)
                h, w = frame_img.shape[:2] if frame_img is not None else (768, 1024)
                base_mask = np.zeros((h, w), dtype=np.uint8)

            masks_by_level = make_hierarchical_masks(base_mask, kernel_size=5)
        else:
            masks_by_level = {}
            for lvl in mask_levels:
                src_png = os.path.join(frame_subdir, f"{lvl}.png")
                mask = cv2.imread(src_png, cv2.IMREAD_GRAYSCALE) if os.path.exists(src_png) else None
                if mask is None:
                    frame_img = cv2.imread(frame_path)
                    h, w = frame_img.shape[:2] if frame_img is not None else (768, 1024)
                    mask = np.zeros((h, w), dtype=np.uint8)
                masks_by_level[lvl] = to_binary_mask(mask)

        # Build output paths for each level
        for lvl in mask_levels:
            dst_png = os.path.join(scene_root, f"multiview_masks_{lvl}", "000", f"{image_stem}.png")
            cv2.imwrite(dst_png, masks_by_level[lvl])
                
    print("Hierarchical mask mapping complete. Prepared directory shapes: ")
    print(f" - /data/05_3dgs/multiview_masks_default/000/")
    print(f" - /data/05_3dgs/multiview_masks_middle/000/")
    print(f" - /data/05_3dgs/multiview_masks_small/000/")
    print("Successfully structured active reconstruction workspace.")

if __name__ == "__main__":
    main()
