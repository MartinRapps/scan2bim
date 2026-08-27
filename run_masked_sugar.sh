#!/usr/bin/env bash
set -euo pipefail

# Object-only mesh pipeline. The default route (`SUGAR_MESH_MODE=original_gs`)
# keeps the original STS Gaussian geometry, performs Diamond-Mesh surface
# sampling/Poisson extraction, and exports a coarse PLY plus an OBJ for the
# Centerline step. The legacy `sugar_coarse` route stages the same input,
# trains the local mask-aware SuGaR fork, and exports a refined model separately.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Standalone invocations must use the invoking host identity for bind mounts,
# just like run_pipeline.sh and the coarse-mesh ablation helper.
export HOST_UID="${HOST_UID:-$(id -u)}"
export HOST_GID="${HOST_GID:-$(id -g)}"

# A plain terminal invocation is guided. Reproducible commands that provide at
# least one configuration variable keep the previous non-interactive behavior.
CONFIGURATION_WAS_PROVIDED=0
for config_variable in \
        ITERATIONS REGULARIZATION REFINEMENT_TIME MASK_LEVEL NORMAL_MASK_LEVEL \
        TEXTURE_MASK_LEVEL MASK_DILATION_PX TEXTURE_MASK_DILATION_PX \
        MESH_VERTICES SURFACE_SAMPLE_COUNT COARSE_ITERATIONS SUGAR_RUN_TAG \
        SUGAR_MESH_MODE SURFACE_LEVEL POISSON_DEPTH VERTICES_DENSITY_QUANTILE \
        PROJECT_MESH_ON_SURFACE_POINTS LOW_OPACITY_GAUSSIAN_THRESHOLD \
        SURFACE_SAMPLE_SEED INCLUDE_BACKGROUND_MESH USE_GAUSSIAN_DEPTH \
        STOP_AFTER_COARSE_MESH RUN_CONSENSUS_CROP FILTERED_PLY \
        SUGAR_MESH_EXPORT_NAME FILTER_MIN_OPACITY FILTER_BLACK_THRESHOLD \
        SUGAR_INPUT_ALPHA; do
        if [[ -v $config_variable ]]; then
                CONFIGURATION_WAS_PROVIDED=1
                break
        fi
done

# MASKED_SUGAR_INTERACTIVE controls only whether this helper asks its own
# configuration questions. It is deliberately independent from
# STOP_AFTER_COARSE_MESH, which controls whether refinement/export continues.
INTERACTIVE_SETTING="${MASKED_SUGAR_INTERACTIVE:-auto}"
case "$INTERACTIVE_SETTING" in
        auto)
                if [[ -t 0 && "$CONFIGURATION_WAS_PROVIDED" == "0" ]]; then
                        INTERACTIVE=1
                else
                        INTERACTIVE=0
                fi
                ;;
        1|true|TRUE|yes|YES)
                INTERACTIVE=1
                ;;
        0|false|FALSE|no|NO)
                INTERACTIVE=0
                ;;
        *)
                echo "Error: MASKED_SUGAR_INTERACTIVE must be auto, 0, or 1." >&2
                exit 2
                ;;
esac

explain_checkpoint_iteration() {
        cat <<'EOF'

    ITERATIONS selects the existing STS checkpoint and geometry input PLY.
    It must match point_cloud_filtered_opacity999999.ply and cameras.json from
    the same STS run. The source point_cloud_filtered.ply is retained separately
    with its original opacity values.
    The current object experiment uses the STS checkpoint at 7000 by default.
EOF
}

explain_regularization() {
        cat <<'EOF'

    dn_consistency : Current object route. Uses masked RGB supervision and the
                                     local density schedule. DN/SDF terms are only
                                     activated for targets above 9000.
    density        : Density/SDF regularization without the DN-specific schedule.
    sdf            : Alternative upstream regularization route.
    Keep dn_consistency for comparisons with the current reference run.
EOF
}

explain_mesh_mode() {
        cat <<'EOF'

    original_gs : Current production default (A). Skips SuGaR Coarse
                  optimization and uses the prepared high-opacity STS Gaussian
                  cloud directly. Diamond-Mesh depth, surface sampling, Poisson,
                  cleanup and decimation remain active. No Gaussian-bound
                  Refinement or UV baking is performed.
    sugar_coarse : Legacy/experimental route (C-like with Diamond-Mesh depth).
                  Runs the mask-aware SuGaR Coarse optimization and, unless
                  stopped, its mesh-bound Refinement and UV export.
EOF
}

explain_coarse_iterations() {
        cat <<'EOF'

    COARSE_ITERATIONS is the final counter of the local dn_consistency trainer,
    not simply an independent number of new optimizer updates. Because the model
    starts from the STS checkpoint, its counter begins at 6999.

    The current local schedule is:
        7000-9000 : masked RGB optimization; entropy regularization is active.
        >9000     : depth-normal consistency and SDF-related geometric terms start.

    9000 is the current geometry-oriented standard for segmented objects. It
    retains the STS-derived surface support without requiring the later DN/SDF
    phase or external depth data. Targets above 9000 activate DN/SDF and remain
    separate comparisons because they can improve thin parts while also
    consolidating contact-region artifacts.
EOF
}

explain_mesh_vertices() {
        cat <<'EOF'

    MESH_VERTICES is the target after Poisson reconstruction and mesh decimation.
    It controls the resolution of the coarse mesh handed to refinement. It does
    not reduce the preceding camera-based surface sampling or Poisson solve by
    the same factor. 25k-100k is useful for a visual screening mesh; 1,000,000
    is the current detailed reference. Do not compare their fine geometry as if
    they had identical resolution.
EOF
}

explain_surface_sample_count() {
        cat <<'EOF'

    SURFACE_SAMPLE_COUNT is the total target number of Gaussian surface samples
    collected across the training cameras before Poisson reconstruction. With
    --eval=True, the current 699 registered views become 611 training views and
    88 held-out evaluation views. The current screening target is 5,000,000;
    the upstream detailed reference is 10,000,000. This is a direct
    runtime/quality trade-off in mesh extraction: fewer samples can accelerate
    a screening run but can make thin structures or artifacts less reliable.
EOF
}

explain_refinement_time() {
        cat <<'EOF'

    short  : 2000 refinement updates; use for a pipeline or runtime screen.
    medium : 7000 refinement updates; current reference setting.
    long   : 15000 refinement updates.

    Refinement is bound to the extracted coarse mesh. It can improve the surface
    appearance but cannot prove that an already incorrect coarse sheet was valid.
EOF
}

explain_stop_after_coarse_mesh() {
    cat <<'EOF'

    STOP_AFTER_COARSE_MESH=1 ends after the selected coarse-mesh route. In the
    default original_gs route this means after direct surface sampling and PLY/
    OBJ export; in sugar_coarse it means after Coarse optimization and Coarse
    mesh extraction. Refinement, UV texture baking, and semantic crop are then
    skipped.

    STOP_AFTER_COARSE_MESH=0 is the complete pipeline. It preserves the saved
    Coarse PLY, then uses that PLY as input for refinement and writes refined
    outputs separately. A stopped run is intentionally not resumed by changing
    this value on the same tag; use a fresh tag for a complete comparison run.
EOF
}

explain_mask_levels() {
        cat <<'EOF'

    default : original SAM foreground mask.
    middle  : one 5x5 erosion; conservative inner object region.
    small   : two 5x5 erosions; strict inner core.

    RGB uses MASK_LEVEL in coarse and refinement. DN uses NORMAL_MASK_LEVEL only
    in coarse training and has no additional dilation. UV uses TEXTURE_MASK_LEVEL
    only while collecting colors for the final texture atlas.
EOF
}

explain_mask_dilation() {
        cat <<'EOF'

    RGB dilation expands the selected RGB mask before masked L1+DSSIM supervision
    in coarse training and refinement. Its standard value is 0 pixels. It can include
    uncertain silhouette/background pixels, so it remains a testable cause of
    geometry changes. Set it to 0 for the controlled no-dilation experiment.

    UV dilation is separate. It expands only the pixels accepted while baking
    colors into the texture atlas; it is not a geometry loss and cannot change
    the coarse mesh or refined PLY. Set it to 0 alongside RGB dilation so the
    rendered appearance does not obscure a geometric comparison.
EOF
}

export_refined_model() {
    local source_mtl
    local texture_reference
    local source_texture

    REFINED_PLY=""
    if [[ -d "$OUTPUT_HOST_DIR/refined_ply" ]]; then
        REFINED_PLY="$(find "$OUTPUT_HOST_DIR/refined_ply" -type f -name '*.ply' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2- || true)"
    fi
    FINAL_MESH=""
    if [[ -d "$OUTPUT_HOST_DIR/refined_mesh" ]]; then
        FINAL_MESH="$(find "$OUTPUT_HOST_DIR/refined_mesh" -type f -name '*.obj' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2- || true)"
    fi
    if [[ -z "$FINAL_MESH" || ! -f "$FINAL_MESH" ]]; then
        echo "Error: The mask-aware SuGaR run completed without a textured OBJ output." >&2
        exit 2
    fi
    if [[ -z "$REFINED_PLY" || ! -f "$REFINED_PLY" ]]; then
        echo "Warning: No refined PLY found; continuing with OBJ/MTL/texture export only." >&2
        REFINED_PLY=""
    fi

    MESH_EXPORT_DIR="data/06_mesh/$MESH_EXPORT_NAME"
    if [[ -e "$MESH_EXPORT_DIR" ]]; then
        if [[ "${REPLACE:-0}" != "1" ]]; then
            echo "Error: Short refined-model export already exists: $MESH_EXPORT_DIR" >&2
            echo "Set SUGAR_MESH_EXPORT_NAME to a new name, or set REPLACE=1 to replace it deliberately." >&2
            exit 2
        fi
        rm -rf "$MESH_EXPORT_DIR"
    fi
    mkdir -p "$MESH_EXPORT_DIR"

    EXPORTED_REFINED_PLY=""
    EXPORTED_OBJ="$MESH_EXPORT_DIR/refined.obj"
    if [[ -n "$REFINED_PLY" ]]; then
        EXPORTED_REFINED_PLY="$MESH_EXPORT_DIR/refined.ply"
        cp "$REFINED_PLY" "$EXPORTED_REFINED_PLY"
    fi
    cp "$FINAL_MESH" "$EXPORTED_OBJ"

    source_mtl="${FINAL_MESH%.*}.mtl"
    if [[ -f "$source_mtl" ]]; then
        cp "$source_mtl" "$MESH_EXPORT_DIR/refined.mtl"
        sed -i -E 's|^[[:space:]]*mtllib[[:space:]].*$|mtllib refined.mtl|' "$EXPORTED_OBJ"
        texture_reference="$(awk '$1 == "map_Kd" { print $2; exit }' "$source_mtl")"
        source_texture="$(dirname "$source_mtl")/$texture_reference"
        if [[ -n "$texture_reference" && -f "$source_texture" ]]; then
            cp "$source_texture" "$MESH_EXPORT_DIR/texture.png"
            sed -i -E 's|^[[:space:]]*map_Kd[[:space:]].*$|map_Kd texture.png|' "$MESH_EXPORT_DIR/refined.mtl"
        fi
    fi
}

export_original_gs_mesh() {
    local coarse_mesh_host_dir="$OUTPUT_HOST_DIR/coarse_mesh/05_3dgs"
    local coarse_mesh_container_dir="$OUTPUT_CONTAINER_ROOT/coarse_mesh/05_3dgs"
    local coarse_mesh_path
    local mesh_export_dir="data/06_mesh/$MESH_EXPORT_NAME"
    local mesh_export_container_dir="/data/06_mesh/$MESH_EXPORT_NAME"

    if [[ "${EXPORT_ONLY:-0}" != "1" ]]; then
        mkdir -p "$coarse_mesh_host_dir"
        local extract_arguments=(
            python3 extract_mesh.py
            -s /data/05_3dgs
            -c "$CHECKPOINT_CONTAINER_DIR"
            -i "$ITERATIONS"
            -l "$SURFACE_LEVEL"
            -d "$MESH_VERTICES"
            -o "$coarse_mesh_container_dir"
            --surface-sample-count "$SURFACE_SAMPLE_COUNT"
            --project_mesh_on_surface_points "$PROJECT_MESH_ON_SURFACE_POINTS"
            --poisson-depth "$POISSON_DEPTH"
            --vertices-density-quantile "$VERTICES_DENSITY_QUANTILE"
            --low-opacity-gaussian-threshold "$LOW_OPACITY_GAUSSIAN_THRESHOLD"
            --include-background-mesh "$INCLUDE_BACKGROUND_MESH"
            --use-gaussian-depth "$USE_GAUSSIAN_DEPTH"
            --use_vanilla_3dgs True
            --eval True
            --gpu 0
        )
        if [[ -n "$SURFACE_SAMPLE_SEED" ]]; then
            extract_arguments+=(--surface-sample-seed "$SURFACE_SAMPLE_SEED")
        fi

        docker compose -f docker-compose.yml -f docker-compose.sugar-dev.yml run --rm sugar-meshing \
            "${extract_arguments[@]}"
    fi

    coarse_mesh_path="$(find "$coarse_mesh_host_dir" -type f -name '*.ply' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2- || true)"
    if [[ -z "$coarse_mesh_path" || ! -s "$coarse_mesh_path" ]]; then
        echo "Error: Original-GS coarse mesh PLY was not created below $coarse_mesh_host_dir." >&2
        exit 2
    fi

    if [[ -e "$mesh_export_dir" ]]; then
        if [[ "${REPLACE:-0}" != "1" ]]; then
            echo "Error: Mesh export already exists: $mesh_export_dir" >&2
            echo "Set SUGAR_MESH_EXPORT_NAME to a new name, or use REPLACE=1 deliberately." >&2
            exit 2
        fi
        rm -rf "$mesh_export_dir"
    fi
    mkdir -p "$mesh_export_dir"
    cp "$coarse_mesh_path" "$mesh_export_dir/coarse.ply"

    docker compose -f docker-compose.yml -f docker-compose.sugar-dev.yml run --rm sugar-meshing \
        python3 /app/src/python/export_mesh_obj.py \
        --input "$coarse_mesh_container_dir/$(basename "$coarse_mesh_path")" \
        --output "$mesh_export_container_dir/refined.obj"

    MESH_EXPORT_DIR="$mesh_export_dir"
    EXPORTED_REFINED_PLY=""
    EXPORTED_OBJ="$mesh_export_dir/refined.obj"
    if [[ ! -s "$EXPORTED_OBJ" ]]; then
        echo "Error: Original-GS OBJ export was not created: $EXPORTED_OBJ" >&2
        exit 2
    fi
    cat > "$mesh_export_dir/mesh_mode.txt" <<EOF
SUGAR_MESH_MODE=original_gs
source=STS high-opacity Gaussian PLY
depth=projected Diamond-Mesh z-buffer
coarse_ply=coarse.ply
obj=refined.obj (compatibility filename; no SuGaR refinement was run)
surface_sample_seed=${SURFACE_SAMPLE_SEED:-None}
EOF
    echo "Original-GS coarse PLY export: $mesh_export_dir/coarse.ply"
    echo "Original-GS OBJ export: $EXPORTED_OBJ"
}

explain_consensus_crop() {
        cat <<'EOF'

    RUN_CONSENSUS_CROP=1 runs a post-export semantic mesh crop. It is not part of
    coarse training, refinement, or texture baking. Set it to 0 for diagnostics
    so the exported mesh is inspected before any crop removes faces.
EOF
}

explain_run_tag() {
        cat <<'EOF'

    SUGAR_RUN_TAG names both a private staged input checkpoint and an output
    directory. A new tag preserves every prior run. The runner refuses a reused
    tag unless REPLACE=1 is explicitly set; do not use REPLACE=1 for comparisons.
EOF
}

ask_value() {
        local variable_name="$1"
        local prompt="$2"
        local default_value="$3"
        local explain_function="$4"
        local answer

        while true; do
                read -r -p "$prompt [Default: $default_value]: " answer
                if [[ "${answer,,}" == "explain" ]]; then
                        "$explain_function"
                        continue
                fi
                printf -v "$variable_name" '%s' "${answer:-$default_value}"
                return
        done
}

ITERATIONS="${ITERATIONS:-7000}"
REGULARIZATION="${REGULARIZATION:-dn_consistency}"
SUGAR_MESH_MODE="${SUGAR_MESH_MODE:-original_gs}"
REFINEMENT_TIME="${REFINEMENT_TIME:-medium}"
MASK_LEVEL="${MASK_LEVEL:-default}"
NORMAL_MASK_LEVEL="${NORMAL_MASK_LEVEL:-middle}"
TEXTURE_MASK_LEVEL="${TEXTURE_MASK_LEVEL:-default}"
MASK_DILATION_PX="${MASK_DILATION_PX:-0}"
TEXTURE_MASK_DILATION_PX="${TEXTURE_MASK_DILATION_PX:-0}"
MASK_SSIM_WINDOW="${MASK_SSIM_WINDOW:-11}"
MESH_VERTICES="${MESH_VERTICES:-200000}"
SURFACE_SAMPLE_COUNT="${SURFACE_SAMPLE_COUNT:-5000000}"
SURFACE_LEVEL="${SURFACE_LEVEL:-0.3}"
POISSON_DEPTH="${POISSON_DEPTH:-10}"
VERTICES_DENSITY_QUANTILE="${VERTICES_DENSITY_QUANTILE:-0.1}"
PROJECT_MESH_ON_SURFACE_POINTS="${PROJECT_MESH_ON_SURFACE_POINTS:-True}"
LOW_OPACITY_GAUSSIAN_THRESHOLD="${LOW_OPACITY_GAUSSIAN_THRESHOLD:-0.5}"
SURFACE_SAMPLE_SEED="${SURFACE_SAMPLE_SEED:-42}"
INCLUDE_BACKGROUND_MESH="${INCLUDE_BACKGROUND_MESH:-True}"
USE_GAUSSIAN_DEPTH="${USE_GAUSSIAN_DEPTH:-False}"
COARSE_ITERATIONS="${COARSE_ITERATIONS:-}"
if [[ "$SUGAR_MESH_MODE" == "sugar_coarse" && "$REGULARIZATION" == "dn_consistency" && -z "$COARSE_ITERATIONS" ]]; then
    COARSE_ITERATIONS=9000
fi
if [[ "$SUGAR_MESH_MODE" == "original_gs" ]]; then
    COARSE_ITERATIONS=""
fi
STOP_AFTER_COARSE_MESH="${STOP_AFTER_COARSE_MESH:-0}"
RUN_CONSENSUS_CROP="${RUN_CONSENSUS_CROP:-0}"
RUN_TAG="${SUGAR_RUN_TAG:-}"

if [[ "$INTERACTIVE" == "1" ]]; then
    echo "=== Guided mask-aware SuGaR configuration ==="
    echo "Enter EXPLAIN at any prompt for the parameter rationale."
    ask_value ITERATIONS \
        "STS checkpoint iteration (or EXPLAIN)" "$ITERATIONS" explain_checkpoint_iteration
    ask_value SUGAR_MESH_MODE \
        "Mesh route (original_gs/sugar_coarse, or EXPLAIN)" "$SUGAR_MESH_MODE" explain_mesh_mode
    if [[ "$SUGAR_MESH_MODE" == "sugar_coarse" ]]; then
        ask_value REGULARIZATION \
            "Regularization (sdf/density/dn_consistency, or EXPLAIN)" "$REGULARIZATION" explain_regularization
        if [[ "$REGULARIZATION" == "dn_consistency" ]]; then
            ask_value COARSE_ITERATIONS \
                "Coarse final iteration counter (or EXPLAIN)" "${COARSE_ITERATIONS:-9000}" explain_coarse_iterations
        else
            COARSE_ITERATIONS=""
        fi
    else
        COARSE_ITERATIONS=""
        echo "A-Route gewaehlt: SuGaR-Coarse-Training und Refinement werden uebersprungen."
    fi
    if [[ "$SUGAR_MESH_MODE" != "sugar_coarse" ]]; then
        REGULARIZATION="dn_consistency"
    fi
    ask_value MESH_VERTICES \
        "Coarse mesh vertex target (or EXPLAIN)" "$MESH_VERTICES" explain_mesh_vertices
    ask_value SURFACE_SAMPLE_COUNT \
        "Total camera surface samples (or EXPLAIN)" "$SURFACE_SAMPLE_COUNT" explain_surface_sample_count
    ask_value STOP_AFTER_COARSE_MESH \
        "Stop after Coarse mesh? 1=yes, 0=no (or EXPLAIN)" "$STOP_AFTER_COARSE_MESH" explain_stop_after_coarse_mesh
    ask_value REFINEMENT_TIME \
        "Refinement time (short/medium/long, or EXPLAIN)" "$REFINEMENT_TIME" explain_refinement_time
    ask_value MASK_LEVEL \
        "RGB mask level (default/middle/small, or EXPLAIN)" "$MASK_LEVEL" explain_mask_levels
    ask_value MASK_DILATION_PX \
        "RGB mask dilation in pixels (or EXPLAIN)" "$MASK_DILATION_PX" explain_mask_dilation
    ask_value NORMAL_MASK_LEVEL \
        "DN mask level (default/middle/small, or EXPLAIN)" "$NORMAL_MASK_LEVEL" explain_mask_levels
    ask_value TEXTURE_MASK_LEVEL \
        "UV mask level (default/middle/small, or EXPLAIN)" "$TEXTURE_MASK_LEVEL" explain_mask_levels
    ask_value TEXTURE_MASK_DILATION_PX \
        "UV mask dilation in pixels (or EXPLAIN)" "$TEXTURE_MASK_DILATION_PX" explain_mask_dilation
    ask_value RUN_CONSENSUS_CROP \
        "Run final semantic crop? 1=yes, 0=no (or EXPLAIN)" "$RUN_CONSENSUS_CROP" explain_consensus_crop
    ask_value RUN_TAG \
        "New run tag (or EXPLAIN)" "${RUN_TAG:-masked_${ITERATIONS}_${REGULARIZATION}_${REFINEMENT_TIME}}" explain_run_tag
fi

RUN_TAG="${RUN_TAG:-sugar_i${ITERATIONS}_c${COARSE_ITERATIONS:-default}_v${MESH_VERTICES}}"

case "$REGULARIZATION" in
    sdf|density|dn_consistency)
        ;;
    *)
        echo "Error: REGULARIZATION must be sdf, density, or dn_consistency." >&2
        exit 2
        ;;
esac
case "$SUGAR_MESH_MODE" in
    original_gs|sugar_coarse)
        ;;
    *)
        echo "Error: SUGAR_MESH_MODE must be original_gs or sugar_coarse." >&2
        exit 2
        ;;
esac
if ! [[ "$ITERATIONS" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: ITERATIONS must be a positive integer." >&2
    exit 2
fi
case "$REFINEMENT_TIME" in
    short|medium|long)
        ;;
    *)
        echo "Error: REFINEMENT_TIME must be short, medium, or long." >&2
        exit 2
        ;;
esac
for mask_level_variable in MASK_LEVEL NORMAL_MASK_LEVEL TEXTURE_MASK_LEVEL; do
    case "${!mask_level_variable}" in
        default|middle|small)
            ;;
        *)
            echo "Error: $mask_level_variable must be default, middle, or small." >&2
            exit 2
            ;;
    esac
done
for nonnegative_integer_variable in MASK_DILATION_PX TEXTURE_MASK_DILATION_PX; do
    if ! [[ "${!nonnegative_integer_variable}" =~ ^[0-9]+$ ]]; then
        echo "Error: $nonnegative_integer_variable must be a non-negative integer." >&2
        exit 2
    fi
done
if ! [[ "$MASK_SSIM_WINDOW" =~ ^[1-9][0-9]*$ ]] || (( MASK_SSIM_WINDOW < 3 || MASK_SSIM_WINDOW % 2 == 0 )); then
    echo "Error: MASK_SSIM_WINDOW must be an odd integer of at least 3." >&2
    exit 2
fi
if ! [[ "$MESH_VERTICES" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: MESH_VERTICES must be a positive integer." >&2
    exit 2
fi
if ! [[ "$SURFACE_SAMPLE_COUNT" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: SURFACE_SAMPLE_COUNT must be a positive integer." >&2
    exit 2
fi
if ! [[ "$SURFACE_LEVEL" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "Error: SURFACE_LEVEL must be a non-negative decimal number." >&2
    exit 2
fi
if ! [[ "$POISSON_DEPTH" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: POISSON_DEPTH must be a positive integer." >&2
    exit 2
fi
if ! [[ "$VERTICES_DENSITY_QUANTILE" =~ ^(0|0\.[0-9]+)$ ]]; then
    echo "Error: VERTICES_DENSITY_QUANTILE must be in [0, 1)." >&2
    exit 2
fi
if ! [[ "$LOW_OPACITY_GAUSSIAN_THRESHOLD" =~ ^0(\.[0-9]+)?$ ]]; then
    echo "Error: LOW_OPACITY_GAUSSIAN_THRESHOLD must be in [0, 1)." >&2
    exit 2
fi
if [[ -n "$SURFACE_SAMPLE_SEED" && ! "$SURFACE_SAMPLE_SEED" =~ ^[0-9]+$ ]]; then
    echo "Error: SURFACE_SAMPLE_SEED must be empty or a non-negative integer." >&2
    exit 2
fi
case "${PROJECT_MESH_ON_SURFACE_POINTS,,}" in
    1|true|yes|y) PROJECT_MESH_ON_SURFACE_POINTS="True" ;;
    0|false|no|n) PROJECT_MESH_ON_SURFACE_POINTS="False" ;;
    *) echo "Error: PROJECT_MESH_ON_SURFACE_POINTS must be True or False." >&2; exit 2 ;;
esac
case "${INCLUDE_BACKGROUND_MESH,,}" in
    1|true|yes|y) INCLUDE_BACKGROUND_MESH="True" ;;
    0|false|no|n) INCLUDE_BACKGROUND_MESH="False" ;;
    *) echo "Error: INCLUDE_BACKGROUND_MESH must be True or False." >&2; exit 2 ;;
esac
case "${USE_GAUSSIAN_DEPTH,,}" in
    1|true|yes|y) USE_GAUSSIAN_DEPTH="True" ;;
    0|false|no|n) USE_GAUSSIAN_DEPTH="False" ;;
    *) echo "Error: USE_GAUSSIAN_DEPTH must be True or False." >&2; exit 2 ;;
esac
if [[ -n "$COARSE_ITERATIONS" && ! "$COARSE_ITERATIONS" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: COARSE_ITERATIONS must be a positive integer when supplied." >&2
    exit 2
fi
if [[ -n "$COARSE_ITERATIONS" && "$REGULARIZATION" != "dn_consistency" ]]; then
    echo "Error: COARSE_ITERATIONS is currently supported only with REGULARIZATION=dn_consistency." >&2
    exit 2
fi
if [[ -n "$COARSE_ITERATIONS" && "$COARSE_ITERATIONS" -le 6999 ]]; then
    echo "Error: COARSE_ITERATIONS must exceed the loaded STS counter 6999." >&2
    exit 2
fi
if [[ -n "$COARSE_ITERATIONS" && "$COARSE_ITERATIONS" -le 9000 ]]; then
    echo "Notice: DN/SDF phase is not reached; this is intentional for the segmented-object default." >&2
elif [[ -n "$COARSE_ITERATIONS" ]]; then
    echo "Notice: DN/SDF phase is active for this comparison run (about $((COARSE_ITERATIONS - 9000)) updates)." >&2
fi
case "$RUN_CONSENSUS_CROP" in
    0|1)
        ;;
    *)
        echo "Error: RUN_CONSENSUS_CROP must be 0 or 1." >&2
        exit 2
        ;;
esac
case "$STOP_AFTER_COARSE_MESH" in
    0|1)
        ;;
    *)
        echo "Error: STOP_AFTER_COARSE_MESH must be 0 or 1." >&2
        exit 2
        ;;
esac
if ! [[ "$RUN_TAG" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "Error: SUGAR_RUN_TAG may contain only letters, digits, dots, underscores, and hyphens." >&2
    exit 2
fi

if [[ "$SUGAR_MESH_MODE" == "original_gs" ]]; then
    COARSE_TARGET="original_gs"
elif [[ "$REGULARIZATION" == "dn_consistency" ]]; then
    COARSE_TARGET="$COARSE_ITERATIONS"
else
    COARSE_TARGET="default"
fi
MESH_EXPORT_NAME="${SUGAR_MESH_EXPORT_NAME:-sugar_i${ITERATIONS}_${COARSE_TARGET}_v${MESH_VERTICES}_${MASK_LEVEL}_dn${NORMAL_MASK_LEVEL}}"
if ! [[ "$MESH_EXPORT_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "Error: SUGAR_MESH_EXPORT_NAME may contain only letters, digits, dots, underscores, and hyphens." >&2
    exit 2
fi

DEFAULT_FILTERED_PLY="data/05_3dgs/output/point_cloud/iteration_${ITERATIONS}/point_cloud_filtered_opacity999999.ply"
FILTERED_PLY="${FILTERED_PLY:-$DEFAULT_FILTERED_PLY}"
FILTER_MIN_OPACITY="${FILTER_MIN_OPACITY:-0.01}"
FILTER_BLACK_THRESHOLD="${FILTER_BLACK_THRESHOLD:-0.08}"
SUGAR_INPUT_ALPHA="${SUGAR_INPUT_ALPHA:-0.999999}"
CAMERAS_JSON="${CAMERAS_JSON:-data/05_3dgs/output/cameras.json}"
MASKS_DIR="${MASKS_DIR:-data/03_masks}"
MASKS_CONTAINER_DIR="${MASKS_CONTAINER_DIR:-/data/03_masks}"
CHECKPOINT_HOST_DIR="data/05_3dgs/masked_sugar_input/${RUN_TAG}"
CHECKPOINT_CONTAINER_DIR="/data/05_3dgs/masked_sugar_input/${RUN_TAG}/"
OUTPUT_HOST_DIR="data/sugar_output/${RUN_TAG}"
# The local SuGaR dev overlay replaces /opt/sugar, so the image's nested
# /opt/sugar/output volume is hidden. Keep all runtime outputs on the shared
# /data bind mount instead.
OUTPUT_CONTAINER_ROOT="/data/sugar_output/${RUN_TAG}"

if [[ "${EXPORT_ONLY:-0}" == "1" ]]; then
    if [[ "$SUGAR_MESH_MODE" == "original_gs" ]]; then
        echo "=== Exporting existing Original-GS coarse mesh without retraining ==="
        export_original_gs_mesh
        echo "Original-GS OBJ export: $EXPORTED_OBJ"
    else
        echo "=== Exporting existing SuGaR refined mesh without retraining ==="
        export_refined_model
        echo "Refined OBJ export: $EXPORTED_OBJ"
        if [[ -n "$EXPORTED_REFINED_PLY" ]]; then
            echo "Refined PLY export: $EXPORTED_REFINED_PLY"
        else
            echo "Refined PLY export: not available (OBJ export is usable for post-processing)"
        fi
    fi
    exit 0
fi

if [[ ! -f "$FILTERED_PLY" && "$FILTERED_PLY" == "$DEFAULT_FILTERED_PLY" ]]; then
    echo "Standard high-opacity SuGaR input is missing; preparing it from the STS checkpoint..."
    ITERATIONS="$ITERATIONS" \
    FILTER_MIN_OPACITY="$FILTER_MIN_OPACITY" \
    FILTER_BLACK_THRESHOLD="$FILTER_BLACK_THRESHOLD" \
    SUGAR_INPUT_ALPHA="$SUGAR_INPUT_ALPHA" \
    ./prepare_sugar_input.sh
fi
if [[ ! -f "$FILTERED_PLY" ]]; then
    echo "Error: No filtered object point cloud was found:" >&2
    echo "  $FILTERED_PLY" >&2
    echo "Run ./prepare_sugar_input.sh first, or pass FILTERED_PLY explicitly." >&2
    exit 2
fi
if [[ ! -f "$CAMERAS_JSON" || ! -d "$MASKS_DIR" ]]; then
    echo "Error: cameras.json or the source masks are missing." >&2
    exit 2
fi

if [[ ( -e "$OUTPUT_HOST_DIR" || -e "$CHECKPOINT_HOST_DIR" ) && "${REPLACE:-0}" != "1" ]]; then
    echo "Error: Output or private staged checkpoint already exists for tag: $RUN_TAG" >&2
    [[ -e "$OUTPUT_HOST_DIR" ]] && echo "  Existing output: $OUTPUT_HOST_DIR" >&2
    [[ -e "$CHECKPOINT_HOST_DIR" ]] && echo "  Existing staged checkpoint: $CHECKPOINT_HOST_DIR" >&2
    echo "Set SUGAR_RUN_TAG to a new value, or set REPLACE=1 to deliberately replace this run." >&2
    exit 2
fi
if [[ "${REPLACE:-0}" == "1" ]]; then
    rm -rf "$OUTPUT_HOST_DIR" "$CHECKPOINT_HOST_DIR"
fi

echo "=== Object mesh reconstruction ==="
echo "Filtered input : $FILTERED_PLY"
echo "Source masks   : $MASKS_DIR"
echo "Run tag        : $RUN_TAG"
echo "Mesh route     : $SUGAR_MESH_MODE"
echo "Regularization : $REGULARIZATION"
echo "Refinement     : $REFINEMENT_TIME"
echo "Mesh vertices  : $MESH_VERTICES"
echo "Surface samples: $SURFACE_SAMPLE_COUNT"
echo "Stop after Coarse mesh: $STOP_AFTER_COARSE_MESH"
echo "Mesh export: data/06_mesh/$MESH_EXPORT_NAME"
if [[ "$SUGAR_MESH_MODE" == "original_gs" ]]; then
    echo "A route: SuGaR Coarse optimization, Gaussian-bound refinement, and UV baking are skipped."
    echo "Surface route: Original STS GS + projected Diamond-Mesh depth"
elif [[ "$REGULARIZATION" == "dn_consistency" ]]; then
    echo "Coarse target counter: $COARSE_TARGET (starts at 6999; about $((COARSE_TARGET - 6999)) new updates)"
    if (( COARSE_TARGET > 9000 )); then
        echo "DN/SDF-phase updates: about $((COARSE_TARGET - 9000)) after activation above 9000"
    else
        echo "DN/SDF-phase updates: 0 (not reached for the segmented-object default)"
    fi
else
    echo "Coarse iterations: implementation default for $REGULARIZATION"
fi
echo "RGB / DN / UV masks: $MASK_LEVEL / $NORMAL_MASK_LEVEL / $TEXTURE_MASK_LEVEL"

# SuGaR can only load point_cloud.ply from a checkpoint root. Stage a private
# copy rather than replacing the original STS checkpoint or its full-scene PLY.
mkdir -p "$CHECKPOINT_HOST_DIR/point_cloud/iteration_${ITERATIONS}"
cp "$CAMERAS_JSON" "$CHECKPOINT_HOST_DIR/cameras.json"
if [[ -f data/05_3dgs/output/cfg_args ]]; then
    cp data/05_3dgs/output/cfg_args "$CHECKPOINT_HOST_DIR/cfg_args"
fi
cp "$FILTERED_PLY" "$CHECKPOINT_HOST_DIR/point_cloud/iteration_${ITERATIONS}/point_cloud.ply"

# SuGaR independently derives its train/eval split from cameras.json. Keep
# empty semantic-mask views out of this private checkpoint without changing
# the STS checkpoint or the original camera metadata.
docker compose -f docker-compose.yml -f docker-compose.sugar-dev.yml run --rm --no-deps sugar-meshing \
    python3 /app/src/python/filter_sugar_cameras_by_mask.py \
    --input "$CHECKPOINT_CONTAINER_DIR/cameras.json" \
    --output "$CHECKPOINT_CONTAINER_DIR/cameras.json" \
    --masks-dir "$MASKS_CONTAINER_DIR" \
    --levels "$MASK_LEVEL" "$NORMAL_MASK_LEVEL" "$TEXTURE_MASK_LEVEL"

if [[ "$SUGAR_MESH_MODE" == "original_gs" ]]; then
    export_original_gs_mesh
    if [[ "$STOP_AFTER_COARSE_MESH" == "1" ]]; then
        echo "Original-GS A route stopped after coarse mesh export; no SuGaR refinement, UV texture, or consensus crop was run."
        exit 0
    fi
else
    COARSE_ARGUMENTS=()
    if [[ -n "$COARSE_ITERATIONS" ]]; then
        COARSE_ARGUMENTS+=(--coarse-iterations "$COARSE_ITERATIONS")
    fi

    docker compose -f docker-compose.yml -f docker-compose.sugar-dev.yml run --rm sugar-meshing \
        python3 train.py \
        -s /data/05_3dgs \
        -c "$CHECKPOINT_CONTAINER_DIR" \
        -i "$ITERATIONS" \
        -r "$REGULARIZATION" \
        -v "$MESH_VERTICES" \
        --surface-sample-count "$SURFACE_SAMPLE_COUNT" \
        --stop-after-coarse-mesh "$STOP_AFTER_COARSE_MESH" \
        "${COARSE_ARGUMENTS[@]}" \
        --refinement_time "$REFINEMENT_TIME" \
        --eval True \
        --masks-dir "$MASKS_CONTAINER_DIR" \
        --mask-level "$MASK_LEVEL" \
        --normal-mask-level "$NORMAL_MASK_LEVEL" \
        --mask-dilation-px "$MASK_DILATION_PX" \
        --texture-mask-level "$TEXTURE_MASK_LEVEL" \
        --texture-mask-dilation-px "$TEXTURE_MASK_DILATION_PX" \
        --mask-ssim-window "$MASK_SSIM_WINDOW" \
        --output-root "$OUTPUT_CONTAINER_ROOT"

    if [[ "$STOP_AFTER_COARSE_MESH" == "1" ]]; then
        echo "Mask-aware SuGaR stopped after Coarse mesh. Refinement, UV texture, and consensus crop were intentionally skipped."
        exit 0
    fi

    export_refined_model
    echo "Refined PLY export: $EXPORTED_REFINED_PLY"
    echo "Refined OBJ export: $EXPORTED_OBJ"
fi

if [[ "$RUN_CONSENSUS_CROP" != "1" ]]; then
    if [[ "$SUGAR_MESH_MODE" == "original_gs" ]]; then
        echo "Original-GS A route completed. Consensus crop intentionally skipped."
    else
        echo "Mask-aware SuGaR completed. Consensus crop intentionally skipped."
    fi
    exit 0
fi

CROPPED_MESH="$MESH_EXPORT_DIR/refined_multiview.obj"
echo "Starting final multi-view consensus crop..."
MESH_PATH="$EXPORTED_OBJ" \
OUTPUT_PATH="$CROPPED_MESH" \
MASK_LEVEL="$TEXTURE_MASK_LEVEL" \
MASK_DILATION_PX="$TEXTURE_MASK_DILATION_PX" \
RENDER_SCALE="${CROP_RENDER_SCALE:-0.25}" \
MIN_VISIBLE_VIEWS="${CROP_MIN_VISIBLE_VIEWS:-3}" \
MIN_VISIBLE_PIXELS="${CROP_MIN_VISIBLE_PIXELS:-2}" \
MIN_VIEW_MASK_FRACTION="${CROP_MIN_VIEW_MASK_FRACTION:-0.5}" \
MIN_SUPPORT_RATIO="${CROP_MIN_SUPPORT_RATIO:-0.6}" \
OVERWRITE="${REPLACE:-0}" \
MASKS_CONTAINER_DIR="$MASKS_CONTAINER_DIR" \
./run_multiview_crop.sh

echo "=== Mesh pipeline completed ==="
if [[ "$SUGAR_MESH_MODE" == "original_gs" ]]; then
    echo "Final Original-GS coarse PLY: $MESH_EXPORT_DIR/coarse.ply"
    echo "Final Original-GS OBJ: $EXPORTED_OBJ"
else
    echo "Final refined PLY: $EXPORTED_REFINED_PLY"
    echo "Final refined OBJ: $EXPORTED_OBJ"
fi
echo "Final cropped mesh: $CROPPED_MESH"
