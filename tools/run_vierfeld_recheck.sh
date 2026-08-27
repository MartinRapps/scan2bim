#!/usr/bin/env bash
# Vierfeld-Ablation-Recheck aus archivierten Checkpoints (kein Training).
#
# Hintergrund: Die Original-A/B/C/D-Meshes der Vierfeld-Ablation (Tabelle
# tab:mesh-ablation in der PA) lagen in einem zwischenzeitlich komprimierten
# Batch. Dieser Recheck extrahiert alle vier Zellen erneut aus den archivierten
# Checkpoints und schreibt Vertices-/Face-Zahlen plus Distanzkennzahlen in eine
# CSV. Erwartungsgemass weichen die absoluten Zahlen vom Historienlauf ab (anderer
# Checkpoint-Stand); die PA-Tabelle wird mit den neuen Werten aktualisiert.
#
# Quellen:
#   A/B: data/10_runs/matrix_e2e_verifikation_260826/5fps/720p/opencv_a/live
#        -> STS-Checkpoint (point_cloud_filtered_opacity999999.ply)
#   C/D: data/10_runs/matrix_qualitaetsvergleich_20260818/5fps/720p/opencv_sugar
#        /live/sugar_output -> SuGaR-Coarse-Checkpoint (c=9000)
#
# Verwendung:  bash tools/run_vierfeld_recheck.sh
# Ergebnis:    data/09_evaluation/vierfeld_recheck/vierfeld_recheck.csv

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export HOST_UID="${HOST_UID:-$(id -u)}"
export HOST_GID="${HOST_GID:-$(id -g)}"

OUT_ROOT="data/09_evaluation/vierfeld_recheck"
mkdir -p "$OUT_ROOT"

declare -A SOURCE_TAG=(
    [A]=vierfeld_recheck_a
    [B]=vierfeld_recheck_b
    [C]=vierfeld_recheck_c
    [D]=vierfeld_recheck_d
)

stage_ab() {
    local src="data/10_runs/matrix_e2e_verifikation_260826/5fps/720p/opencv_a/live"
    local tag="$1"
    rm -rf "data/05_3dgs/masked_sugar_input/${tag}"
    mkdir -p "data/05_3dgs/masked_sugar_input/${tag}/point_cloud/iteration_7000"
    cp "$src/sts/output/point_cloud/iteration_7000/point_cloud_filtered_opacity999999.ply" \
       "data/05_3dgs/masked_sugar_input/${tag}/point_cloud/iteration_7000/point_cloud.ply"
    mkdir -p "data/sugar_output/${tag}"
}

stage_cd() {
    local src="data/10_runs/matrix_qualitaetsvergleich_20260818/5fps/720p/opencv_sugar/live/sugar_output"
    local tag="$1"
    local coarse_pt
    coarse_pt="$(find "$src" -path "*coarse/05_3dgs*" -name "*.pt" | sort | head -n 1)"
    if [[ -z "$coarse_pt" ]]; then
        echo "FEHLER: Kein SuGaR-Coarse-Checkpoint (*.pt) unter $src gefunden." >&2
        exit 1
    fi
    rm -rf "data/sugar_output/${tag}"
    mkdir -p "data/sugar_output/${tag}/coarse"
    cp "$coarse_pt" "data/sugar_output/${tag}/coarse/coarse_model.pt"
}

run_cell() {
    local cell="$1" og="$2" gdepth="$3"
    echo "=== Zelle $cell (USE_ORIGINAL_GS=$og, USE_GAUSSIAN_DEPTH=$gdepth) ==="
    ITERATIONS=7000 \
    SOURCE_RUN_TAG="${SOURCE_TAG[$cell]}" \
    COARSE_MESH_ABLATION_TAG="recheck_${cell}" \
    MESH_VERTICES=200000 \
    SURFACE_SAMPLE_COUNT=5000000 \
    SURFACE_SAMPLE_SEED=42 \
    SURFACE_LEVEL=0.3 \
    POISSON_DEPTH=10 \
    VERTICES_DENSITY_QUANTILE=0.1 \
    USE_ORIGINAL_GS="$og" \
    USE_GAUSSIAN_DEPTH="$gdepth" \
    INCLUDE_BACKGROUND_MESH=True \
    COARSE_MESH_ABLATION_INTERACTIVE=0 \
    bash tools/run_coarse_mesh_ablation.sh
}

count_mesh() {
    python3 - "$1" <<'PY'
import sys
try:
    import open3d as o3d
    mesh = o3d.io.read_triangle_mesh(sys.argv[1])
    print(f"{len(mesh.vertices)},{len(mesh.triangles)}")
except ImportError:
    # Fallback: PLY-Kopf auslesen
    with open(sys.argv[1], "rb") as fh:
        head = fh.read(4096).decode("ascii", "ignore")
    v = f = 0
    for line in head.splitlines():
        if line.startswith("element vertex"): v = int(line.split()[-1])
        if line.startswith("element face"): f = int(line.split()[-1])
    print(f"{v},{f}")
PY
}

stage_ab "${SOURCE_TAG[A]}"; run_cell A True False
stage_ab "${SOURCE_TAG[B]}"; run_cell B True True
stage_cd "${SOURCE_TAG[C]}"; run_cell C False False
stage_cd "${SOURCE_TAG[D]}"; run_cell D False True

CSV="$OUT_ROOT/vierfeld_recheck.csv"
echo "zelle,vertices,faces,mesh_path" > "$CSV"
for cell in A B C D; do
    mesh="$(find "data/sugar_output/${SOURCE_TAG[$cell]}/coarse_mesh_ablation/recheck_${cell}" -name "*.ply" | head -n 1)"
    counts="$(count_mesh "$mesh")"
    echo "${cell},${counts},${mesh}" >> "$CSV"
done

echo ""
echo "Fertig. Ergebnis: $CSV"
cat "$CSV"
echo ""
echo "Naechster Schritt: gerichtete Distanzmittelwerte (20000 Samples, wie in der"
echo "PA beschrieben) berechnen und die PA-Tabelle tab:mesh-ablation mit den"
echo "neuen Vertices-/Face-Zahlen aktualisieren."
