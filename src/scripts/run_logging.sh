#!/usr/bin/env bash

# Persistent per-run logging for the Scan-to-BIM pipeline.
# The caller must run from the project root because run artifacts live below
# data/10_runs/.

RUN_LOGGING_INITIALIZED=0
RUN_LOGGING_FINALIZED=0
RUN_CURRENT_STEP=""
RUN_CURRENT_STEP_START_EPOCH=""
RUN_CURRENT_STEP_START_ISO=""

run_logging_now() {
    date '+%Y-%m-%dT%H:%M:%S%z'
}

run_logging_detect_video() {
    local raw_dir="$1"
    local candidate

    for candidate in "$raw_dir"/*.mp4 "$raw_dir"/*.mov; do
        [[ -f "$candidate" ]] || continue
        [[ "$(basename "$candidate")" == "output.mp4" ]] && continue
        printf '%s\n' "$candidate"
        return 0
    done

    for candidate in "$raw_dir"/*.mp4 "$raw_dir"/*.mov; do
        if [[ -f "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    printf '%s\n' "unknown_input"
}

run_logging_slug() {
    local value="$1"
    value="${value%.*}"
    value="${value//[^a-zA-Z0-9._-]/_}"
    printf '%s\n' "${value:-unknown_input}"
}

run_logging_init() {
    [[ "$RUN_LOGGING_INITIALIZED" == "1" ]] && return 0

    local raw_dir="${1:-data/01_raw}"
    local input_path
    local input_name
    local video_slug
    local run_timestamp
    local git_commit
    local sugar_commit

    input_path="$(run_logging_detect_video "$raw_dir")"
    input_name="$(basename "$input_path")"
    video_slug="$(run_logging_slug "$input_name")"
    run_timestamp="$(date '+%Y%m%d_%H%M%S')"

    RUN_ID="${video_slug}_${run_timestamp}"
    RUN_DIR="data/10_runs/$RUN_ID"
    RUN_LOG="$RUN_DIR/run.log"
    RUN_REPORT="$RUN_DIR/run.md"
    RUN_STEPS_FILE="$RUN_DIR/.steps.tsv"
    RUN_INPUT_PATH="$input_path"
    RUN_START_ISO="$(run_logging_now)"

    mkdir -p "$RUN_DIR"
    : > "$RUN_STEPS_FILE"

    git_commit="$(git rev-parse --short HEAD 2>/dev/null || printf 'unknown')"
    if [[ -f "third_party/SuGaR/train.py" ]]; then
        sugar_commit="$(git -C third_party/SuGaR rev-parse --short HEAD 2>/dev/null || printf 'unknown')"
    else
        sugar_commit="not-initialized"
    fi

    {
        printf '# Scan-to-BIM Lauf\n\n'
        printf -- '- **Run-ID:** `%s`\n' "$RUN_ID"
        printf -- '- **Input:** `%s`\n' "$RUN_INPUT_PATH"
        printf -- '- **Start Lauf:** `%s`\n' "$RUN_START_ISO"
        printf -- '- **Host UID/GID:** `%s/%s`\n' "${HOST_UID:-unknown}" "${HOST_GID:-unknown}"
        printf -- '- **Git Commit:** `%s`\n' "$git_commit"
        printf -- '- **SuGaR Commit:** `%s`\n' "$sugar_commit"
        printf -- '- **Logdatei:** `%s`\n' "$RUN_LOG"
        printf '\n## Einstellungen\n\n'
    } > "$RUN_REPORT"

    # Keep the complete terminal and Docker output while still showing it live.
    exec > >(tee -a "$RUN_LOG") 2>&1
    RUN_LOGGING_INITIALIZED=1
    trap 'run_logging_finalize "$?"' EXIT

    run_logging_event "RUN START: $RUN_ID"
    printf 'Run-Log: %s\nRun-Report: %s\n' "$RUN_LOG" "$RUN_REPORT"
}

run_logging_event() {
    [[ "$RUN_LOGGING_INITIALIZED" == "1" ]] || return 0
    printf '[%s] [RUN] %s\n' "$(run_logging_now)" "$*"
}

run_log_setting() {
    [[ "$RUN_LOGGING_INITIALIZED" == "1" ]] || return 0
    local key="$1"
    shift
    local value="$*"
    value="${value//$'\n'/ }"
    [[ -n "$value" ]] || value="(nicht gesetzt)"
    printf -- '- **%s:** `%s`\n' "$key" "$value" >> "$RUN_REPORT"
}

run_log_setting_from_var() {
    local variable_name="$1"
    run_log_setting "$variable_name" "${!variable_name-}"
}

run_log_pipeline_settings() {
    local variable_name
    for variable_name in \
        AUTOPILOT RUN_RESOLUTION FRAME_PROFILE_SCOPE SELECTED_VIDEO TEXT_PROMPT \
        SAM3_FRAME_MAX_SIDE SAM3_FRAME_STEP \
        COLMAP_CAMERA_MODEL COLMAP_MAX_FEATURES COLMAP_SEQUENTIAL_OVERLAP \
        COLMAP_GUIDED_MATCHING COLMAP_SIFT_PEAK_THRESHOLD \
        ITERATIONS STAGE2_ITERS ON_THE_FLY \
        FILTER_MIN_OPACITY FILTER_BLACK_THRESHOLD SUGAR_INPUT_ALPHA \
        SUGAR_MESH_MODE REGULARIZATION COARSE_ITERATIONS MESH_VERTICES \
        SURFACE_SAMPLE_COUNT SURFACE_LEVEL POISSON_DEPTH \
        VERTICES_DENSITY_QUANTILE PROJECT_MESH_ON_SURFACE_POINTS \
        LOW_OPACITY_GAUSSIAN_THRESHOLD SURFACE_SAMPLE_SEED \
        INCLUDE_BACKGROUND_MESH USE_GAUSSIAN_DEPTH \
        REFINEMENT_TIME MASK_LEVEL MASK_DILATION_PX NORMAL_MASK_LEVEL \
        TEXTURE_MASK_LEVEL TEXTURE_MASK_DILATION_PX STOP_AFTER_COARSE_MESH \
        RUN_CONSENSUS_CROP SUGAR_RUN_TAG SUGAR_MESH_EXPORT_NAME \
        STS_IMAGES_DIR STS_SFM_DIR \
        STS_MASKS_DIR MASK_MAX_EMPTY_FRACTION EVAL_FRAMES_PATH SUGAR_EVAL_FRAMES_PATH \
        MATRIX_BATCH_ID MATRIX_RESOLUTION_ID MATRIX_VARIANT \
        CENTERLINE_MODE VOXEL_SIZE MIN_PATH_LENGTH BSPLINE_DEGREE \
        BSPLINE_SAMPLES_PER_SEGMENT SEGMENT_CORNERS GEOJSON_SRS FALLBACK_ANCHOR; do
        run_log_setting_from_var "$variable_name"
    done
}

run_logging_store_hf_token() {
    local token="$1"
    local env_path=".env"
    local temporary_path=".env.tmp.$$"

    umask 077
    : > "$temporary_path"
    if [[ -f "$env_path" ]]; then
        while IFS= read -r line; do
            case "$line" in
                HF_TOKEN=*)
                    continue
                    ;;
                *)
                    printf '%s\n' "$line" >> "$temporary_path"
                    ;;
            esac
        done < "$env_path"
    fi
    printf 'HF_TOKEN=%s\n' "$token" >> "$temporary_path"
    chmod 600 "$temporary_path"
    mv "$temporary_path" "$env_path"
}

run_logging_validate_hf_token() {
    local check_output
    local check_path="${RUN_DIR:-.}/.hf-auth-check.$$"

    if docker compose run --rm -e HF_TOKEN="$HF_TOKEN" sam3-preprocess \
        hf auth whoami > "$check_path" 2>&1; then
        rm -f "$check_path"
        return 0
    fi

    check_output="$(<"$check_path")"
    rm -f "$check_path"
    if [[ "$check_output" == *"Invalid user token"* || "$check_output" == *"401 Unauthorized"* ]]; then
        return 1
    fi

    echo "HF-Token-Pruefung konnte wegen eines technischen Container-/Netzwerkfehlers nicht abgeschlossen werden." >&2
    return 2
}

ensure_hf_token() {
    run_step_start "HuggingFace-Authentifizierung"

    if [[ -z "${HF_TOKEN:-}" ]]; then
        read -r -s -p "Bitte HuggingFace Token eingeben (Eingabe bleibt verborgen): " HF_INPUT_TOKEN
        printf '\n'
        if [[ -z "$HF_INPUT_TOKEN" ]]; then
            echo "Kein HuggingFace Token eingegeben." >&2
            run_step_end 1
            return 1
        fi
        run_logging_store_hf_token "$HF_INPUT_TOKEN"
        export HF_TOKEN="$HF_INPUT_TOKEN"
        unset HF_INPUT_TOKEN
    fi

    local validation_status
    if run_logging_validate_hf_token; then
        validation_status=0
    else
        validation_status=$?
    fi
    if [[ "$validation_status" == "0" ]]; then
        echo "HuggingFace-Token erfolgreich validiert."
        run_step_end 0
        return 0
    fi
    if [[ "$validation_status" == "2" ]]; then
        echo "HuggingFace-Token konnte technisch nicht validiert werden. Pipeline wird beendet." >&2
        run_step_end 1
        return 1
    fi

    local attempt
    for attempt in 1 2; do
        echo "Der gespeicherte HuggingFace-Token ist ungueltig oder wurde widerrufen." >&2
        read -r -s -p "Neuen HuggingFace Token eingeben (Versuch $attempt/2, verborgen): " HF_INPUT_TOKEN
        printf '\n'
        if [[ -z "$HF_INPUT_TOKEN" ]]; then
            continue
        fi
        run_logging_store_hf_token "$HF_INPUT_TOKEN"
        export HF_TOKEN="$HF_INPUT_TOKEN"
        unset HF_INPUT_TOKEN
        if run_logging_validate_hf_token; then
            validation_status=0
        else
            validation_status=$?
        fi
        if [[ "$validation_status" == "0" ]]; then
            echo "Neuer HuggingFace-Token erfolgreich validiert."
            run_step_end 0
            return 0
        fi
        if [[ "$validation_status" == "2" ]]; then
            echo "HuggingFace-Token konnte technisch nicht validiert werden. Pipeline wird beendet." >&2
            run_step_end 1
            return 1
        fi
    done

    echo "HuggingFace-Authentifizierung fehlgeschlagen. Pipeline wird vor SAM3 beendet." >&2
    run_step_end 1
    return 1
}

run_step_start() {
    local step_name="$1"
    RUN_CURRENT_STEP="$step_name"
    RUN_CURRENT_STEP_START_EPOCH="$(date +%s)"
    RUN_CURRENT_STEP_START_ISO="$(run_logging_now)"
    run_logging_event "START: $step_name"
}

run_step_end() {
    [[ -n "$RUN_CURRENT_STEP" ]] || return 0
    local status="${1:-0}"
    local end_epoch="$(date +%s)"
    local end_iso="$(run_logging_now)"
    local duration=$((end_epoch - RUN_CURRENT_STEP_START_EPOCH))
    local status_label="OK"
    [[ "$status" == "0" ]] || status_label="FAILED ($status)"

    printf '%s\t%s\t%s\t%s\t%s\n' \
        "$RUN_CURRENT_STEP" "$RUN_CURRENT_STEP_START_ISO" "$end_iso" \
        "$duration" "$status_label" >> "$RUN_STEPS_FILE"
    run_logging_event "END: $RUN_CURRENT_STEP | status=$status_label | duration=${duration}s"
    RUN_CURRENT_STEP=""
    RUN_CURRENT_STEP_START_EPOCH=""
    RUN_CURRENT_STEP_START_ISO=""
}

run_logging_finalize() {
    local status="${1:-0}"
    [[ "$RUN_LOGGING_INITIALIZED" == "1" ]] || return 0
    [[ "$RUN_LOGGING_FINALIZED" == "1" ]] && return 0
    RUN_LOGGING_FINALIZED=1

    if [[ -n "$RUN_CURRENT_STEP" ]]; then
        run_step_end "$status"
    fi

    local end_iso="$(run_logging_now)"
    local status_label="SUCCESS"
    [[ "$status" == "0" ]] || status_label="FAILED (exit $status)"
    run_logging_event "RUN END: $status_label"

    {
        printf '\n## Schritte\n\n'
        printf '| Schritt | Start | Ende | Dauer (s) | Status |\n'
        printf '|---|---|---|---:|---|\n'
        if [[ -s "$RUN_STEPS_FILE" ]]; then
            while IFS=$'\t' read -r step start end duration step_status; do
                printf '| %s | %s | %s | %s | %s |\n' \
                    "$step" "$start" "$end" "$duration" "$step_status"
            done < "$RUN_STEPS_FILE"
        fi
        printf '\n## Abschluss\n\n'
        printf -- '- **Ende Lauf:** `%s`\n' "$end_iso"
        printf -- '- **Status:** `%s`\n' "$status_label"
        printf -- '- **Exit-Code:** `%s`\n' "$status"
    } >> "$RUN_REPORT"
    rm -f "$RUN_STEPS_FILE"
}
