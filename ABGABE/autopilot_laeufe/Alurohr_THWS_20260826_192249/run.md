# Scan-to-BIM Lauf

- **Run-ID:** `Alurohr_THWS_20260826_192249`
- **Input:** `data/01_raw/Alurohr_THWS.mp4`
- **Start Lauf:** `2026-08-26T19:22:49+0200`
- **Host UID/GID:** `190290584/190200513`
- **Git Commit:** `f794dcd`
- **SuGaR Commit:** `a0fc37b`
- **Logdatei:** `data/10_runs/Alurohr_THWS_20260826_192249/run.log`

## Einstellungen

- **AUTOPILOT:** `false`
- **RUN_RESOLUTION:** `720p`
- **FRAME_PROFILE_SCOPE:** `all`
- **SELECTED_VIDEO:** `data/01_raw/output.mp4`
- **TEXT_PROMPT:** `pipe`
- **SAM3_FRAME_MAX_SIDE:** `1280`
- **SAM3_FRAME_STEP:** `(nicht gesetzt)`
- **COLMAP_CAMERA_MODEL:** `OPENCV`
- **COLMAP_MAX_FEATURES:** `4096`
- **COLMAP_SEQUENTIAL_OVERLAP:** `25`
- **COLMAP_GUIDED_MATCHING:** `0`
- **COLMAP_SIFT_PEAK_THRESHOLD:** `0.003`
- **ITERATIONS:** `(nicht gesetzt)`
- **STAGE2_ITERS:** `(nicht gesetzt)`
- **ON_THE_FLY:** `(nicht gesetzt)`
- **FILTER_MIN_OPACITY:** `(nicht gesetzt)`
- **FILTER_BLACK_THRESHOLD:** `(nicht gesetzt)`
- **SUGAR_INPUT_ALPHA:** `(nicht gesetzt)`
- **SUGAR_MESH_MODE:** `(nicht gesetzt)`
- **REGULARIZATION:** `(nicht gesetzt)`
- **COARSE_ITERATIONS:** `(nicht gesetzt)`
- **MESH_VERTICES:** `(nicht gesetzt)`
- **SURFACE_SAMPLE_COUNT:** `(nicht gesetzt)`
- **SURFACE_LEVEL:** `(nicht gesetzt)`
- **POISSON_DEPTH:** `(nicht gesetzt)`
- **VERTICES_DENSITY_QUANTILE:** `(nicht gesetzt)`
- **PROJECT_MESH_ON_SURFACE_POINTS:** `(nicht gesetzt)`
- **LOW_OPACITY_GAUSSIAN_THRESHOLD:** `(nicht gesetzt)`
- **SURFACE_SAMPLE_SEED:** `(nicht gesetzt)`
- **INCLUDE_BACKGROUND_MESH:** `(nicht gesetzt)`
- **USE_GAUSSIAN_DEPTH:** `(nicht gesetzt)`
- **REFINEMENT_TIME:** `(nicht gesetzt)`
- **MASK_LEVEL:** `(nicht gesetzt)`
- **MASK_DILATION_PX:** `(nicht gesetzt)`
- **NORMAL_MASK_LEVEL:** `(nicht gesetzt)`
- **TEXTURE_MASK_LEVEL:** `(nicht gesetzt)`
- **TEXTURE_MASK_DILATION_PX:** `(nicht gesetzt)`
- **STOP_AFTER_COARSE_MESH:** `(nicht gesetzt)`
- **RUN_CONSENSUS_CROP:** `(nicht gesetzt)`
- **SUGAR_RUN_TAG:** `(nicht gesetzt)`
- **SUGAR_MESH_EXPORT_NAME:** `(nicht gesetzt)`
- **STS_IMAGES_DIR:** `/data/04_sfm/undistorted/images`
- **STS_SFM_DIR:** `/data/04_sfm/undistorted`
- **STS_MASKS_DIR:** `/data/03_masks_ideal`
- **MASK_MAX_EMPTY_FRACTION:** `0.30`
- **EVAL_FRAMES_PATH:** `(nicht gesetzt)`
- **SUGAR_EVAL_FRAMES_PATH:** `(nicht gesetzt)`
- **MATRIX_BATCH_ID:** `(nicht gesetzt)`
- **MATRIX_RESOLUTION_ID:** `(nicht gesetzt)`
- **MATRIX_VARIANT:** `(nicht gesetzt)`
- **CENTERLINE_MODE:** `single`
- **VOXEL_SIZE:** `0.1`
- **MIN_PATH_LENGTH:** `0.75`
- **BSPLINE_DEGREE:** `10`
- **BSPLINE_SAMPLES_PER_SEGMENT:** `4`
- **SEGMENT_CORNERS:** `0`
- **GEOJSON_SRS:** `EPSG:25832`
- **FALLBACK_ANCHOR:** `567028.563,5516784.082,177`

## Schritte

| Schritt | Start | Ende | Dauer (s) | Status |
|---|---|---|---:|---|
| GCP-Vorbereitung | 2026-08-26T19:22:51+0200 | 2026-08-26T19:22:55+0200 | 4 | OK |
| HuggingFace-Authentifizierung | 2026-08-26T19:22:55+0200 | 2026-08-26T19:22:56+0200 | 1 | OK |
| Video-Preprocessing | 2026-08-26T19:24:06+0200 | 2026-08-26T19:24:09+0200 | 3 | OK |
| SAM3-Maskenextraktion | 2026-08-26T19:25:32+0200 | 2026-08-26T19:26:45+0200 | 73 | OK |
| COLMAP-SfM | 2026-08-26T19:26:45+0200 | 2026-08-26T19:33:14+0200 | 389 | OK |
| Masken-Warp in die ideale Bilddomaene | 2026-08-26T19:33:14+0200 | 2026-08-26T19:33:24+0200 | 10 | OK |
| GCP-Picking / CloudCompare | 2026-08-26T19:33:24+0200 | 2026-08-26T19:43:47+0200 | 623 | OK |

## Abschluss

- **Ende Lauf:** `2026-08-26T19:43:47+0200`
- **Status:** `FAILED (exit 2)`
- **Exit-Code:** `2`
