#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$PROJECT_ROOT/data"
NEW_VIDEO_MODE=0
MATRIX_RESET_MODE=0

print_usage() {
  cat <<'EOF'
Usage: ./clean_data_interactive.sh [--new-video] [--matrix-reset] [--help]

Options:
  --new-video   Presets defaults for a new input video (rebuild 02..09 and delete 01_raw/output.mp4).
  --matrix-reset  Non-interactively clear generated 02..09/sugar_output data;
                   preserves 01_raw, 01_raw/output.mp4, hf_cache and 10_runs.
  --help        Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --new-video)
      NEW_VIDEO_MODE=1
      shift
      ;;
    --matrix-reset)
      MATRIX_RESET_MODE=1
      shift
      ;;
    --help|-h)
      print_usage
      exit 0
      ;;
    *)
      echo "Unbekanntes Argument: $1"
      print_usage
      exit 1
      ;;
  esac
done

if [[ ! -d "$DATA_DIR" ]]; then
  echo "Fehler: data-Ordner nicht gefunden unter: $DATA_DIR"
  exit 1
fi

cleanup_target() {
  local path="$1"
  if [[ -d "$path" ]]; then
    find "$path" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  elif [[ -f "$path" ]]; then
    rm -f "$path"
  fi
}

if [[ "$MATRIX_RESET_MODE" -eq 1 ]]; then
  echo "=== Nichtinteraktiver Matrix-Cleanup ==="
  echo "Loesche nur generierte Live-Daten; 01_raw, GCP-Dateien, .gitkeep, output.mp4, hf_cache und 10_runs bleiben erhalten."
  for protected in \
    "$DATA_DIR/01_raw/gcp_coordinates.csv" \
    "$DATA_DIR/01_raw/gcp_relative.csv" \
    "$DATA_DIR/01_raw/.gitkeep"; do
    if [[ ! -e "$protected" ]]; then
      echo "Warnung: geschuetzte Raw-Datei fehlt und wird nicht erzeugt: $protected" >&2
    fi
  done
  for target in \
    "$DATA_DIR/02_frames" "$DATA_DIR/03_masks" "$DATA_DIR/03_masks_ideal" "$DATA_DIR/04_sfm" \
    "$DATA_DIR/05_3dgs" "$DATA_DIR/06_mesh" "$DATA_DIR/07_centerline" \
    "$DATA_DIR/08_gis" "$DATA_DIR/09_evaluation" "$DATA_DIR/sugar_output"; do
    cleanup_target "$target"
  done
  mkdir -p "$DATA_DIR/02_frames" "$DATA_DIR/03_masks" "$DATA_DIR/03_masks_ideal" "$DATA_DIR/04_sfm" \
    "$DATA_DIR/05_3dgs" "$DATA_DIR/06_mesh" "$DATA_DIR/07_centerline" \
    "$DATA_DIR/08_gis" "$DATA_DIR/09_evaluation" "$DATA_DIR/sugar_output"
  echo "Matrix-Cleanup abgeschlossen."
  exit 0
fi

SELECTED_PATHS=()

add_if_selected() {
  local answer="$1"
  shift
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    for p in "$@"; do
      SELECTED_PATHS+=("$p")
    done
  fi
}

ask_delete() {
  local label="$1"
  local reason="$2"
  local default_answer="$3"
  local var_name="$4"

  echo
  echo "--- $label ---"
  echo "$reason"
  if [[ "$default_answer" == "y" ]]; then
    read -r -p "Loeschen? (y/n) [Default: y]: " response
    response="${response:-y}"
  else
    read -r -p "Loeschen? (y/n) [Default: n]: " response
    response="${response:-n}"
  fi
  printf -v "$var_name" '%s' "$response"
}

default_answer() {
  local normal_default="$1"
  local new_video_default="$2"
  if [[ "$NEW_VIDEO_MODE" -eq 1 ]]; then
    echo "$new_video_default"
  else
    echo "$normal_default"
  fi
}

print_plan() {
  echo
  echo "================ Geplanter Cleanup ================"
  if [[ ${#SELECTED_PATHS[@]} -eq 0 ]]; then
    echo "Es wurde nichts zum Loeschen ausgewaehlt."
    return
  fi

  local total_bytes=0
  for p in "${SELECTED_PATHS[@]}"; do
    if [[ -e "$p" ]]; then
      local size_bytes
      size_bytes=$(du -sb "$p" 2>/dev/null | awk '{print $1}')
      size_bytes=${size_bytes:-0}
      total_bytes=$((total_bytes + size_bytes))
      local rel
      rel=$(realpath --relative-to "$PROJECT_ROOT" "$p")
      local human
      human=$(du -sh "$p" 2>/dev/null | awk '{print $1}')
      human=${human:-"?"}
      echo "- $rel (aktuell: $human)"
    else
      local rel_missing
      rel_missing=$(realpath --relative-to "$PROJECT_ROOT" "$(dirname "$p")")/$(basename "$p")
      echo "- $rel_missing (nicht vorhanden, wird uebersprungen)"
    fi
  done

  echo "---------------------------------------------------"
  echo "Gesamtsumme (ungefaehr): $(numfmt --to=iec --suffix=B "$total_bytes" 2>/dev/null || echo "$total_bytes bytes")"
}

echo "=== Interaktiver Pipeline-Cleanup ==="
echo "Dieses Skript loescht nur abgeleitete Daten unter data/."
echo "Der Ordner data/01_raw bleibt standardmaessig erhalten."
echo

if [[ "$NEW_VIDEO_MODE" -eq 1 ]]; then
  echo "Modus aktiv: --new-video"
  echo "Default-Auswahl wird auf kompletten Neuaufbau fuer ein neues Video gesetzt."
  echo
fi

echo "Hinweis fuer neues Video:"
echo "- Fast immer sinnvoll: 02_frames bis 09_evaluation neu aufbauen"
echo "- Optional behalten: data/hf_cache"
echo

ask_delete \
  "SAM3-Ausgabe zuruecksetzen" \
  "Sinnvoll bei neuem Prompt, neuer Maskenlogik oder neuem Video. Betrifft Frames und Masken." \
  "$(default_answer y y)" \
  "DELETE_SAM3"
add_if_selected "$DELETE_SAM3" "$DATA_DIR/02_frames" "$DATA_DIR/03_masks" "$DATA_DIR/03_masks_ideal"

ask_delete \
  "COLMAP-Ergebnisse zuruecksetzen" \
  "Sinnvoll bei neuem Video oder wenn SfM fehlerhaft/instabil war. Betrifft sparse/dense Rekonstruktion in data/04_sfm." \
  "$(default_answer y y)" \
  "DELETE_COLMAP"
add_if_selected "$DELETE_COLMAP" "$DATA_DIR/04_sfm"

ask_delete \
  "STS/3DGS-Ergebnisse zuruecksetzen" \
  "Sinnvoll bei neuen Masken, anderer Iterationszahl oder neuem COLMAP-Stand. Betrifft data/05_3dgs." \
  "$(default_answer y y)" \
  "DELETE_STS"
add_if_selected "$DELETE_STS" "$DATA_DIR/05_3dgs"

ask_delete \
  "Meshing/Postprocess/Evaluation zuruecksetzen" \
  "Sinnvoll wenn du ab Mesh-Schritt oder Postprocess komplett neu rechnen willst. Betrifft 06, 07, 08, 09 und sugar_output (Coarse/Refined/PLY-Artefakte)." \
  "$(default_answer y y)" \
  "DELETE_LATE"
add_if_selected "$DELETE_LATE" "$DATA_DIR/06_mesh" "$DATA_DIR/07_centerline" "$DATA_DIR/08_gis" "$DATA_DIR/09_evaluation" "$DATA_DIR/sugar_output"

ask_delete \
  "Komprimiertes Arbeitsvideo output.mp4 loeschen" \
  "Sinnvoll wenn alte Komprimierung falsche Orientierung/Parameter hatte. Rohvideo in 01_raw bleibt erhalten." \
  "$(default_answer y y)" \
  "DELETE_COMPRESSED"
add_if_selected "$DELETE_COMPRESSED" "$DATA_DIR/01_raw/output.mp4"

ask_delete \
  "HF Cache loeschen" \
  "Nur loeschen wenn Speicher knapp ist. Sonst behalten, damit Modell-Downloads nicht erneut laufen." \
  "$(default_answer n n)" \
  "DELETE_CACHE"
add_if_selected "$DELETE_CACHE" "$DATA_DIR/hf_cache"

print_plan

if [[ ${#SELECTED_PATHS[@]} -eq 0 ]]; then
  echo
  echo "Nichts ausgewaehlt. Keine Aenderungen vorgenommen."
  exit 0
fi

echo
echo "Sicherheitsabfrage:"
echo "- Loescht nur Inhalte der ausgewaehlten Ordner (Ordnerstruktur bleibt bestehen)."
echo "- Einzeldateien wie output.mp4 werden direkt geloescht."
read -r -p "Zum Fortfahren bitte DELETE eingeben: " CONFIRM

if [[ "$CONFIRM" != "DELETE" ]]; then
  echo "Abgebrochen. Keine Daten geloescht."
  exit 0
fi

echo
echo "Loesche ausgewaehlte Daten..."
for p in "${SELECTED_PATHS[@]}"; do
  cleanup_target "$p"
done

echo "Cleanup abgeschlossen."
