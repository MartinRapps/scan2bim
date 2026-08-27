#!/usr/bin/env bash
set -euo pipefail

# Conservative semantic cleanup of the latest textured SuGaR mesh.  Override
# the defaults through environment variables, for example:
#   RENDER_SCALE=0.5 ./run_multiview_crop.sh
#   MESH_PATH=data/sugar_output/refined_mesh/05_3dgs/example.obj ./run_multiview_crop.sh

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

find_latest_mesh() {
    find data/sugar_output/refined_mesh -type f -name '*.obj' -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr \
        | head -n 1 \
        | cut -d' ' -f2-
}

MESH_PATH="${MESH_PATH:-$(find_latest_mesh)}"
if [[ -z "$MESH_PATH" || ! -f "$MESH_PATH" ]]; then
    echo "Error: No textured SuGaR OBJ mesh found under data/sugar_output/refined_mesh/." >&2
    echo "Set MESH_PATH to a project-relative OBJ path and try again." >&2
    exit 2
fi

case "$MESH_PATH" in
    data/*)
        MESH_CONTAINER_PATH="/$MESH_PATH"
        ;;
    "$PROJECT_ROOT"/data/*)
        MESH_CONTAINER_PATH="/data/${MESH_PATH#"$PROJECT_ROOT"/data/}"
        ;;
    *)
        echo "Error: MESH_PATH must be below this project's data/ directory." >&2
        exit 2
        ;;
esac

MESH_BASENAME="$(basename "${MESH_PATH%.*}")"
CROP_PROFILE="${CROP_PROFILE:-conservative}"
case "$CROP_PROFILE" in
    conservative)
        # Behaelt nicht ausreichend oft beobachtete Flaechen. Das ist fuer
        # eine verlustfreie Diagnose gedacht, nicht fuer einen engen Objekt-Crop.
        OUTPUT_SUFFIX="_multiview"
        ;;
    semantic-core)
        # Dense SuGaR meshes often project each triangle to only one pixel in a
        # video frame. This profile keeps faces supported in at least one
        # semantic observation and removes both rejected and unseen faces.
        OUTPUT_SUFFIX="_semantic_core"
        # Aufloesung des Raycasts relativ zum Trainingsbild. Hoeher erfasst
        # mehr kleine Dreiecke, benoetigt aber mehr Rechenzeit und Speicher.
        RENDER_SCALE="${RENDER_SCALE:-0.5}"
        # Ein Pixel in einer sichtbaren Kamera genuegt als Beobachtung.
        MIN_VISIBLE_VIEWS="${MIN_VISIBLE_VIEWS:-1}"
        # Ein einzelner getroffener Pixel pro Dreieck zaehlt als Sichtbarkeit.
        MIN_VISIBLE_PIXELS="${MIN_VISIBLE_PIXELS:-1}"
        # Mindestens die Haelfte dieser Pixel muss innerhalb der Maske liegen.
        MIN_VIEW_MASK_FRACTION="${MIN_VIEW_MASK_FRACTION:-0.5}"
        # Mindestens die Haelfte der sichtbaren Kameras muss das Dreieck
        # semantisch unterstuetzen.
        MIN_SUPPORT_RATIO="${MIN_SUPPORT_RATIO:-0.5}"
        ;;
    *)
        echo "Error: CROP_PROFILE must be conservative or semantic-core." >&2
        exit 2
        ;;
esac

# Maskenstufe: default ist die vollstaendige SAM-Objektmaske; middle und small
# sind zunehmend konservativere Kerne derselben Segmentierung.
MASK_LEVEL="${MASK_LEVEL:-default}"
MASKS_CONTAINER_DIR="${MASKS_CONTAINER_DIR:-/data/03_masks}"
# 0 = keine Dilatation. Nur Pixel der originalen SAM-Maske sind Objektpixel.
# Ein positiver Wert erweitert die Maske und kann Hintergrund an der Kontur
# ungewollt in den Crop uebernehmen.
MASK_DILATION_PX="${MASK_DILATION_PX:-0}"
# Relative Raycast-Aufloesung. 0.25 ist schnell, 0.5 trifft deutlich mehr
# kleine Dreiecke und ist fuer dichte Meshes sinnvoll.
RENDER_SCALE="${RENDER_SCALE:-0.25}"
# Anzahl verlaesslicher Kameras, bevor eine Flaeche bewertet wird. Hohe Werte
# behalten im konservativen Modus mehr unterbeobachtete Flaechen.
MIN_VISIBLE_VIEWS="${MIN_VISIBLE_VIEWS:-3}"
# Mindestzahl getroffener Raycast-Pixel je Dreieck und Kamera.
MIN_VISIBLE_PIXELS="${MIN_VISIBLE_PIXELS:-2}"
# Mindestanteil dieser Pixel innerhalb der Maske fuer eine positive
# Kamerastimme. Hoehere Werte beschneiden staerker an der Kontur.
MIN_VIEW_MASK_FRACTION="${MIN_VIEW_MASK_FRACTION:-0.5}"
# Mindestanteil positiver Kamerastimmen unter allen sichtbaren Stimmen.
# Hoehere Werte entfernen Flaechen ausserhalb des Objekts aggressiver.
MIN_SUPPORT_RATIO="${MIN_SUPPORT_RATIO:-0.6}"

OUTPUT_PATH="${OUTPUT_PATH:-data/06_mesh/${MESH_BASENAME}${OUTPUT_SUFFIX}.obj}"
case "$OUTPUT_PATH" in
    data/*)
        OUTPUT_CONTAINER_PATH="/$OUTPUT_PATH"
        ;;
    "$PROJECT_ROOT"/data/*)
        OUTPUT_CONTAINER_PATH="/data/${OUTPUT_PATH#"$PROJECT_ROOT"/data/}"
        ;;
    *)
        echo "Error: OUTPUT_PATH must be below this project's data/ directory." >&2
        exit 2
        ;;
esac

mkdir -p "$(dirname "$OUTPUT_PATH")"

EXTRA_ARGS=("$@")
if [[ "$CROP_PROFILE" == "semantic-core" ]]; then
    EXTRA_ARGS+=(--remove-underobserved)
fi
if [[ "${OVERWRITE:-0}" == "1" ]]; then
    EXTRA_ARGS+=(--overwrite)
fi
if [[ "${DRY_RUN:-0}" == "1" ]]; then
    EXTRA_ARGS+=(--dry-run)
fi

echo "=== Multi-view semantic mesh crop ==="
echo "Input : $MESH_PATH"
echo "Output: $OUTPUT_PATH"
echo "Profile: $CROP_PROFILE; mask level: $MASK_LEVEL; render scale: $RENDER_SCALE; mask dilation: ${MASK_DILATION_PX}px"
if [[ "$CROP_PROFILE" == "conservative" ]]; then
    echo "A first pass is conservative. Use CROP_PROFILE=semantic-core for dense full-scene meshes."
else
    echo "Semantic-core mode removes unseen faces; inspect the resulting object mesh before downstream use."
fi

docker compose run --rm --no-deps sugar-meshing \
    python3 /app/src/python/crop_mesh_multiview.py \
    --input-mesh "$MESH_CONTAINER_PATH" \
    --output-mesh "$OUTPUT_CONTAINER_PATH" \
    --cameras-json /data/05_3dgs/output/cameras.json \
    --masks-dir "$MASKS_CONTAINER_DIR" \
    --mask-level "$MASK_LEVEL" \
    --mask-dilation-px "$MASK_DILATION_PX" \
    --render-scale "$RENDER_SCALE" \
    --min-visible-views "$MIN_VISIBLE_VIEWS" \
    --min-visible-pixels "$MIN_VISIBLE_PIXELS" \
    --min-view-mask-fraction "$MIN_VIEW_MASK_FRACTION" \
    --min-support-ratio "$MIN_SUPPORT_RATIO" \
    "${EXTRA_ARGS[@]}"
