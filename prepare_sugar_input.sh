#!/usr/bin/env bash
set -euo pipefail

# Build the standard object-only SuGaR input after STS: retain the segmented
# geometry, then set its initial Gaussian opacity uniformly high for the
# geometry-oriented SuGaR route. The original full-scene PLY remains untouched.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

ITERATIONS="${ITERATIONS:-7000}"
FILTER_MIN_OPACITY="${FILTER_MIN_OPACITY:-0.01}"
FILTER_BLACK_THRESHOLD="${FILTER_BLACK_THRESHOLD:-0.08}"
SUGAR_INPUT_ALPHA="${SUGAR_INPUT_ALPHA:-0.999999}"
RAW_STS_PLY="${RAW_STS_PLY:-data/05_3dgs/output/point_cloud/iteration_${ITERATIONS}/point_cloud.ply}"
FILTERED_OUTPUT_PLY="${FILTERED_OUTPUT_PLY:-data/05_3dgs/output/point_cloud/iteration_${ITERATIONS}/point_cloud_filtered.ply}"
SUGAR_INPUT_OUTPUT_PLY="${SUGAR_INPUT_OUTPUT_PLY:-data/05_3dgs/output/point_cloud/iteration_${ITERATIONS}/point_cloud_filtered_opacity999999.ply}"

to_container_data_path() {
    local host_path="$1"
    case "$host_path" in
        data/*)
            printf '/%s\n' "$host_path"
            ;;
        "$PROJECT_ROOT"/data/*)
            printf '/data/%s\n' "${host_path#"$PROJECT_ROOT"/data/}"
            ;;
        *)
            echo "Error: Path must be below this project's data/ directory: $host_path" >&2
            return 1
            ;;
    esac
}

if ! [[ "$ITERATIONS" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: ITERATIONS must be a positive integer." >&2
    exit 2
fi
if ! [[ "$FILTER_MIN_OPACITY" =~ ^0([.][0-9]+)?$ ]]; then
    echo "Error: FILTER_MIN_OPACITY must be in [0, 1)." >&2
    exit 2
fi
if ! [[ "$FILTER_BLACK_THRESHOLD" =~ ^(0|0[.][0-9]+|1([.]0+)?)$ ]]; then
    echo "Error: FILTER_BLACK_THRESHOLD must be in [0, 1]." >&2
    exit 2
fi
if ! [[ "$SUGAR_INPUT_ALPHA" =~ ^0[.][0-9]+$ ]]; then
    echo "Error: SUGAR_INPUT_ALPHA must be strictly between 0 and 1." >&2
    exit 2
fi
if [[ ! -f "$RAW_STS_PLY" ]]; then
    echo "Error: STS point cloud is missing: $RAW_STS_PLY" >&2
    exit 2
fi

RAW_STS_PLY_CONTAINER="$(to_container_data_path "$RAW_STS_PLY")"
FILTERED_OUTPUT_PLY_CONTAINER="$(to_container_data_path "$FILTERED_OUTPUT_PLY")"
SUGAR_INPUT_OUTPUT_PLY_CONTAINER="$(to_container_data_path "$SUGAR_INPUT_OUTPUT_PLY")"

echo "=== Preparing standard SuGaR geometry input ==="
echo "STS source        : $RAW_STS_PLY"
echo "Filtered output   : $FILTERED_OUTPUT_PLY"
echo "High-opacity input: $SUGAR_INPUT_OUTPUT_PLY"
echo "Opacity filter    : $FILTER_MIN_OPACITY (0 disables rejection)"
echo "Black threshold   : $FILTER_BLACK_THRESHOLD"
echo "SuGaR input alpha : $SUGAR_INPUT_ALPHA"

docker compose run --rm sts-training python3 /app/src/python/filter_cable_pc.py \
    --input_ply "$RAW_STS_PLY_CONTAINER" \
    --output_ply "$FILTERED_OUTPUT_PLY_CONTAINER" \
    --level m \
    --object_id 0 \
    --min_opacity "$FILTER_MIN_OPACITY" \
    --black_threshold "$FILTER_BLACK_THRESHOLD"

docker compose run --rm sts-training python3 /app/src/python/create_opacity_diagnostic_ply.py \
    --input-ply "$FILTERED_OUTPUT_PLY_CONTAINER" \
    --output-ply "$SUGAR_INPUT_OUTPUT_PLY_CONTAINER" \
    --target-alpha "$SUGAR_INPUT_ALPHA"

if [[ ! -f "$SUGAR_INPUT_OUTPUT_PLY" ]]; then
    echo "Error: High-opacity SuGaR input was not created: $SUGAR_INPUT_OUTPUT_PLY" >&2
    exit 2
fi

echo "=== Standard SuGaR geometry input ready ==="
