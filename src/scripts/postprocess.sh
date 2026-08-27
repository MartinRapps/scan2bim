#!/bin/bash
set -euo pipefail

echo "=== Post-Processing and Georeferencing ==="

if [[ -z "${INPUT_MESH:-}" ]]; then
	INPUT_MESH=$(find /data/06_mesh -type f -name refined.obj -print -quit 2>/dev/null || true)
fi
OUTPUT_LOCAL="${OUTPUT_LOCAL:-/data/07_centerline/centerline_local.csv}"
OUTPUT_RAW="${OUTPUT_RAW:-/data/07_centerline/centerline_local_raw.csv}"
OUTPUT_UTM="${OUTPUT_UTM:-/data/07_centerline/centerline_utm.csv}"
OUTPUT_GIS="${OUTPUT_GIS:-/data/08_gis/final_output.geojson}"
MATRIX_PATH="${MATRIX_PATH:-/data/04_sfm/matrix.txt}"
ANCHOR_PATH="${ANCHOR_PATH:-/data/01_raw/anchor.txt}"
GEOJSON_SRS="${GEOJSON_SRS:-EPSG:25832}"
MAX_GRID_SIZE="${MAX_GRID_SIZE:-128}"
VOXEL_SIZE="${VOXEL_SIZE:-0.1}"
AUTO_VOXEL_FALLBACK="${AUTO_VOXEL_FALLBACK:-0}"
CENTERLINE_MODE="${CENTERLINE_MODE:-single}"
PERSISTENCE="${PERSISTENCE:-0}"
MIN_COMPONENT_VOXELS="${MIN_COMPONENT_VOXELS:-4}"
MIN_PATH_POINTS="${MIN_PATH_POINTS:-2}"
MIN_PATH_LENGTH="${MIN_PATH_LENGTH:-0.75}"
MIN_CYCLE_LENGTH="${MIN_CYCLE_LENGTH:-8}"
BSPLINE_SAMPLES_PER_SEGMENT="${BSPLINE_SAMPLES_PER_SEGMENT:-4}"
BSPLINE_DEGREE="${BSPLINE_DEGREE:-20}"
SEGMENT_CORNERS="${SEGMENT_CORNERS:-0}"
SEGMENT_CORNER_WINDOW="${SEGMENT_CORNER_WINDOW:-4}"
SEGMENT_CORNER_ANGLE="${SEGMENT_CORNER_ANGLE:-30}"
EXTRACTOR="${EXTRACTOR:-/usr/local/bin/extractor}"
SCREENSHOT_PATH="${SCREENSHOT_PATH:-/data/01_raw/matrix_screenshot.png}"
FALLBACK_ANCHOR="${FALLBACK_ANCHOR:-567028.563,5516784.082,177}"
OUTPUT_GIS_LOCAL="${OUTPUT_GIS_LOCAL:-/data/08_gis/local_output.geojson}"
OUTPUT_UTM_FALLBACK="${OUTPUT_UTM_FALLBACK:-/data/07_centerline/centerline_fallback_georeferenced.csv}"
OUTPUT_GIS_FALLBACK="${OUTPUT_GIS_FALLBACK:-/data/08_gis/final_output_fallback_georeferenced.geojson}"

mkdir -p /data/07_centerline /data/08_gis
rm -f "$OUTPUT_RAW" "$OUTPUT_LOCAL" "$OUTPUT_UTM" "$OUTPUT_GIS" \
	"$OUTPUT_GIS_LOCAL" "$OUTPUT_UTM_FALLBACK" "$OUTPUT_GIS_FALLBACK" \
	/data/07_centerline/centerline.txt

if [[ -z "$INPUT_MESH" || ! -s "$INPUT_MESH" ]]; then
	echo "Error: no non-empty refined OBJ mesh found. Set INPUT_MESH explicitly." >&2
	exit 1
fi

if [[ ! -x "$EXTRACTOR" ]]; then
	BUILD_DIR="${BUILD_DIR:-/tmp/centerline-build}"
	cmake -S /app/src/cpp -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
	cmake --build "$BUILD_DIR" --parallel "$(nproc)"
	EXTRACTOR="$BUILD_DIR/extractor"
fi

echo "1. Running DGtal centerline extraction..."
echo "Using mesh: $INPUT_MESH"
RAW_TMP=""
LOCAL_TMP=""
UTM_TMP=""
GEOJSON_TMP=""
GEOJSON_LOCAL_TMP=""
IDENTITY_TMP=""
ANCHOR_TMP=""
RAW_TMP=$(mktemp /data/07_centerline/centerline_local_raw.csv.XXXXXX)
trap 'rm -f "$RAW_TMP" "$LOCAL_TMP" "$UTM_TMP" "$GEOJSON_TMP" "$GEOJSON_LOCAL_TMP" "$IDENTITY_TMP" "$ANCHOR_TMP"' EXIT
USED_VOXEL_SIZE="$VOXEL_SIZE"
EXTRACTOR_ERR=$(mktemp /tmp/centerline-extractor.err.XXXXXX)
run_extractor() {
	local voxel="$1"
	"$EXTRACTOR" "$INPUT_MESH" "$RAW_TMP" \
		--mode "$CENTERLINE_MODE" \
		--voxel-size "$voxel" \
		--max-grid-size "$MAX_GRID_SIZE" \
		--persistence "$PERSISTENCE" \
		--min-component-voxels "$MIN_COMPONENT_VOXELS" \
		--min-path-points "$MIN_PATH_POINTS" \
		--min-path-length "$MIN_PATH_LENGTH" \
		--min-cycle-length "$MIN_CYCLE_LENGTH" \
		2>"$EXTRACTOR_ERR"
}

if ! run_extractor "$VOXEL_SIZE"; then
	if [[ "$AUTO_VOXEL_FALLBACK" == "1" ]] &&
		grep -q "centerline network contains no valid paths" "$EXTRACTOR_ERR"; then
		echo "Warning: no valid centerline paths for VOXEL_SIZE=$VOXEL_SIZE, trying fallback voxel sizes..." >&2
		for fallback_voxel in 0.12 0.15 0.2; do
			if [[ "$fallback_voxel" == "$VOXEL_SIZE" ]]; then
				continue
			fi
			echo "  Retrying extractor with VOXEL_SIZE=$fallback_voxel" >&2
			if run_extractor "$fallback_voxel"; then
				USED_VOXEL_SIZE="$fallback_voxel"
				break
			fi
		done
	fi
	if [[ $(wc -l < "$RAW_TMP") -lt 2 ]]; then
		echo "Error: extractor produced no centerline points:" >&2
		cat "$EXTRACTOR_ERR" >&2
		rm -f "$EXTRACTOR_ERR"
		exit 1
	fi
fi
rm -f "$EXTRACTOR_ERR"
echo "Extractor succeeded with VOXEL_SIZE=$USED_VOXEL_SIZE"
if [[ ! -s "$RAW_TMP" ]]; then
	echo "Error: DGtal extractor returned an empty centerline." >&2
	exit 1
fi
mv "$RAW_TMP" "$OUTPUT_RAW"
echo "Raw centerline network written to $OUTPUT_RAW"

echo "2. Fitting clamped uniform B-splines (degree $BSPLINE_DEGREE) to each branch..."
LOCAL_TMP=$(mktemp /data/07_centerline/centerline_local.csv.XXXXXX)
BSPLINE_ARGS=(
	--input_csv "$OUTPUT_RAW"
	--output_csv "$LOCAL_TMP"
	--samples-per-segment "$BSPLINE_SAMPLES_PER_SEGMENT"
	--degree "$BSPLINE_DEGREE"
)
if [[ "$SEGMENT_CORNERS" == "1" ]]; then
	BSPLINE_ARGS+=(
		--segment-corners
		--corner-window "$SEGMENT_CORNER_WINDOW"
		--corner-min-angle "$SEGMENT_CORNER_ANGLE"
	)
fi
python3 /app/src/python/centerline_bspline.py "${BSPLINE_ARGS[@]}"
if [[ ! -s "$LOCAL_TMP" ]]; then
	echo "Error: B-spline-smoothed centerline is empty." >&2
	exit 1
fi
mv "$LOCAL_TMP" "$OUTPUT_LOCAL"
echo "Local centerline written to $OUTPUT_LOCAL"

echo "3. Writing local 3D GeoJSON (pre-georeferencing)..."
GEOJSON_LOCAL_TMP=$(mktemp /data/08_gis/local_output.geojson.XXXXXX)
python3 /app/src/python/centerline_geojson.py \
	--input_csv "$OUTPUT_LOCAL" \
	--output_geojson "$GEOJSON_LOCAL_TMP" \
	--srs LOCAL
if [[ ! -s "$GEOJSON_LOCAL_TMP" ]]; then
	echo "Error: local GeoJSON output is empty." >&2
	exit 1
fi
mv "$GEOJSON_LOCAL_TMP" "$OUTPUT_GIS_LOCAL"
echo "Local GeoJSON written to $OUTPUT_GIS_LOCAL"

echo "4. Georeferencing (matrix + anchor, OCR fallback, or translation-only fallback)..."

# OCR fallback: if matrix.txt is missing but a screenshot exists and tesseract is available
if [[ ! -s "$MATRIX_PATH" ]] && [[ -f "$SCREENSHOT_PATH" ]] && command -v tesseract >/dev/null 2>&1; then
	echo "   matrix.txt missing, screenshot found -> running OCR (tesseract)..."
	if python3 /app/src/python/ocr_matrix.py "$SCREENSHOT_PATH" "$MATRIX_PATH"; then
		echo "   OCR completed, matrix.txt written."
	else
		echo "   OCR failed, will use translation-only fallback." >&2
	fi
fi

if [[ -s "$MATRIX_PATH" && -s "$ANCHOR_PATH" ]]; then
	echo "   matrix.txt + anchor.txt present -> full 4x4 georeferencing."
	UTM_TMP=$(mktemp /data/07_centerline/centerline_utm.csv.XXXXXX)
	python3 /app/src/python/transform_centerline.py \
		--input_csv "$OUTPUT_LOCAL" \
		--matrix "$MATRIX_PATH" \
		--anchor_txt "$ANCHOR_PATH" \
		--output_csv "$UTM_TMP"
	if [[ ! -s "$UTM_TMP" ]]; then
		echo "Error: transformed centerline is empty." >&2
		exit 1
	fi
	mv "$UTM_TMP" "$OUTPUT_UTM"
	GEOJSON_TMP=$(mktemp /data/08_gis/final_output.geojson.XXXXXX)
	python3 /app/src/python/centerline_geojson.py \
		--input_csv "$OUTPUT_UTM" \
		--output_geojson "$GEOJSON_TMP" \
		--srs "$GEOJSON_SRS"
	if [[ ! -s "$GEOJSON_TMP" ]]; then
		echo "Error: GeoJSON output is empty." >&2
		exit 1
	fi
	mv "$GEOJSON_TMP" "$OUTPUT_GIS"
	ogrinfo -ro -al -so "$OUTPUT_GIS" >/dev/null
	GEO_LABEL="georeferenced"
else
	echo "   matrix.txt or anchor.txt missing -> translation-only fallback to ($FALLBACK_ANCHOR)."
	IDENTITY_TMP=$(mktemp /tmp/identity_matrix.XXXXXX)
	ANCHOR_TMP=$(mktemp /tmp/fallback_anchor.XXXXXX)
	printf '1,0,0,0\n0,1,0,0\n0,0,1,0\n0,0,0,1\n' > "$IDENTITY_TMP"
	printf '%s\n' "$FALLBACK_ANCHOR" > "$ANCHOR_TMP"
	UTM_TMP=$(mktemp /data/07_centerline/centerline_fallback_georeferenced.csv.XXXXXX)
	python3 /app/src/python/transform_centerline.py \
		--input_csv "$OUTPUT_LOCAL" \
		--matrix "$IDENTITY_TMP" \
		--anchor_txt "$ANCHOR_TMP" \
		--output_csv "$UTM_TMP"
	if [[ ! -s "$UTM_TMP" ]]; then
		echo "Error: fallback centerline is empty." >&2
		exit 1
	fi
	mv "$UTM_TMP" "$OUTPUT_UTM_FALLBACK"
	GEOJSON_TMP=$(mktemp /data/08_gis/final_output_fallback_georeferenced.geojson.XXXXXX)
	python3 /app/src/python/centerline_geojson.py \
		--input_csv "$OUTPUT_UTM_FALLBACK" \
		--output_geojson "$GEOJSON_TMP" \
		--srs "$GEOJSON_SRS"
	if [[ ! -s "$GEOJSON_TMP" ]]; then
		echo "Error: fallback GeoJSON output is empty." >&2
		exit 1
	fi
	mv "$GEOJSON_TMP" "$OUTPUT_GIS_FALLBACK"
	ogrinfo -ro -al -so "$OUTPUT_GIS_FALLBACK" >/dev/null
	GEO_LABEL="fallback"
fi

echo "Post-Processing completed."
echo "  Local CSV:      $OUTPUT_LOCAL"
echo "  Local GeoJSON:  $OUTPUT_GIS_LOCAL"
if [[ "$GEO_LABEL" == "georeferenced" ]]; then
	echo "  UTM CSV:        $OUTPUT_UTM"
	echo "  GeoJSON:        $OUTPUT_GIS"
else
	echo "  Fallback CSV:   $OUTPUT_UTM_FALLBACK"
	echo "  Fallback GeoJSON: $OUTPUT_GIS_FALLBACK"
fi
