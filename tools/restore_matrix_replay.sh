#!/usr/bin/env bash
set -Eeuo pipefail

# Restore only the inputs needed to replay the SuGaR stage of an archived
# matrix experiment. The archive itself is never modified and raw data/cache
# are not touched.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

usage() {
    cat <<'EOF'
Usage: ./tools/restore_matrix_replay.sh data/10_runs/<batch>/<fps>/<resolution>/<variant>

Restores ideal masks, the ideal COLMAP image scene, the STS camera metadata,
the STS and high-opacity PLYs, the fixed evaluation split, and the sparse scene
metadata needed for rendering. It intentionally does not restore raw frames or
rerun SAM3, COLMAP, or STS.
EOF
}

if [[ $# -eq 1 && ("$1" == "--help" || "$1" == "-h") ]]; then
    usage
    exit 0
fi
if [[ $# -ne 1 ]]; then
    usage >&2
    exit 2
fi

ARCHIVE_ROOT="$1"
if [[ ! -d "$ARCHIVE_ROOT/live/masks_ideal" || ! -d "$ARCHIVE_ROOT/live/colmap" ||
    ! -d "$ARCHIVE_ROOT/live/sts/sparse" ||
      ! -f "$ARCHIVE_ROOT/live/sts/output/cameras.json" ||
      ! -f "$ARCHIVE_ROOT/live/sts/eval_frames.txt" ||
    ! -f "$ARCHIVE_ROOT/live/sts/output/point_cloud/iteration_7000/point_cloud.ply" ||
      ! -f "$ARCHIVE_ROOT/live/sts/output/point_cloud/iteration_7000/point_cloud_filtered_opacity999999.ply" ]]; then
    echo "Archive does not contain the required SuGaR replay inputs: $ARCHIVE_ROOT" >&2
    exit 2
fi

for target in data/03_masks data/04_sfm data/05_3dgs; do
    if [[ -n "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
        echo "Refusing to overwrite non-empty directory: $target" >&2
        echo "Clean or archive the live inputs first." >&2
        exit 2
    fi
done

cp -a "$ARCHIVE_ROOT/live/masks_ideal/." data/03_masks/
cp -a "$ARCHIVE_ROOT/live/colmap/." data/04_sfm/
mkdir -p data/05_3dgs/sparse
cp -a "$ARCHIVE_ROOT/live/sts/sparse/." data/05_3dgs/sparse/
mkdir -p data/05_3dgs/output/point_cloud/iteration_7000
cp -a "$ARCHIVE_ROOT/live/sts/output/cameras.json" data/05_3dgs/output/
if [[ -f "$ARCHIVE_ROOT/live/sts/output/cfg_args" ]]; then
    cp -a "$ARCHIVE_ROOT/live/sts/output/cfg_args" data/05_3dgs/output/
fi
cp -a "$ARCHIVE_ROOT/live/sts/output/point_cloud/iteration_7000/point_cloud_filtered_opacity999999.ply" \
    data/05_3dgs/output/point_cloud/iteration_7000/
cp -a "$ARCHIVE_ROOT/live/sts/output/point_cloud/iteration_7000/point_cloud.ply" \
    data/05_3dgs/output/point_cloud/iteration_7000/
cp -a "$ARCHIVE_ROOT/live/sts/eval_frames.txt" data/05_3dgs/eval_frames.txt

# SuGaR enumerates source_path/images to determine the image extension. A
# relative link works both on the host and inside the /data Docker mount.
ln -s ../04_sfm/undistorted/images data/05_3dgs/images

mask_count=$(find data/03_masks -name middle.png -type f | wc -l)
image_count=$(find data/04_sfm/undistorted/images -maxdepth 1 -type f | wc -l)
eval_count=$(wc -l < data/05_3dgs/eval_frames.txt)
printf 'Replay inputs restored from %s\n' "$ARCHIVE_ROOT"
printf '  ideal middle masks: %s\n' "$mask_count"
printf '  ideal images:       %s\n' "$image_count"
printf '  eval frames:        %s\n' "$eval_count"
printf '  high-opacity PLY:    %s\n' "data/05_3dgs/output/point_cloud/iteration_7000/point_cloud_filtered_opacity999999.ply"
printf '  STS PLY:             %s\n' "data/05_3dgs/output/point_cloud/iteration_7000/point_cloud.ply"
