#!/bin/bash
# =============================================================================
# pipeline_lib.sh — Shared function library for the Scan-to-BIM Pipeline
# =============================================================================
# Source this file in any pipeline script:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/src/scripts/pipeline_lib.sh"
# =============================================================================

# --- Constants ---------------------------------------------------------------
readonly RAW_DIR="data/01_raw"
readonly FRAMES_DIR="data/02_frames"
readonly MASKS_DIR="data/03_masks"
readonly SFM_DIR="data/04_sfm"
readonly _3DGS_DIR="data/05_3dgs"
readonly MESH_DIR="data/06_mesh"
readonly CENTERLINE_DIR="data/07_centerline"
readonly GIS_DIR="data/08_gis"
readonly EVAL_DIR="data/09_evaluation"
readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Keep bind-mounted files readable and generated files owned by the invoking
# user on hosts whose UID/GID is not the usual 1000:1000.
export HOST_UID="${HOST_UID:-$(id -u)}"
export HOST_GID="${HOST_GID:-$(id -g)}"

# Pipeline state (set by configure_* functions, consumed by run_* functions)
AUTOPILOT="${AUTOPILOT:-false}"
FRAME_PROFILE_SCOPE="${FRAME_PROFILE_SCOPE:-all}"
RUN_RESOLUTION="${RUN_RESOLUTION:-720p}"

# SAM3 works on the full working-video width of the selected preset, matching
# the archived production runs (720p->1280, qhd->960, low->640).
_sam3_side_for_resolution() {
    case "${1:-720p}" in
        qhd) echo "960" ;;
        low) echo "640" ;;
        *)   echo "1280" ;;
    esac
}

COLMAP_CAMERA_MODEL="${COLMAP_CAMERA_MODEL:-OPENCV}"
COLMAP_MAX_FEATURES="${COLMAP_MAX_FEATURES:-4096}"
COLMAP_SEQUENTIAL_OVERLAP="${COLMAP_SEQUENTIAL_OVERLAP:-15}"
COLMAP_GUIDED_MATCHING="${COLMAP_GUIDED_MATCHING:-0}"
COLMAP_SIFT_PEAK_THRESHOLD="${COLMAP_SIFT_PEAK_THRESHOLD:-0.003}"
SELECTED_VIDEO=""
TEXT_PROMPT=""
# Replay from an existing SuGaR checkpoint keeps the historical 7000 default;
# the full STS configuration below uses the current 7000-run standard.
ITERATIONS=7000
STAGE2_ITERS=5000
ON_THE_FLY=""
FILTER_MIN_OPACITY="${FILTER_MIN_OPACITY:-0.01}"
FILTER_BLACK_THRESHOLD="${FILTER_BLACK_THRESHOLD:-0.08}"
SUGAR_INPUT_ALPHA="${SUGAR_INPUT_ALPHA:-0.999999}"
REGULARIZATION="${REGULARIZATION:-dn_consistency}"
SUGAR_MESH_MODE="${SUGAR_MESH_MODE:-original_gs}"
REFINEMENT_TIME="${REFINEMENT_TIME:-medium}"
MESH_VERTICES="${MESH_VERTICES:-200000}"
SURFACE_SAMPLE_COUNT="${SURFACE_SAMPLE_COUNT:-5000000}"
MASK_LEVEL="${MASK_LEVEL:-default}"
MASK_DILATION_PX="${MASK_DILATION_PX:-0}"
NORMAL_MASK_LEVEL="${NORMAL_MASK_LEVEL:-middle}"
TEXTURE_MASK_LEVEL="${TEXTURE_MASK_LEVEL:-default}"
TEXTURE_MASK_DILATION_PX="${TEXTURE_MASK_DILATION_PX:-0}"
STOP_AFTER_COARSE_MESH="${STOP_AFTER_COARSE_MESH:-0}"
RUN_CONSENSUS_CROP="${RUN_CONSENSUS_CROP:-0}"
CENTERLINE_MODE="${CENTERLINE_MODE:-single}"
VOXEL_SIZE="${VOXEL_SIZE:-0.1}"
MIN_PATH_LENGTH="${MIN_PATH_LENGTH:-0.75}"
BSPLINE_DEGREE="${BSPLINE_DEGREE:-10}"
BSPLINE_SAMPLES_PER_SEGMENT="${BSPLINE_SAMPLES_PER_SEGMENT:-4}"
SEGMENT_CORNERS="${SEGMENT_CORNERS:-0}"
GEOJSON_SRS="${GEOJSON_SRS:-EPSG:25832}"
FALLBACK_ANCHOR="${FALLBACK_ANCHOR:-567028.563,5516784.082,177}"
STS_IMAGES_DIR="${STS_IMAGES_DIR:-/data/04_sfm/undistorted/images}"
STS_SFM_DIR="${STS_SFM_DIR:-/data/04_sfm/undistorted}"

# --- Logging -----------------------------------------------------------------
_log() {
    local level="$1"; shift
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $*"
}

log_info()  { _log "INFO"  "$@"; }
log_warn()  { _log "WARN"  "$@" >&2; }
log_error() { _log "ERROR" "$@" >&2; }
log_step()  { echo ""; echo "=========================================================="; _log "STEP" "$@"; echo "=========================================================="; }

# --- Validation Helpers ------------------------------------------------------
validate_dir_not_empty() {
    local dir_path="$1"
    local description="$2"
    if [[ ! -d "$dir_path" ]] || [[ -z "$(ls -A "$dir_path" 2>/dev/null)" ]]; then
        log_error "$description: Verzeichnis '$dir_path' existiert nicht oder ist leer."
        return 1
    fi
    local count
    count=$(find "$dir_path" -maxdepth 1 -type f | wc -l)
    log_info "$description: $count Dateien in '$dir_path' gefunden."
    return 0
}

validate_file_exists() {
    local file_path="$1"
    local description="$2"
    if [[ ! -f "$file_path" ]]; then
        log_error "$description: Datei '$file_path' nicht gefunden."
        return 1
    fi
    local size
    size=$(stat --printf="%s" "$file_path" 2>/dev/null || echo "0")
    if [[ "$size" -eq 0 ]]; then
        log_warn "$description: Datei '$file_path' ist leer (0 Bytes)."
        return 1
    fi
    log_info "$description: '$file_path' OK ($(numfmt --to=iec "$size" 2>/dev/null || echo "$size bytes"))"
    return 0
}

validate_masks_quality() {
    # Check that at least some masks are non-empty
    local masks_dir="$1"
    local min_nonempty="${2:-1}"

    if [[ ! -d "$masks_dir" ]]; then
        log_error "Maskenverzeichnis '$masks_dir' existiert nicht."
        return 1
    fi

    local total_masks nonempty_masks
    total_masks=$(find "$masks_dir" -maxdepth 1 -name "frame_*_obj_001.png" -type f | wc -l)
    if [[ "$total_masks" -eq 0 ]]; then
        # Check hierarchical masks
        total_masks=$(find "$masks_dir" -name "middle.png" -type f | wc -l)
    fi

    if [[ "$total_masks" -eq 0 ]]; then
        log_error "Keine Masken in '$masks_dir' gefunden."
        return 1
    fi

    log_info "Masken-Qualitaet: $total_masks Masken-Dateien gefunden."
    return 0
}

validate_colmap_model() {
    local sparse_dir="$1"
    if [[ ! -d "$sparse_dir" ]]; then
        log_error "COLMAP Sparse-Verzeichnis '$sparse_dir' nicht gefunden."
        return 1
    fi

    # Check for COLMAP output files in any subdirectory
    local found_model=false
    for subdir in "$sparse_dir" "$sparse_dir"/*/; do
        if [[ -f "$subdir/cameras.bin" ]] || [[ -f "$subdir/cameras.txt" ]]; then
            if [[ -f "$subdir/images.bin" ]] || [[ -f "$subdir/images.txt" ]]; then
                if [[ -f "$subdir/points3D.bin" ]] || [[ -f "$subdir/points3D.txt" ]]; then
                    found_model=true
                    log_info "COLMAP-Modell gefunden in: $subdir"
                    break
                fi
            fi
        fi
    done

    if [[ "$found_model" == "false" ]]; then
        log_error "Kein vollstaendiges COLMAP-Modell (cameras + images + points3D) gefunden in '$sparse_dir'."
        return 1
    fi
    return 0
}

# --- Environment Setup -------------------------------------------------------
load_env() {
    if [[ -f .env ]]; then
        # shellcheck disable=SC2046
        export $(grep -v '^#' .env | grep -v '^\s*$' | xargs)
        log_info ".env Datei geladen."
    fi
}

check_hf_token() {
    load_env
    ensure_hf_token
}

# --- Autopilot Configuration -------------------------------------------------
configure_autopilot() {
    if [[ "$AUTOPILOT" == "true" ]]; then
        log_info "Autopilot-Modus bereits aktiviert (via Umgebungsvariable oder Parameter)."
        return
    fi

    read -rp "Pipeline im Autopilot-Modus ausfuehren? (Alle Standardvorgaben automatisch) (y/n) [Default: n]: " USER_AUTOPILOT
    if [[ "$USER_AUTOPILOT" =~ ^[Yy]$ ]]; then
        AUTOPILOT="true"
        log_info "Autopilot-Modus AKTIVIERT."
    else
        AUTOPILOT="false"
    fi
}

# --- Video Input Configuration -----------------------------------------------
configure_frame_profile_scope() {
    if [[ "$AUTOPILOT" == "true" ]]; then
        FRAME_PROFILE_SCOPE="${FRAME_PROFILE_SCOPE:-all}"
        log_info "Frame-Profil: $FRAME_PROFILE_SCOPE"
        return
    fi

    while true; do
        read -rp "Frame-/Pipeline-Profil: all oder colmap-stop/EXPLAIN [Default: all]: " USER_SCOPE
        USER_SCOPE=${USER_SCOPE:-all}
        if [[ "${USER_SCOPE^^}" == "EXPLAIN" ]]; then
            explain_frame_profile_scope
            USER_SCOPE=""
            continue
        fi
        break
    done
    case "${USER_SCOPE,,}" in
        all)
            FRAME_PROFILE_SCOPE="all"
            ;;
        colmap|colmap-only|colmap-stop)
            FRAME_PROFILE_SCOPE="colmap"
            log_warn "COLMAP-stop gewaehlt. SAM3 laeuft fuer Frames/Masken; danach stoppt die Pipeline vor GCP/STS/SuGaR."
            ;;
        *)
            log_warn "Ungueltige Auswahl, verwende all."
            FRAME_PROFILE_SCOPE="all"
            ;;
    esac
}

explain_frame_profile_scope() {
    echo ""
    echo "  all: Der Frame-Satz (Aufloesung laut Lauf-Preset) gilt fuer SAM3, COLMAP,"
    echo "       STS und SuGaR. Das ist der normale Vollpipeline-Modus."
    echo "  colmap-stop: Diagnoseprofil fuer die SfM-Stufe; der Replay stoppt danach"
    echo "       vor GCP/STS/SuGaR. Die Rohmasken werden VOR dem Stopp in die ideale"
    echo "       Domäne gewarpt, sodass der Zwischenstand mit '--from sts'"
    echo "       fortsetzbar bleibt (kein erneuter SAM3-/COLMAP-Lauf noetig)."
    echo ""
}

explain_colmap_values() {
    echo ""
    echo "  OPENCV: getrennte Brennweiten sowie radiale/tangentiale Parameter."
    echo "          Aktueller Produktionsstandard; in der Matrixauswertung bei"
    echo "          720p und 5 FPS die besten maskierten Objektmetriken."
    echo "  SIMPLE_RADIAL: eine Brennweite, Hauptpunkt und ein radialer Parameter."
    echo "  SIMPLE_PINHOLE: ideale Kamera ohne Verzeichnung; setzt bereits"
    echo "                  entzerrte Eingabebilder voraus. Fuer PINHOLE/"
    echo "                  SIMPLE_PINHOLE wird image_undistorter uebersprungen."
    echo "  4096 SIFT-Merkmale: aktueller Kompromiss aus Punktdichte und Laufzeit."
    echo "  Guided Matching: zusaetzliche Zuordnung, im Test deutlich langsamer."
    echo "  Overlap: Anzahl zeitlicher Nachbarbilder im Sequential Matching."
    echo ""
}

configure_colmap_values() {
    if [[ "$AUTOPILOT" == "true" ]]; then
        log_info "COLMAP-Profil: ${COLMAP_CAMERA_MODEL}, ${COLMAP_MAX_FEATURES} SIFT, overlap=${COLMAP_SEQUENTIAL_OVERLAP}, guided=${COLMAP_GUIDED_MATCHING}"
        return
    fi
    while true; do
        read -rp "COLMAP-Kameramodell (SIMPLE_RADIAL/SIMPLE_PINHOLE/PINHOLE/OPENCV oder EXPLAIN) [Default: $COLMAP_CAMERA_MODEL]: " value
        value=${value:-$COLMAP_CAMERA_MODEL}
        if [[ "${value^^}" == "EXPLAIN" ]]; then explain_colmap_values; continue; fi
        if [[ "$value" =~ ^(SIMPLE_RADIAL|SIMPLE_PINHOLE|PINHOLE|OPENCV)$ ]]; then COLMAP_CAMERA_MODEL="$value"; break; fi
        log_warn "Ungueltiges Kameramodell."
    done
    while true; do
        read -rp "COLMAP SIFT-Merkmale (positive Zahl oder EXPLAIN) [Default: $COLMAP_MAX_FEATURES]: " value
        value=${value:-$COLMAP_MAX_FEATURES}
        if [[ "${value^^}" == "EXPLAIN" ]]; then explain_colmap_values; continue; fi
        if [[ "$value" =~ ^[1-9][0-9]*$ ]]; then COLMAP_MAX_FEATURES="$value"; break; fi
        log_warn "Bitte eine positive ganze Zahl eingeben."
    done
    while true; do
        read -rp "Sequential-Matching-Overlap (positive Zahl oder EXPLAIN) [Default: $COLMAP_SEQUENTIAL_OVERLAP]: " value
        value=${value:-$COLMAP_SEQUENTIAL_OVERLAP}
        if [[ "${value^^}" == "EXPLAIN" ]]; then explain_colmap_values; continue; fi
        if [[ "$value" =~ ^[1-9][0-9]*$ ]]; then COLMAP_SEQUENTIAL_OVERLAP="$value"; break; fi
        log_warn "Bitte eine positive ganze Zahl eingeben."
    done
    while true; do
        read -rp "Guided Matching aktivieren? 0/1 oder EXPLAIN [Default: $COLMAP_GUIDED_MATCHING]: " value
        value=${value:-$COLMAP_GUIDED_MATCHING}
        if [[ "${value^^}" == "EXPLAIN" ]]; then explain_colmap_values; continue; fi
        if [[ "$value" == "0" || "$value" == "1" ]]; then COLMAP_GUIDED_MATCHING="$value"; break; fi
        log_warn "Bitte 0 oder 1 eingeben."
    done
    while true; do
        read -rp "SIFT-Peak-Threshold oder EXPLAIN [Default: $COLMAP_SIFT_PEAK_THRESHOLD]: " value
        value=${value:-$COLMAP_SIFT_PEAK_THRESHOLD}
        if [[ "${value^^}" == "EXPLAIN" ]]; then explain_colmap_values; continue; fi
        if [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]]; then COLMAP_SIFT_PEAK_THRESHOLD="$value"; break; fi
        log_warn "Bitte eine nichtnegative Zahl eingeben."
    done
}

configure_video_input() {
    local raw_video=""
    local compressed_video=""
    local detected_width=""
    local detected_height=""
    local orientation_hint="unknown"

    for candidate in "$RAW_DIR"/*; do
        [[ -e "$candidate" ]] || continue
        case "${candidate,,}" in
            *.mp4|*.mov)
                if [[ "$(basename "$candidate")" == "output.mp4" ]]; then
                    compressed_video="$candidate"
                elif [[ -z "$raw_video" ]]; then
                    raw_video="$candidate"
                fi
                ;;
        esac
    done

    if [[ -n "$compressed_video" ]]; then
        log_info "Gefundenes komprimiertes Video: $compressed_video"
        if [[ "$AUTOPILOT" == "true" ]]; then
            log_info "Autopilot: Verwende komprimiertes Video."
            SELECTED_VIDEO="$compressed_video"
            return
        fi
        read -rp "Komprimiertes Video fuer SAM3 verwenden? (y/n) [Default: y]: " USE_COMPRESSED
        if [[ -z "$USE_COMPRESSED" || "$USE_COMPRESSED" =~ ^[Yy]$ ]]; then
            SELECTED_VIDEO="$compressed_video"
            return
        fi
    fi

    if [[ -z "$raw_video" ]]; then
        if [[ -n "$compressed_video" ]]; then
            log_info "Kein weiteres Rohvideo gefunden. Verwende $compressed_video"
            SELECTED_VIDEO="$compressed_video"
            return
        fi
        log_warn "Kein Video in $RAW_DIR gefunden."
        return
    fi

    log_info "Originalvideo erkannt: $raw_video"

    # Detect video resolution
    local probe_output
    probe_output=$(docker compose run --rm sam3-preprocess ffprobe -v error -select_streams v:0 \
        -show_entries stream=width,height -of csv=p=0:s=x \
        "/data/01_raw/$(basename "$raw_video")" 2>/dev/null | tr -d '\r' | head -n 1)
    if [[ "$probe_output" =~ ^([0-9]+)x([0-9]+)$ ]]; then
        detected_width="${BASH_REMATCH[1]}"
        detected_height="${BASH_REMATCH[2]}"
        if (( detected_height > detected_width )); then
            orientation_hint="portrait"
        else
            orientation_hint="landscape"
        fi
        log_info "Erkannte Videoaufloesung: ${detected_width}x${detected_height} (${orientation_hint})"
    else
        log_warn "Konnte Videoorientierung nicht automatisch erkennen."
    fi

    if [[ "$AUTOPILOT" == "true" ]]; then
        log_info "Autopilot: Erzeuge komprimiertes Arbeitsvideo mit Standard-Vorgaben..."
        _create_compressed_video "$raw_video" "$orientation_hint" 0
        return
    fi

    echo "Optional kann vor SAM3 ein komprimiertes Arbeitsvideo erzeugt werden."
    echo "Warum: kleinere Aufloesung/FPS sparen VRAM, I/O und Laufzeit."
    echo "Empfohlene COLMAP-Defaults: 1280x720, 5 FPS, Plain-SIFT 4096, Guided Matching aus"
    echo "Video-Defaults: transpose=0, fps=5, codec=libx264, crf=18, preset=medium"
    if [[ "$orientation_hint" == "portrait" ]]; then
        echo "WICHTIG: Hochkant erkannt. Bitte nur drehen, wenn das Bild sichtbar falsch ausgerichtet ist."
    fi
    read -rp "Komprimiertes Arbeitsvideo erzeugen? (y/n) [Default: y]: " CREATE_COMPRESSED

    if [[ -z "$CREATE_COMPRESSED" || "$CREATE_COMPRESSED" =~ ^[Yy]$ ]]; then
        _create_compressed_video_interactive "$raw_video" "$orientation_hint"
    else
        SELECTED_VIDEO="$raw_video"
    fi
}

_create_compressed_video() {
    local raw_video="$1"
    local orientation_hint="$2"
    local transpose_value="${3:-0}"
    local target_width=1280
    local target_height=720
    local target_fps=5
    local target_crf=18
    local target_preset="medium"

    if [[ "$orientation_hint" == "portrait" ]]; then
        target_width=1080
        target_height=1920
    fi

    local vf_chain=""
    if [[ "$transpose_value" != "0" ]]; then
        vf_chain="transpose=${transpose_value},"
    fi
    vf_chain+="scale=${target_width}:${target_height}:force_original_aspect_ratio=decrease,pad=${target_width}:${target_height}:(ow-iw)/2:(oh-ih)/2:black,fps=${target_fps}"

    log_info "Erzeuge komprimiertes Arbeitsvideo (${target_width}x${target_height}, ${target_fps}fps, crf=${target_crf})..."
    run_step_start "Video-Preprocessing"
    docker compose run --rm sam3-preprocess ffmpeg -y -i "/data/01_raw/$(basename "$raw_video")" \
        -vf "$vf_chain" \
        -c:v libx264 -crf "$target_crf" -preset "$target_preset" \
        -an "/data/01_raw/output.mp4"
    run_step_end 0

    SELECTED_VIDEO="$RAW_DIR/output.mp4"
}

_create_compressed_video_interactive() {
    local raw_video="$1"
    local orientation_hint="$2"
    local default_width=1280
    local default_height=720

    if [[ "$orientation_hint" == "portrait" ]]; then
        default_width=1080
        default_height=1920
    fi

    read -rp "Transpose? 0=keine, 1=90CW, 2=90CCW [Default: 0]: " USER_TRANSPOSE
    local transpose_value=${USER_TRANSPOSE:-0}

    read -rp "Zielbreite [Default: ${default_width}]: " USER_WIDTH
    local target_width=${USER_WIDTH:-$default_width}

    read -rp "Zielhoehe [Default: ${default_height}]: " USER_HEIGHT
    local target_height=${USER_HEIGHT:-$default_height}

    read -rp "Ziel-FPS [Default: 5]: " USER_FPS
    local target_fps=${USER_FPS:-5}

    read -rp "CRF Qualitaet [Default: 18]: " USER_CRF
    local target_crf=${USER_CRF:-18}

    read -rp "x264 Preset [Default: medium]: " USER_PRESET
    local target_preset=${USER_PRESET:-medium}

    if [[ "$orientation_hint" == "portrait" && "$target_width" -gt "$target_height" ]]; then
        log_warn "Hochkant erkannt, aber Ziel ist Querformat (${target_width}x${target_height})."
    fi

    local vf_chain=""
    if [[ "$transpose_value" != "0" ]]; then
        vf_chain="transpose=${transpose_value},"
    fi
    vf_chain+="scale=${target_width}:${target_height}:force_original_aspect_ratio=decrease,pad=${target_width}:${target_height}:(ow-iw)/2:(oh-ih)/2:black,fps=${target_fps}"

    log_info "Erzeuge komprimiertes Arbeitsvideo..."
    docker compose run --rm sam3-preprocess ffmpeg -y -i "/data/01_raw/$(basename "$raw_video")" \
        -vf "$vf_chain" \
        -c:v libx264 -crf "$target_crf" -preset "$target_preset" \
        -an "/data/01_raw/output.mp4"

    SELECTED_VIDEO="$RAW_DIR/output.mp4"
}

# --- STS Training Configuration ----------------------------------------------
configure_sts_training() {
    log_step "STS Gaussian Splatting Training Configuration"

    if [[ "$AUTOPILOT" == "true" ]]; then
        ITERATIONS=7000
        STAGE2_ITERS=5000
        ON_THE_FLY=""
        log_info "Autopilot: 7000 Gesamtiterationen (5000 Objektphase + 2000 All-Object-Phase) ohne On-The-Fly-Laden."
    else
        read -rp "Total training iterations (5000 Objektphase + 2000 All-Object-Phase = 7000) [Default: 7000]: " USER_ITERATIONS
        ITERATIONS=${USER_ITERATIONS:-7000}

        local DEFAULT_STAGE2=5000
        read -rp "Objekt-/Stage-2-Iterationen innerhalb des Gesamttrainings [Default: $DEFAULT_STAGE2]: " USER_STAGE2
        STAGE2_ITERS=${USER_STAGE2:-$DEFAULT_STAGE2}

        read -rp "GPU-saving 'on-the-fly' image loading? (y/n) [Default: n]: " USER_LY
        if [[ "$USER_LY" =~ ^[Yy]$ ]]; then
            ON_THE_FLY="--load2gpu_on_the_fly"
        else
            ON_THE_FLY=""
        fi
    fi

    echo "--------------------------------------------------------"
    echo "Active Configurations:"
    echo " - Total Optimization Iterations: $ITERATIONS"
    echo " - Stage 2 Fine-Tuning Iterations: $STAGE2_ITERS"
    echo " - GPU On-The-Fly Mode: ${ON_THE_FLY:-Disabled}"
    echo "--------------------------------------------------------"
}

# --- Pipeline Step Runners ----------------------------------------------------

run_step_gcp() {
    run_step_start "GCP-Vorbereitung"
    log_step "[Step 0/5] Preparing relative GCP coordinates..."
    docker compose run --rm sam3-preprocess python3 /app/src/python/prepare_gcp.py
    run_step_end 0
}

run_step_sam3() {
    run_step_start "SAM3-Maskenextraktion"
    log_step "[Step 1/5] SAM 3.1 Mask Extraction: '$TEXT_PROMPT'"

    # Mirror the inline flow: SAM3 always receives an explicit max side that
    # follows the run preset (720p->1280, qhd->960, low->640).
    local sam3_side="${SAM3_FRAME_MAX_SIDE:-$(_sam3_side_for_resolution "${RUN_RESOLUTION:-720p}")}"
    if [[ -n "$SELECTED_VIDEO" ]]; then
        log_info "Eingabevideo: $SELECTED_VIDEO (SAM3_FRAME_MAX_SIDE=$sam3_side)"
        docker compose run --rm -e SAM3_FRAME_MAX_SIDE="$sam3_side" sam3-preprocess python3 /app/src/python/extract_masks_notebook_flow.py \
            --prompt "$TEXT_PROMPT" \
            --input-path "/data/01_raw/$(basename "$SELECTED_VIDEO")"
    else
        docker compose run --rm -e SAM3_FRAME_MAX_SIDE="$sam3_side" sam3-preprocess python3 /app/src/python/extract_masks_notebook_flow.py \
            --prompt "$TEXT_PROMPT"
    fi

    log_info "Exporting non-interactive SAM3 mask review samples..."
    docker compose run --rm sam3-preprocess \
        python3 /app/tools/export_mask_review_samples.py \
        --frames-dir /data/02_frames \
        --masks-dir /data/03_masks \
        --mask-name middle \
        --output-dir /data/03_masks/_review_samples \
        --non-interactive \
        --manifest /data/03_masks/_review_samples/review_manifest.json

    # Validate output
    validate_masks_quality "$MASKS_DIR" || {
        log_error "Maskenextraktion fehlgeschlagen oder leer. Pipeline stoppt."
        return 1
    }
    run_step_end 0
}

run_step_colmap() {
    run_step_start "COLMAP-SfM"
    log_step "[Step 2/5] Running COLMAP Structure from Motion..."
    docker compose run --rm \
        -e COLMAP_CAMERA_MODEL="$COLMAP_CAMERA_MODEL" \
        -e COLMAP_MAX_FEATURES="$COLMAP_MAX_FEATURES" \
        -e COLMAP_SEQUENTIAL_OVERLAP="$COLMAP_SEQUENTIAL_OVERLAP" \
        -e COLMAP_GUIDED_MATCHING="$COLMAP_GUIDED_MATCHING" \
        -e COLMAP_SIFT_PEAK_THRESHOLD="$COLMAP_SIFT_PEAK_THRESHOLD" \
        colmap-sfm /app/src/scripts/run_sfm.sh

    # Validate output
    validate_colmap_model "$SFM_DIR/sparse" || {
        log_error "COLMAP hat kein gueltiges Sparse-Modell erzeugt."
        return 1
    }
    run_step_end 0
}

breakpoint_cloudcompare() {
    run_step_start "GCP-Picking / CloudCompare"
    echo "=========================================================="
    echo "BREAKPOINT: Bitte oeffne die Sparse Point Cloud in CloudCompare"
    echo "auf dem Host-System. Picke die GCP-Koordinatenpunkte, berechne"
    echo "die 4x4-Transformationsmatrix und speichere sie in data/04_sfm/matrix.txt"
    echo "=========================================================="
    read -rp "Sobald die Transformationsmatrix gespeichert ist, druecke [Enter]..."

    validate_file_exists "$SFM_DIR/matrix.txt" "Transformationsmatrix" || {
        log_warn "matrix.txt nicht gefunden. Fortfahren auf eigene Gefahr."
    }
    run_step_end 0
}

run_step_mask_warp() {
    # Warpt die Rohmasken nach COLMAP in die ideale Bilddomaene (identisch zum
    # Inline-Vollauf). Wird im Replay-Dispatcher nach einem frischen COLMAP-Lauf
    # aufgerufen, damit auch Replays ab gcp/sam3/colmap dieselbe Gate-/Warp-Kette
    # nutzen. Replays ab sts/sugar/postprocess erwarten weiterhin bereits
    # ideale Masken und rufen diese Funktion nicht auf.
    local ideal_masks_host="${IDEAL_MASKS_HOST_DIR:-data/03_masks_ideal}"
    local sts_masks_dir="${STS_MASKS_DIR:-/data/03_masks_ideal}"
    local max_empty="${MASK_MAX_EMPTY_FRACTION:-0.30}"
    run_step_start "Masken-Warp in die ideale Bilddomaene"
    echo "Warpe Rohmasken aus /data/03_masks in die COLMAP-Idealbilddomaene..."
    rm -rf "$ideal_masks_host"
    mkdir -p "$ideal_masks_host"
    docker compose run --rm sam3-preprocess \
        python3 /app/src/python/warp_masks_to_undistorted.py \
        --raw-masks-dir /data/03_masks \
        --output-dir "$sts_masks_dir" \
        --raw-sfm-txt /data/04_sfm/sparse_txt \
        --ideal-sfm-txt /data/04_sfm/undistorted/sparse_txt \
        --raw-images-dir /data/02_frames \
        --ideal-images-dir /data/04_sfm/undistorted/images \
        --report "$sts_masks_dir/mask_warp_report.json"
    docker compose run --rm sam3-preprocess \
        python3 /app/src/python/validate_mask_coverage.py \
        --frames-dir /data/04_sfm/undistorted/images \
        --masks-dir "$sts_masks_dir" \
        --mask-name middle \
        --max-empty-fraction "$max_empty" \
        --report "$sts_masks_dir/mask_coverage_report.json"
    run_step_end 0
}

run_step_sts_prep() {
    run_step_start "STS-Workspace und Initialisierung"
    log_step "[Step 3/5] Setting up Segment-then-Splat (STS) workspace..."
    docker compose run --rm \
        -e STS_IMAGES_DIR="$STS_IMAGES_DIR" \
        -e STS_SFM_DIR="$STS_SFM_DIR" \
        -e STS_MASKS_DIR="${STS_MASKS_DIR:-/data/03_masks}" \
        -e EVAL_FRAMES_PATH="${EVAL_FRAMES_PATH:-}" \
        sam3-preprocess python3 /app/src/python/prep_sts_scene.py

    log_info "Running STS object-specific 3D point cloud initialization..."
    docker compose run --rm sts-training python3 helpers/object_specific_initialization.py --scene_root /data/05_3dgs
    run_step_end 0
}

run_step_sts_train() {
    run_step_start "STS-Training"
    log_step "[Step 3/5] Starting STS Object-Specific 3DGS Training..."
    docker compose run --rm sts-training python3 train.py \
        -s /data/05_3dgs \
        -m /data/05_3dgs/output \
        --eval \
        --iterations "$ITERATIONS" \
        --stage2_iters "$STAGE2_ITERS" \
        --save_iterations "$ITERATIONS" \
        --test_iterations "$ITERATIONS" \
        $ON_THE_FLY
    run_step_end 0
}

run_step_filter_cable() {
    run_step_start "STS-Objektfilterung und SuGaR-Eingang"
    log_step "[Step 3.5/5] Preparing the standard SuGaR geometry input..."

    docker compose run --rm sts-training python3 -c "import os, shutil; base='/data/05_3dgs/output/point_cloud/iteration_${ITERATIONS}'; src=f'{base}/point_cloud.ply'; dst=f'{base}/point_cloud_full_scene.ply'; os.path.exists(src) or (_ for _ in ()).throw(FileNotFoundError(src)); shutil.copy2(src, dst)"
    ITERATIONS="$ITERATIONS" \
    FILTER_MIN_OPACITY="$FILTER_MIN_OPACITY" \
    FILTER_BLACK_THRESHOLD="$FILTER_BLACK_THRESHOLD" \
    SUGAR_INPUT_ALPHA="$SUGAR_INPUT_ALPHA" \
    "$PROJECT_ROOT/prepare_sugar_input.sh"
    run_log_pipeline_settings
    run_step_end 0
}

run_step_sugar() {
    run_step_start "SuGaR-Meshing"
    log_step "[Step 4/5] Running selected object mesh route (default: Original-STS-GS A)..."
    if [[ "$SUGAR_MESH_MODE" == "original_gs" ]]; then
        COARSE_ITERATIONS=""
    elif [[ "$REGULARIZATION" == "dn_consistency" ]]; then
        COARSE_ITERATIONS="${COARSE_ITERATIONS:-9000}"
    else
        COARSE_ITERATIONS=""
    fi
    if [[ "$SUGAR_MESH_MODE" == "original_gs" ]]; then
        SUGAR_RUN_TAG="${SUGAR_RUN_TAG:-library_i${ITERATIONS}_original_gs_v${MESH_VERTICES}}"
    else
        SUGAR_RUN_TAG="${SUGAR_RUN_TAG:-library_i${ITERATIONS}_c${COARSE_ITERATIONS:-default}_v${MESH_VERTICES}}"
    fi
    SUGAR_MESH_EXPORT_NAME="${SUGAR_MESH_EXPORT_NAME:-$SUGAR_RUN_TAG}"
    run_log_pipeline_settings

    MASKED_SUGAR_INTERACTIVE="${SUGAR_REPLAY_INTERACTIVE:-0}" \
    ITERATIONS="$ITERATIONS" \
    SUGAR_MESH_MODE="$SUGAR_MESH_MODE" \
    REGULARIZATION="$REGULARIZATION" \
    COARSE_ITERATIONS="$COARSE_ITERATIONS" \
    REFINEMENT_TIME="$REFINEMENT_TIME" \
    MESH_VERTICES="$MESH_VERTICES" \
    SURFACE_SAMPLE_COUNT="$SURFACE_SAMPLE_COUNT" \
    MASK_LEVEL="$MASK_LEVEL" \
    MASK_DILATION_PX="$MASK_DILATION_PX" \
    NORMAL_MASK_LEVEL="$NORMAL_MASK_LEVEL" \
    TEXTURE_MASK_LEVEL="$TEXTURE_MASK_LEVEL" \
    TEXTURE_MASK_DILATION_PX="$TEXTURE_MASK_DILATION_PX" \
    STOP_AFTER_COARSE_MESH="$STOP_AFTER_COARSE_MESH" \
    RUN_CONSENSUS_CROP="$RUN_CONSENSUS_CROP" \
    SUGAR_RUN_TAG="$SUGAR_RUN_TAG" \
    SUGAR_MESH_EXPORT_NAME="$SUGAR_MESH_EXPORT_NAME" \
    FILTERED_PLY="data/05_3dgs/output/point_cloud/iteration_${ITERATIONS}/point_cloud_filtered_opacity999999.ply" \
    "$PROJECT_ROOT/run_masked_sugar.sh"
    run_step_end 0
}

run_step_postprocess() {
    run_step_start "Centerline und Georeferenzierung"
    log_step "[Step 5/5] Extracting centerline and georeferencing to UTM..."
    docker compose run --rm \
        -e INPUT_MESH="/data/06_mesh/${SUGAR_MESH_EXPORT_NAME}/refined.obj" \
        -e CENTERLINE_MODE="$CENTERLINE_MODE" \
        -e VOXEL_SIZE="$VOXEL_SIZE" \
        -e MIN_PATH_LENGTH="$MIN_PATH_LENGTH" \
        -e BSPLINE_DEGREE="$BSPLINE_DEGREE" \
        -e BSPLINE_SAMPLES_PER_SEGMENT="$BSPLINE_SAMPLES_PER_SEGMENT" \
        -e SEGMENT_CORNERS="$SEGMENT_CORNERS" \
        -e GEOJSON_SRS="$GEOJSON_SRS" \
        -e FALLBACK_ANCHOR="$FALLBACK_ANCHOR" \
        post-processing /app/src/scripts/postprocess.sh
    run_step_end 0
}

# --- Composite Runners -------------------------------------------------------

# Run the complete pipeline from a given starting point
# Usage: run_pipeline_from <step>
# Steps: gcp, sam3, colmap, sts, sugar, postprocess
run_pipeline_from() {
    local start_step="${1:-gcp}"
    local steps_order=(gcp sam3 colmap sts sugar postprocess)
    local started=false

    for step in "${steps_order[@]}"; do
        if [[ "$step" == "$start_step" ]]; then
            started=true
        fi
        [[ "$started" == "false" ]] && continue

        case "$step" in
            gcp)
                run_step_gcp
                ;;
            sam3)
                check_hf_token
                if [[ -z "$TEXT_PROMPT" ]]; then
                    read -rp "Maskierungs-Prompt eingeben (z.B. 'cable', 'pipe'): " TEXT_PROMPT
                fi
                configure_frame_profile_scope
                configure_video_input
                run_log_pipeline_settings
                run_step_sam3 || return 1
                ;;
            colmap)
                configure_colmap_values
                run_log_pipeline_settings
                run_step_colmap || return 1
                # The mask warp runs in BOTH frame-profile scopes so that a
                # colmap-stop replay leaves a continuation-ready state
                # ('--from sts' works without re-running SAM3/COLMAP).
                run_step_mask_warp || return 1
                if [[ "$FRAME_PROFILE_SCOPE" == "colmap" ]]; then
                    log_info "COLMAP-only-Profil abgeschlossen; Masken sind gewarpt, Fortsetzung mit '--from sts' moeglich."
                    return 0
                fi
                breakpoint_cloudcompare
                ;;
            sts)
                run_step_sts_prep
                configure_sts_training
                run_log_pipeline_settings
                run_step_sts_train
                run_step_filter_cable
                ;;
            sugar)
                # A SuGaR replay is normally an interactive parameter study.
                # The full pipeline has already collected these values inline,
                # but the replay dispatcher used to call run_step_sugar with
                # silent defaults, which made --from sugar unexpectedly retrain
                # c9000/medium/200k without asking the user.
                configure_autopilot
                if [[ "$AUTOPILOT" == "true" ]]; then
                    SUGAR_REPLAY_INTERACTIVE=0
                else
                    SUGAR_REPLAY_INTERACTIVE=1
                fi
                run_step_sugar
                if [[ "$STOP_AFTER_COARSE_MESH" == "1" ]]; then
                    log_info "SuGaR replay stopped after Coarse mesh; postprocessing is intentionally skipped."
                    return 0
                fi
                ;;
            postprocess)
                run_step_postprocess
                ;;
        esac
    done
}
