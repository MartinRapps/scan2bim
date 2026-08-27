#!/usr/bin/env bash
set -Eeuo pipefail

# Sequential, isolated experiment matrix for camera models, resolutions and
# object-only Gaussian/SuGaR stages. It never runs experiments in parallel and
# never deletes raw input or the Hugging Face cache.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export HOST_UID="${HOST_UID:-$(id -u)}"
export HOST_GID="${HOST_GID:-$(id -g)}"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.sugar-dev.yml)
BASE_COMPOSE=(docker compose -f docker-compose.yml)
BATCH_ID="${MATRIX_BATCH_ID:-matrix_$(date +%Y%m%d_%H%M%S)}"
BATCH_ROOT="data/10_runs/$BATCH_ID"
MATRIX_CONFIG="${MATRIX_CONFIG:-tools/experiment_matrix.tsv}"
MATRIX_INPUT_VIDEO="${MATRIX_INPUT_VIDEO:-}"
MATRIX_PROMPT="${MATRIX_PROMPT:-pipe}"
MATRIX_FRAME_STEP="${MATRIX_FRAME_STEP:-1}"
MATRIX_FPS_LIST="${MATRIX_FPS_LIST:-5,2}"
MATRIX_FPS=5
MATRIX_MAX_EMPTY_MASK_FRACTION="${MATRIX_MAX_EMPTY_MASK_FRACTION:-0.30}"
MATRIX_SIFT_FEATURES="${MATRIX_SIFT_FEATURES:-4096}"
MATRIX_SEQUENTIAL_OVERLAP="${MATRIX_SEQUENTIAL_OVERLAP:-15}"
MATRIX_GUIDED_MATCHING="${MATRIX_GUIDED_MATCHING:-0}"
MATRIX_SIFT_PEAK_THRESHOLD="${MATRIX_SIFT_PEAK_THRESHOLD:-0.003}"
MATRIX_STS_ITERATIONS="${MATRIX_STS_ITERATIONS:-7000}"
MATRIX_STS_STAGE2_ITERS="${MATRIX_STS_STAGE2_ITERS:-5000}"
MATRIX_MESH_VERTICES="${MATRIX_MESH_VERTICES:-200000}"
MATRIX_SURFACE_SAMPLE_COUNT="${MATRIX_SURFACE_SAMPLE_COUNT:-5000000}"
MATRIX_SURFACE_SAMPLE_SEED="${MATRIX_SURFACE_SAMPLE_SEED:-42}"
MATRIX_STOP_ON_ERROR="${MATRIX_STOP_ON_ERROR:-0}"
MATRIX_KEEP_LIVE="${MATRIX_KEEP_LIVE:-0}"
MATRIX_DRY_RUN=0
MATRIX_ONLY_RESOLUTION="${MATRIX_ONLY_RESOLUTION:-}"
MATRIX_ONLY_VARIANT="${MATRIX_ONLY_VARIANT:-}"
MATRIX_ONLY_FPS="${MATRIX_ONLY_FPS:-}"
MATRIX_MASK_ONLY="${MATRIX_MASK_ONLY:-0}"

usage() {
    cat <<'EOF'
Usage: ./tools/run_experiment_matrix.sh [options]

Runs every configured camera/mesh experiment at 5 FPS and 2 FPS, and at
1280x720, 960x540 and 640x360.
Each run is sequential, archived below data/10_runs/<batch>, and cleaned before
 the next run. Raw input and data/hf_cache are never deleted.

Options:
    --dry-run                 Print the complete matrix without running it.
    --resolution ID           Run only 720p, qhd or low.
    --fps VALUE               Run only one FPS value, for example 5 or 2.
    --mask-only               Stop after ideal-mask coverage; do not run STS.
    --variant ID              Run only one ID from tools/experiment_matrix.tsv.
    --config FILE             Use another TSV matrix configuration.
    --keep-live               Keep generated data after each experiment.
    --stop-on-error           Stop after the first failed experiment.
                            Without this option, failed experiments are archived,
                            cleaned up and skipped automatically.
    --help                    Show this help.

Useful environment variables:
    MATRIX_INPUT_VIDEO=/absolute/or/data/01_raw/video.mp4
    MATRIX_PROMPT=pipe
    MATRIX_FPS_LIST=5,2
    MATRIX_STOP_ON_ERROR=0    Continue after failed experiments (default).
    MATRIX_BATCH_ID=matrix_name
    MATRIX_REFINEMENT_TIME=short|medium|long (default: per TSV)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) MATRIX_DRY_RUN=1; shift ;;
        --resolution) MATRIX_ONLY_RESOLUTION="${2:?missing resolution}"; shift 2 ;;
        --fps) MATRIX_ONLY_FPS="${2:?missing fps}"; shift 2 ;;
        --mask-only) MATRIX_MASK_ONLY=1; shift ;;
        --variant) MATRIX_ONLY_VARIANT="${2:?missing variant}"; shift 2 ;;
        --config) MATRIX_CONFIG="${2:?missing config}"; shift 2 ;;
        --keep-live) MATRIX_KEEP_LIVE=1; shift ;;
        --stop-on-error) MATRIX_STOP_ON_ERROR=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ ! -f "$MATRIX_CONFIG" ]]; then
    echo "Matrix config not found: $MATRIX_CONFIG" >&2
    exit 2
fi
if [[ ! "$MATRIX_FRAME_STEP" =~ ^[1-9][0-9]*$ ]]; then
    echo "MATRIX_FRAME_STEP must be positive." >&2
    exit 2
fi
IFS=',' read -r -a MATRIX_FPS_VALUES <<< "$MATRIX_FPS_LIST"
if [[ ${#MATRIX_FPS_VALUES[@]} -eq 0 ]]; then
    echo "MATRIX_FPS_LIST must contain at least one FPS value." >&2
    exit 2
fi
for fps_value in "${MATRIX_FPS_VALUES[@]}"; do
    if [[ ! "$fps_value" =~ ^[1-9][0-9]*([.][0-9]+)?$ ]]; then
        echo "Invalid FPS value in MATRIX_FPS_LIST: $fps_value" >&2
        exit 2
    fi
done
if [[ ! "$MATRIX_MAX_EMPTY_MASK_FRACTION" =~ ^0([.][0-9]+)?$ ]]; then
    echo "MATRIX_MAX_EMPTY_MASK_FRACTION must be a decimal fraction in [0, 1)." >&2
    exit 2
fi

if [[ -z "$MATRIX_INPUT_VIDEO" ]]; then
    for candidate in data/01_raw/*.mp4 data/01_raw/*.mov; do
        [[ -f "$candidate" ]] || continue
        [[ "$(basename "$candidate")" == "output.mp4" ]] && continue
        MATRIX_INPUT_VIDEO="$candidate"
        break
    done
fi
if [[ -z "$MATRIX_INPUT_VIDEO" ]]; then
    echo "No raw input video found. Set MATRIX_INPUT_VIDEO explicitly." >&2
    exit 2
fi
case "$MATRIX_INPUT_VIDEO" in
    data/*) INPUT_VIDEO_CONTAINER="/data/${MATRIX_INPUT_VIDEO#data/}" ;;
    "$PROJECT_ROOT"/data/*) INPUT_VIDEO_CONTAINER="/data/${MATRIX_INPUT_VIDEO#"$PROJECT_ROOT"/data/}" ;;
    *) echo "MATRIX_INPUT_VIDEO must be below this project's data/ directory." >&2; exit 2 ;;
esac

mkdir -p "$BATCH_ROOT"
exec > >(tee -a "$BATCH_ROOT/matrix.log") 2>&1

# Resolution target is the longest image side. For the current 16:9 source this
# yields exactly 1280x720, 960x540 and 640x360.
RESOLUTION_ROWS=(
    "720p|1280|1280x720"
    "qhd|960|960x540"
    "low|640|640x360"
)
MATRIX_VIDEO_CONTAINER=""

copy_if_exists() {
    local source="$1"
    local destination="$2"
    if [[ -e "$source" ]]; then
        mkdir -p "$(dirname "$destination")"
        cp -a "$source" "$destination"
    fi
}

relative_data_path() {
    local path="$1"
    case "$path" in
        data/*) printf '/data/%s\n' "${path#data/}" ;;
        "$PROJECT_ROOT"/data/*) printf '/data/%s\n' "${path#"$PROJECT_ROOT"/data/}" ;;
        *) echo "Path is not below data/: $path" >&2; return 1 ;;
    esac
}

resolve_path_in_data() {
    local path="$1"
    case "$path" in
        data/*) printf '%s\n' "$path" ;;
        "$PROJECT_ROOT"/data/*) printf 'data/%s\n' "${path#"$PROJECT_ROOT"/data/}" ;;
        *) printf '%s\n' "$path" ;;
    esac
}

write_parameters() {
    local output="$1" resolution_id="$2" max_side="$3" image_size="$4" variant="$5" camera="$6" mesh_mode="$7" coarse="$8" refinement="$9"
    cat > "$output" <<EOF
{
  "batch_id": "${BATCH_ID}",
    "resolution_id": "${resolution_id}",
    "fps": ${MATRIX_FPS},
  "frame_max_side": ${max_side},
    "max_empty_mask_fraction": ${MATRIX_MAX_EMPTY_MASK_FRACTION},
    "mask_only": ${MATRIX_MASK_ONLY},
  "expected_image_size": "${image_size}",
    "prompt": "${MATRIX_PROMPT}",
  "camera_model": "${camera}",
  "mesh_mode": "${mesh_mode}",
  "coarse_iterations": "${coarse}",
  "refinement_time": "${refinement}",
  "sts_iterations": ${MATRIX_STS_ITERATIONS},
  "sts_stage2_iterations": ${MATRIX_STS_STAGE2_ITERS},
  "sift_features": ${MATRIX_SIFT_FEATURES},
  "sequential_overlap": ${MATRIX_SEQUENTIAL_OVERLAP},
  "guided_matching": ${MATRIX_GUIDED_MATCHING},
  "sift_peak_threshold": ${MATRIX_SIFT_PEAK_THRESHOLD},
  "mesh_vertices": ${MATRIX_MESH_VERTICES},
  "surface_sample_count": ${MATRIX_SURFACE_SAMPLE_COUNT},
  "surface_sample_seed": ${MATRIX_SURFACE_SAMPLE_SEED},
  "evaluation_scope": "object_masked_only"
}
EOF
}

prepare_matrix_video() {
    local experiment_root="$1" image_size="$2" input_path="$3"
    local target_width="${image_size%x*}"
    local target_height="${image_size#*x}"
    local output_host="$experiment_root/input_${MATRIX_FPS}fps.mp4"
    local output_container="/data/${output_host#data/}"
    mkdir -p "$(dirname "$output_host")"
    echo "Preparing matrix video: ${image_size} at ${MATRIX_FPS} FPS -> $output_host" >&2
    "${BASE_COMPOSE[@]}" run --rm sam3-preprocess ffmpeg -y \
        -i "$input_path" \
        -vf "scale=${target_width}:${target_height}:force_original_aspect_ratio=decrease,pad=${target_width}:${target_height}:(ow-iw)/2:(oh-ih)/2:black,fps=${MATRIX_FPS}" \
        -c:v libx264 -crf 18 -preset medium -an \
        "$output_container"
    [[ -s "$output_host" ]] || {
        echo "Matrix video was not created: $output_host" >&2
        return 1
    }
    MATRIX_VIDEO_CONTAINER="$output_container"
}

parse_resolution() {
    local resolution_id="$1"
    local row id max_side image_size
    for row in "${RESOLUTION_ROWS[@]}"; do
        IFS='|' read -r id max_side image_size <<< "$row"
        if [[ "$id" == "$resolution_id" ]]; then
            printf '%s|%s\n' "$max_side" "$image_size"
            return 0
        fi
    done
    echo "Unknown resolution: $resolution_id" >&2
    return 1
}

run_review() {
    local frames_dir="$1" masks_dir="$2" output_dir="$3" manifest="$4"
    "${BASE_COMPOSE[@]}" run --rm sam3-preprocess \
        python3 /app/tools/export_mask_review_samples.py \
        --frames-dir "$frames_dir" \
        --masks-dir "$masks_dir" \
        --mask-name middle \
        --output-dir "$output_dir" \
        --non-interactive \
        --manifest "$manifest"
}

render_standard_splat() {
    local model_dir="$1" iteration="$2"
    "${COMPOSE[@]}" run --rm sugar-meshing \
        python3 /opt/sugar/gaussian_splatting/render.py \
        -s /data/05_3dgs \
        -m "$model_dir" \
        --iteration "$iteration" \
        --skip_train \
        --quiet \
        --eval
}

evaluate_render() {
    local renders="$1" ground_truth="$2" output="$3"
    "${BASE_COMPOSE[@]}" run --rm sts-training \
        python3 /app/src/python/evaluate_masked_splat_metrics.py \
        --renders-dir "$renders" \
        --ground-truth-dir "$ground_truth" \
        --masks-dir /data/03_masks \
        --eval-frames /data/05_3dgs/eval_frames.txt \
        --output "$output" \
        --mask-level default \
        --require-lpips
}

archive_live_workspace() {
    local experiment_root="$1"
    mkdir -p "$experiment_root/live"
    copy_if_exists data/02_frames "$experiment_root/live/frames"
    copy_if_exists data/03_masks "$experiment_root/live/masks_ideal"
    copy_if_exists data/04_sfm "$experiment_root/live/colmap"
    copy_if_exists data/05_3dgs "$experiment_root/live/sts"
    copy_if_exists data/06_mesh "$experiment_root/live/mesh"
    copy_if_exists data/07_centerline "$experiment_root/live/centerline"
    copy_if_exists data/08_gis "$experiment_root/live/gis"
    copy_if_exists data/09_evaluation "$experiment_root/live/evaluation"
    copy_if_exists data/sugar_output "$experiment_root/live/sugar_output"
}

archive_latest_pipeline_log() {
    local experiment_root="$1"
    local latest
    latest="$(find data/10_runs -mindepth 1 -maxdepth 1 -type d ! -path "data/10_runs/$BATCH_ID" -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2- || true)"
    if [[ -n "$latest" && -d "$latest" ]]; then
        copy_if_exists "$latest" "$experiment_root/pipeline_run"
    fi
}

write_result_manifest() {
    local output="$1" status="$2" resolution_id="$3" variant="$4" camera="$5" mesh_mode="$6" message="$7"
    cat > "$output" <<EOF
{
  "batch_id": "${BATCH_ID}",
  "status": "${status}",
  "resolution_id": "${resolution_id}",
    "fps": ${MATRIX_FPS},
  "variant": "${variant}",
  "camera_model": "${camera}",
  "mesh_mode": "${mesh_mode}",
  "message": "${message}",
  "evaluation_scope": "object_masked_only",
  "full_frame_metrics": false
}
EOF
}

write_experiment_report() {
    local experiment_root="$1" status="$2" resolution_id="$3" variant="$4" camera="$5" mesh_mode="$6" message="$7"
    cat > "$experiment_root/run.md" <<EOF
# Experiment $resolution_id / $variant

- **Status:** $status
- **Kameramodell:** $camera
- **Meshroute:** $mesh_mode
- **Auflösung:** $resolution_id
- **FPS:** ${MATRIX_FPS}
- **Auswertungsumfang:** object-masked-only
- **Full-frame-Metriken:** deaktiviert
- **Nachricht:** $message

## Archivierte Ergebnisse

- Parameter: parameters.json
- Matrix-Log: matrix.log
- Pipeline-Log: pipeline_run/
- Maskenreview roh/ideal: masks/review_raw/, masks/review_ideal/
- COLMAP und SfM: live/colmap/
- STS und Splats: live/sts/, splats/
- Mesh/Postprocessing: live/mesh/, live/centerline/, live/gis/
- Maskierte Metriken: metrics/sts_masked.json, metrics/sugar_refined_masked.json
EOF
}

run_one() {
    local resolution_id="$1" max_side="$2" image_size="$3" fps_id="$4" run_fps="$5" variant="$6" camera="$7" mesh_mode="$8" coarse="$9" refinement="${10}"
    MATRIX_FPS="$run_fps"
    local experiment_root="$BATCH_ROOT/$fps_id/$resolution_id/$variant"
    local experiment_container_root="/data/${experiment_root#data/}"
    local export_name="matrix_${BATCH_ID}_${fps_id}_${resolution_id}_${variant}"
    local run_tag="$export_name"
    local resolution_info
    mkdir -p "$experiment_root" "$experiment_root/masks/raw" "$experiment_root/metrics"
    write_parameters "$experiment_root/parameters.json" "$resolution_id" "$max_side" "$image_size" "$variant" "$camera" "$mesh_mode" "$coarse" "$refinement"
    echo
    echo "===== MATRIX START: $fps_id / $resolution_id / $variant ($camera / $mesh_mode) ====="

    ./clean_data_interactive.sh --matrix-reset

    prepare_matrix_video "$experiment_root" "$image_size" "$INPUT_VIDEO_CONTAINER"
    local_matrix_video="$MATRIX_VIDEO_CONTAINER"

    echo "[1/11] SAM3 frame extraction and segmentation at max side $max_side..."
    "${BASE_COMPOSE[@]}" run --rm \
        -e SAM3_FRAME_MAX_SIDE="$max_side" \
        -e SAM3_FRAME_STEP="$MATRIX_FRAME_STEP" \
        sam3-preprocess python3 /app/src/python/extract_masks_notebook_flow.py \
        --prompt "$MATRIX_PROMPT" \
        --input-path "$local_matrix_video" \
        --frames-dir /data/02_frames \
        --masks-dir /data/03_masks \
        --frame-max-side "$max_side" \
        --frame-step "$MATRIX_FRAME_STEP"

    cp -a data/03_masks/. "$experiment_root/masks/raw/"
    echo "[1b/11] Validating mask coverage (abort at >= ${MATRIX_MAX_EMPTY_MASK_FRACTION} empty masks)..."
    "${BASE_COMPOSE[@]}" run --rm sam3-preprocess \
        python3 /app/src/python/validate_mask_coverage.py \
        --frames-dir /data/02_frames \
        --masks-dir /data/03_masks \
        --mask-name middle \
        --max-empty-fraction "$MATRIX_MAX_EMPTY_MASK_FRACTION" \
        --report "$experiment_container_root/masks/raw/mask_coverage_report.json"
    run_review /data/02_frames /data/03_masks \
        "$experiment_container_root/masks/review_raw" \
        "$experiment_container_root/masks/review_raw/review_manifest.json"

    echo "[2/11] COLMAP $camera..."
    "${BASE_COMPOSE[@]}" run --rm \
        -e COLMAP_CAMERA_MODEL="$camera" \
        -e COLMAP_MAX_FEATURES="$MATRIX_SIFT_FEATURES" \
        -e COLMAP_SEQUENTIAL_OVERLAP="$MATRIX_SEQUENTIAL_OVERLAP" \
        -e COLMAP_GUIDED_MATCHING="$MATRIX_GUIDED_MATCHING" \
        -e COLMAP_SIFT_PEAK_THRESHOLD="$MATRIX_SIFT_PEAK_THRESHOLD" \
        colmap-sfm /app/src/scripts/run_sfm.sh

    echo "[3/11] Warp masks into the ideal STS image domain..."
    "${BASE_COMPOSE[@]}" run --rm sam3-preprocess \
        python3 /app/src/python/warp_masks_to_undistorted.py \
        --raw-masks-dir /data/03_masks \
        --output-dir "$experiment_container_root/masks/ideal" \
        --raw-sfm-txt /data/04_sfm/sparse_txt \
        --ideal-sfm-txt /data/04_sfm/undistorted/sparse_txt \
        --raw-images-dir /data/02_frames \
        --ideal-images-dir /data/04_sfm/undistorted/images \
        --report "$experiment_container_root/masks/mask_warp_report.json"

    run_review /data/04_sfm/undistorted/images \
        "$experiment_container_root/masks/ideal" \
        "$experiment_container_root/masks/review_ideal" \
        "$experiment_container_root/masks/review_ideal/review_manifest.json"
    echo "[4b/11] Validating warped-mask coverage (abort at >= ${MATRIX_MAX_EMPTY_MASK_FRACTION} empty masks)..."
    "${BASE_COMPOSE[@]}" run --rm sam3-preprocess \
        python3 /app/src/python/validate_mask_coverage.py \
        --frames-dir /data/04_sfm/undistorted/images \
        --masks-dir "$experiment_container_root/masks/ideal" \
        --mask-name middle \
        --max-empty-fraction "$MATRIX_MAX_EMPTY_MASK_FRACTION" \
        --report "$experiment_container_root/masks/ideal/mask_coverage_report.json"
    echo "[4c/11] Fixed evaluation split (non-empty ideal masks)..."
    "${BASE_COMPOSE[@]}" run --rm sam3-preprocess \
        python3 /app/src/python/create_eval_split.py \
        --images-dir /data/04_sfm/undistorted/images \
        --masks-dir "$experiment_container_root/masks/ideal" \
        --mask-name middle \
        --output /data/05_3dgs/eval_frames.txt \
        --stride 8
    if [[ "$MATRIX_MASK_ONLY" -eq 1 ]]; then
        write_result_manifest "$experiment_root/manifest.json" success "$resolution_id" "$variant" "$camera" "$mesh_mode" "mask coverage passed; STS intentionally skipped"
        write_experiment_report "$experiment_root" success "$resolution_id" "$variant" "$camera" "$mesh_mode" "mask coverage passed; STS intentionally skipped"
        ./clean_data_interactive.sh --matrix-reset
        echo "[MASK-ONLY END] $fps_id / $resolution_id / $variant"
        return 0
    fi
    rm -rf data/03_masks
    mkdir -p data/03_masks
    cp -a "$experiment_root/masks/ideal"/. data/03_masks/

    echo "[5/11] STS + selected mesh route..."
    export EVAL_FRAMES_PATH=/data/05_3dgs/eval_frames.txt
    export SUGAR_EVAL_FRAMES_PATH=/data/05_3dgs/eval_frames.txt
    export STS_IMAGES_DIR=/data/04_sfm/undistorted/images
    export STS_SFM_DIR=/data/04_sfm/undistorted
    export STS_MASKS_DIR=/data/03_masks
    export COLMAP_CAMERA_MODEL="$camera"
    export SAM3_FRAME_MAX_SIDE="$max_side"
    export MATRIX_BATCH_ID="$BATCH_ID"
    export MATRIX_RESOLUTION_ID="$resolution_id"
    export MATRIX_VARIANT="$variant"
    AUTOPILOT=true \
    FRAME_PROFILE_SCOPE=all \
    TEXT_PROMPT="$MATRIX_PROMPT" \
    ITERATIONS="$MATRIX_STS_ITERATIONS" \
    STAGE2_ITERS="$MATRIX_STS_STAGE2_ITERS" \
    SUGAR_MESH_MODE="$mesh_mode" \
    COARSE_ITERATIONS="${coarse:-}" \
    REFINEMENT_TIME="$refinement" \
    MESH_VERTICES="$MATRIX_MESH_VERTICES" \
    SURFACE_SAMPLE_COUNT="$MATRIX_SURFACE_SAMPLE_COUNT" \
    SURFACE_SAMPLE_SEED="$MATRIX_SURFACE_SAMPLE_SEED" \
    SUGAR_RUN_TAG="$run_tag" \
    SUGAR_MESH_EXPORT_NAME="$export_name" \
    STOP_AFTER_COARSE_MESH=0 \
    RUN_CONSENSUS_CROP=0 \
    ./run_pipeline.sh --from sts

    echo "[6/11] Archive STS and mesh outputs before rendering..."
    archive_live_workspace "$experiment_root"
    archive_latest_pipeline_log "$experiment_root"
    cp -f "$BATCH_ROOT/matrix.log" "$experiment_root/matrix.log"

    echo "[7/11] Render STS test Splat..."
    render_standard_splat /data/05_3dgs/output "$MATRIX_STS_ITERATIONS"
    mkdir -p "$experiment_root/splats/sts"
    cp -a "data/05_3dgs/output/test/ours_${MATRIX_STS_ITERATIONS}" "$experiment_root/splats/sts/"
    evaluate_render \
        /data/05_3dgs/output/test/ours_${MATRIX_STS_ITERATIONS}/renders \
        /data/05_3dgs/output/test/ours_${MATRIX_STS_ITERATIONS}/gt \
        "$experiment_container_root/metrics/sts_masked.json"

    if [[ "$mesh_mode" == "sugar_coarse" ]]; then
        echo "[8/11] Render SuGaR Coarse Splat on the fixed test split..."
        coarse_checkpoint="$(find "data/sugar_output/$run_tag/coarse" -type f -name '*.pt' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2- || true)"
        if [[ -n "$coarse_checkpoint" && -s "$coarse_checkpoint" ]]; then
            "${COMPOSE[@]}" run --rm sugar-meshing \
                python3 /app/src/python/render_sugar_checkpoint.py \
                --scene-path /data/05_3dgs \
                --checkpoint-path "/data/05_3dgs/masked_sugar_input/$run_tag/" \
                --coarse-model-path "/data/${coarse_checkpoint#data/}" \
                --iteration "$MATRIX_STS_ITERATIONS" \
                --output-dir "$experiment_container_root/splats/sugar_coarse"
            evaluate_render \
                "$experiment_container_root/splats/sugar_coarse/renders" \
                "$experiment_container_root/splats/sugar_coarse/gt" \
                "$experiment_container_root/metrics/sugar_coarse_masked.json"
            mkdir -p "$experiment_root/sugar"
            cp -a "$coarse_checkpoint" "$experiment_root/sugar/"
        else
            echo "SuGaR coarse checkpoint not available; recording explicit skip."
            printf '{"status":"skipped","reason":"no coarse checkpoint exported"}\n' > "$experiment_root/metrics/sugar_coarse_masked.json"
        fi

        echo "[9/11] Render SuGaR refined Splat when a refined PLY exists..."
        refined_ply="data/06_mesh/$export_name/refined.ply"
        if [[ -s "$refined_ply" ]]; then
            render_model="data/10_runs/$BATCH_ID/$resolution_id/$variant/sugar_render_model"
            mkdir -p "$render_model/point_cloud/iteration_${MATRIX_STS_ITERATIONS}"
            cp "$refined_ply" "$render_model/point_cloud/iteration_${MATRIX_STS_ITERATIONS}/point_cloud.ply"
            render_standard_splat "$experiment_container_root/sugar_render_model" "$MATRIX_STS_ITERATIONS"
            evaluate_render \
                "$experiment_container_root/sugar_render_model/test/ours_${MATRIX_STS_ITERATIONS}/renders" \
                "$experiment_container_root/sugar_render_model/test/ours_${MATRIX_STS_ITERATIONS}/gt" \
                "$experiment_container_root/metrics/sugar_refined_masked.json"
        else
            echo "SuGaR refined PLY not available; recording explicit skip."
            printf '{"status":"skipped","reason":"no refined.ply exported"}\n' > "$experiment_root/metrics/sugar_refined_masked.json"
        fi
    else
        printf '{"status":"not_applicable","reason":"variant A uses the STS Splat directly"}\n' > "$experiment_root/metrics/sugar_refined_masked.json"
    fi

    echo "[10/11] Copy final renders and metrics into archive..."
    copy_if_exists data/05_3dgs/eval_frames.txt "$experiment_root/evaluation/eval_frames.txt"
    cp -f "$BATCH_ROOT/matrix.log" "$experiment_root/run.log"
    write_result_manifest "$experiment_root/manifest.json" success "$resolution_id" "$variant" "$camera" "$mesh_mode" "completed"
    write_experiment_report "$experiment_root" success "$resolution_id" "$variant" "$camera" "$mesh_mode" "completed"

    echo "[11/11] Cleanup live generated data..."
    if [[ "$MATRIX_KEEP_LIVE" -eq 0 ]]; then
        ./clean_data_interactive.sh --matrix-reset
    else
        echo "MATRIX_KEEP_LIVE=1: live generated data retained."
    fi
    echo "[12/12] MATRIX END: $resolution_id / $variant"
}

mapfile -t MATRIX_ROWS < <(grep -vE '^\s*(#|$)' "$MATRIX_CONFIG")
if [[ ${#MATRIX_ROWS[@]} -eq 0 ]]; then
    echo "Matrix config has no experiments: $MATRIX_CONFIG" >&2
    exit 2
fi

if [[ "$MATRIX_DRY_RUN" -eq 1 ]]; then
    echo "Batch: $BATCH_ID"
    echo "Input: $MATRIX_INPUT_VIDEO"
    for fps_value in "${MATRIX_FPS_VALUES[@]}"; do
        [[ -n "$MATRIX_ONLY_FPS" && "$MATRIX_ONLY_FPS" != "$fps_value" ]] && continue
        for row in "${RESOLUTION_ROWS[@]}"; do
            IFS='|' read -r resolution_id max_side image_size <<< "$row"
            [[ -n "$MATRIX_ONLY_RESOLUTION" && "$MATRIX_ONLY_RESOLUTION" != "$resolution_id" ]] && continue
            for matrix_row in "${MATRIX_ROWS[@]}"; do
                read -r variant camera mesh_mode coarse refinement _ <<< "$matrix_row"
                [[ -z "$variant" || "$variant" == \#* ]] && continue
                [[ -n "$MATRIX_ONLY_VARIANT" && "$MATRIX_ONLY_VARIANT" != "$variant" ]] && continue
                echo "${fps_value}fps $resolution_id ($image_size): $variant camera=$camera mesh=$mesh_mode coarse=$coarse refinement=$refinement"
            done
        done
    done
    exit 0
fi

TOTAL=0
FAILED=0
for fps_value in "${MATRIX_FPS_VALUES[@]}"; do
    [[ -n "$MATRIX_ONLY_FPS" && "$MATRIX_ONLY_FPS" != "$fps_value" ]] && continue
    for row in "${RESOLUTION_ROWS[@]}"; do
        IFS='|' read -r resolution_id max_side image_size <<< "$row"
        [[ -n "$MATRIX_ONLY_RESOLUTION" && "$MATRIX_ONLY_RESOLUTION" != "$resolution_id" ]] && continue
        for matrix_row in "${MATRIX_ROWS[@]}"; do
            read -r variant camera mesh_mode coarse refinement _ <<< "$matrix_row"
            [[ -z "$variant" || "$variant" == \#* ]] && continue
            [[ -n "$MATRIX_ONLY_VARIANT" && "$MATRIX_ONLY_VARIANT" != "$variant" ]] && continue
            TOTAL=$((TOTAL + 1))
            fps_id="${fps_value}fps"
            # Keep failure manifests/report files tied to the attempted FPS.
            # run_one executes in a strict subshell, so its local assignment
            # cannot update the parent shell after a failure.
            MATRIX_FPS="$fps_value"
            # Do not call run_one directly as the condition of an `if`: Bash then
            # disables errexit throughout the called function. Run the experiment
            # in a dedicated strict subshell and inspect its status afterwards so a
            # failed Docker/Python step cannot continue into later stages.
            set +e
            (
                set -Eeuo pipefail
                run_one "$resolution_id" "$max_side" "$image_size" "$fps_id" "$fps_value" "$variant" "$camera" "$mesh_mode" "$coarse" "$refinement"
            )
            run_status=$?
            set -e
            if [[ "$run_status" -eq 0 ]]; then
                :
            else
                FAILED=$((FAILED + 1))
                experiment_root="$BATCH_ROOT/$fps_id/$resolution_id/$variant"
                mkdir -p "$experiment_root"
                archive_live_workspace "$experiment_root"
                archive_latest_pipeline_log "$experiment_root"
                cp -f "$BATCH_ROOT/matrix.log" "$experiment_root/run.log"
                write_result_manifest "$experiment_root/manifest.json" failed "$resolution_id" "$variant" "$camera" "$mesh_mode" "command failed"
                write_experiment_report "$experiment_root" failed "$resolution_id" "$variant" "$camera" "$mesh_mode" "command failed"
                if [[ "$MATRIX_KEEP_LIVE" -eq 0 ]]; then
                    ./clean_data_interactive.sh --matrix-reset || true
                fi
                if [[ "$MATRIX_STOP_ON_ERROR" -eq 1 ]]; then
                    echo "Stopping after first failed experiment."
                    break 3
                fi
            fi
        done
    done
done

echo "Matrix finished: total=$TOTAL failed=$FAILED batch=$BATCH_ROOT"
if [[ "$FAILED" -gt 0 ]]; then
    exit 1
fi
