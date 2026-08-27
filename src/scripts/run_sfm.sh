#!/bin/bash
set -e

echo "=== Running COLMAP SfM ==="
WORKSPACE_PATH="/data/04_sfm"
IMAGE_PATH="/data/02_frames"
CAMERA_MODEL="${COLMAP_CAMERA_MODEL:-OPENCV}"
MAX_FEATURES="${COLMAP_MAX_FEATURES:-4096}"
SEQUENTIAL_OVERLAP="${COLMAP_SEQUENTIAL_OVERLAP:-15}"
GUIDED_MATCHING="${COLMAP_GUIDED_MATCHING:-0}"
SIFT_PEAK_THRESHOLD="${COLMAP_SIFT_PEAK_THRESHOLD:-0.003}"

mkdir -p $WORKSPACE_PATH

echo "1. Feature extraction..."
echo "   camera_model=${CAMERA_MODEL}, max_features=${MAX_FEATURES}, peak_threshold=${SIFT_PEAK_THRESHOLD}"
colmap feature_extractor \
    --database_path $WORKSPACE_PATH/database.db \
    --image_path $IMAGE_PATH \
    --ImageReader.camera_model "$CAMERA_MODEL" \
    --ImageReader.single_camera 1 \
    --SiftExtraction.max_num_features "$MAX_FEATURES" \
    --SiftExtraction.peak_threshold "$SIFT_PEAK_THRESHOLD"

echo "2. Feature matching (Sequential)..."
echo "   overlap=${SEQUENTIAL_OVERLAP}, guided_matching=${GUIDED_MATCHING}"
colmap sequential_matcher \
    --database_path $WORKSPACE_PATH/database.db \
    --SequentialMatching.overlap "$SEQUENTIAL_OVERLAP" \
    --FeatureMatching.guided_matching "$GUIDED_MATCHING"

echo "3. Mapper..."
mkdir -p $WORKSPACE_PATH/sparse
colmap mapper \
    --database_path $WORKSPACE_PATH/database.db \
    --image_path $IMAGE_PATH \
    --output_path $WORKSPACE_PATH/sparse \
    --Mapper.abs_pose_min_num_inliers 15 \
    --Mapper.min_num_matches 10

echo "4. Export the largest reconstructed point cloud to PLY..."
LARGEST_DIR=""
MAX_SIZE=0

# Find the numeric sub-directory under sparse/ with the largest points3D.bin or points3D.txt
for dir in "$WORKSPACE_PATH"/sparse/*; do
    if [ -d "$dir" ] && [[ "$(basename "$dir")" =~ ^[0-9]+$ ]]; then
        bin_file="$dir/points3D.bin"
        txt_file="$dir/points3D.txt"
        size=0
        if [ -f "$bin_file" ]; then
            size=$(stat -c%s "$bin_file" 2>/dev/null || stat -f%z "$bin_file" 2>/dev/null || echo 0)
        elif [ -f "$txt_file" ]; then
            size=$(stat -c%s "$txt_file" 2>/dev/null || stat -f%z "$txt_file" 2>/dev/null || echo 0)
        fi
        if (( size > MAX_SIZE )); then
            MAX_SIZE=$size
            LARGEST_DIR="$dir"
        fi
    fi
done

# Best input model directory for both PLY and TXT export.
if [ -n "$LARGEST_DIR" ]; then
    BEST_INPUT="$LARGEST_DIR"
elif [ -d "$WORKSPACE_PATH/sparse" ]; then
    echo "No custom sub-models found. Fallback to base sparse directory..."
    BEST_INPUT="$WORKSPACE_PATH/sparse"
else
    BEST_INPUT=""
fi

if [ -n "$BEST_INPUT" ]; then
    echo "Using model: $BEST_INPUT ($MAX_SIZE bytes)"
    colmap model_converter \
        --input_path "$BEST_INPUT" \
        --output_path $WORKSPACE_PATH/points3D.ply \
        --output_type PLY
    # TXT export (cameras.txt + images.txt + points3D.txt) for the GCP
    # registration UI: image marking + triangulation needs the camera
    # intrinsics and poses in a parseable text format.
    mkdir -p $WORKSPACE_PATH/sparse_txt
    colmap model_converter \
        --input_path "$BEST_INPUT" \
        --output_path $WORKSPACE_PATH/sparse_txt \
        --output_type TXT
    echo "Exported cameras/images TXT to $WORKSPACE_PATH/sparse_txt/ for GCP registration."

    # STS only accepts ideal PINHOLE/SIMPLE_PINHOLE camera models. For a
    # distortion-bearing COLMAP model (for example SIMPLE_RADIAL), preserve the
    # original scene for GCP/SfM evaluation and create a separate ideal scene
    # for STS. If the input model is already PINHOLE or SIMPLE_PINHOLE, the
    # images are assumed to have been undistorted before COLMAP and must not be
    # undistorted a second time. In that case we create a pass-through STS scene
    # at the historical 'undistorted' path so downstream scripts keep one stable
    # data contract.
    STS_SCENE_DIR="$WORKSPACE_PATH/undistorted"
    rm -rf "$STS_SCENE_DIR"
    mkdir -p "$STS_SCENE_DIR"
    case "$CAMERA_MODEL" in
        PINHOLE|SIMPLE_PINHOLE)
            echo "5. Camera model is already ideal ($CAMERA_MODEL); skipping image undistortion."
            mkdir -p "$STS_SCENE_DIR/images" "$STS_SCENE_DIR/sparse"
            cp -a "$IMAGE_PATH"/. "$STS_SCENE_DIR/images"/
            cp -a "$BEST_INPUT"/. "$STS_SCENE_DIR/sparse"/
            ;;
        *)
            echo "5. Undistorting images and camera model for STS..."
            colmap image_undistorter \
                --image_path "$IMAGE_PATH" \
                --input_path "$BEST_INPUT" \
                --output_path "$STS_SCENE_DIR" \
                --output_type COLMAP \
                --copy_policy COPY
            ;;
    esac
    if [[ ! -d "$STS_SCENE_DIR/images" || \
          ! -f "$STS_SCENE_DIR/sparse/cameras.bin" || \
          ! -f "$STS_SCENE_DIR/sparse/images.bin" || \
          ! -f "$STS_SCENE_DIR/sparse/points3D.bin" ]]; then
        echo "Error: No usable ideal STS scene was created." >&2
        exit 1
    fi
    mkdir -p "$STS_SCENE_DIR/sparse_txt"
    colmap model_converter \
        --input_path "$STS_SCENE_DIR/sparse" \
        --output_path "$STS_SCENE_DIR/sparse_txt" \
        --output_type TXT
    echo "STS scene written to $STS_SCENE_DIR (ideal pinhole cameras)."
else
    echo "Warning: No sparse model folders found."
fi

echo "COLMAP SfM completed."
