# Agent Memory (zusammengeführt)

# Agent Memory (Repo Export)

Source: /memories/repo/docker.md
Exported on: 2026-07-17

- Docker Compose uses `gpus: all` for GPU services; `deploy.resources` alone is not enough for normal `docker compose` runs.
- SAM 3.1 runtime expectations: Python 3.12, PyTorch 2.7+, CUDA 12.6+ (specifically nvidia/cuda:12.6.3-cudnn-devel-ubuntu24.04 in Container A) and Hugging Face checkpoint access.
- Scripts and entrypoints:
  - `run_sam3.sh` runs general/single-image fallback mode using SAM 3.1 (`extract_masks_notebook_flow.py` in `auto` mode).
  - `sam3_1_Video.sh` runs specifically in `video` mode (`--input-mode video`) for video frame extraction, interactive video segmentation, and dense tracking on MP4/MOV assets.

- Some installed SAM3 multiplex builds expose `offload_state_to_cpu` in `start_session`, but crash in `model.init_state`; fallback wrapper dropping that kwarg is required.
- If `flash_attn_interface` is missing in Container A, set `use_fa3=False` when building the multiplex predictor.
- Stable low-memory run settings observed: frame downscale via `SAM3_FRAME_MAX_SIDE` (e.g. 768) and smaller chunking via `SAM3_MAX_FRAMES_PER_CHUNK` (e.g. 6-8).

- Hugging Face CLI in the container uses `hf`; `huggingface-cli whoami` is deprecated and can produce false failure checks. Use `hf auth whoami` instead.

- **Main breakthrough (VRAM & Tracking format)**:
  1. Low-VRAM Video Propagation without Chunking/OOM: Setting `batched_grounding_batch_size = 1` and disabling PyTorch serialization compilation (`TORCH_COMPILE_DISABLE=1`) stabilizes GPU memory at <5GB for 100-frame tracking sequences.
  2. AssertionError Resolved: Reverted limiting `max_cond_frames_in_attn = 2` to default settings to bypass the `AssertionError` that occurred in SAM 3.1 multiplex conditioning shape assertions.
  3. Output Matcher: SAM 3.1 Multiplex returns prediction streams as `{"out_obj_ids": ..., "out_binary_masks": ..., ...}` instead of standard nested dictionaries. Parsing must explicitly query `out_binary_masks[idx]` to retrieve segmentation masks correctly.
- **Container B (COLMAP-SFM)**: Upgraded to use the official GPU-supported pre-built image `colmap/colmap:latest`. This avoids build/compilation failures inside the workspace (since the COLMAP C++ source code is not present) and dramatically speeds up build times from ~45 minutes to <4 minutes with robust out-of-the-box CUDA and EGL support, utilizing the host GPU natively without any performance bottleneck.
- **Container D (SuGaR-Meshing)**:
  - Base Image: `nvidia/cuda:11.8.0-devel-ubuntu22.04`
  - Needs `ninja-build` to compile CUDA extensions (`diff-gaussian-rasterization` and `simple-knn`) in python setuptools.
  - Requires environmental variables `FORCE_CUDA=1` and `TORCH_CUDA_ARCH_LIST="7.0;7.5;8.0;8.6;8.9;9.0"` to construct the kernels for current and target GPU architectures.
  - Leverage `--no-build-isolation` to reuse Conda pre-installed PyTorch & pre-configured CUDA runtime without spinning up separate build containers which lack CUDA access.
  - MKL>=2025 removes the `iJIT_NotifyEvent` symbol needed by PyTorch 2.0.1 -> pin `"mkl==2024.0.0"` alongside `numpy<2` in the conda install line, else `import torch` crashes with `undefined symbol: iJIT_NotifyEvent`.
  - `extract_mesh.py` has NO `--regularization` flag; that belongs to root-level `train.py` (`-s` scene_path, `-c` checkpoint_path, `-i` iteration_to_load, `-r` regularization_type, `--refinement_time`). `train.py` runs coarse training -> mesh extraction -> refinement all in one call.
  - docker-compose runs containers as `user: "${HOST_UID:-1000}:${HOST_GID:-1000}"` (non-root), but `/opt/sugar` is built as root -> `PermissionError` on runtime-created output dirs (e.g. `./output/coarse/...`). Fix: `RUN chmod -R 777 /opt/sugar` at the end of the Dockerfile.
- Pipeline scripts (`run_from_sts.sh`, `run_from_sugar.sh`) have an Autopilot-mode prompt at the top, plus an "EXPLAIN" keyword accepted at the SuGaR regularization-type/refinement-time prompts that prints plain-language explanations before re-asking the same question.
- **Web UI (`ui/server.py`, stdlib-only, no pip deps)**: PTY-based interactive script execution (`pty.openpty()` + `select`) so `read -p` prompts without newline stream live via SSE; `ThreadingMixIn` HTTP server (SSE would otherwise block all requests); `/api/upload` multipart endpoint with whitelisted targets (matrix_screenshot->01_raw, matrix_txt->04_sfm, raw_video/raw_image/gcp_csv->01_raw); processes started with `os.setsid` and killed via `os.killpg` so `docker compose run` children terminate too. Frontend has drag&drop upload zone + quick-answer buttons (y/n/EXPLAIN/Enter).
- **GCP Pre-Run Guard**: `run_pipeline.sh` has an integrated check at Schritt 0. It queries `gcp_coordinates.csv` and offers fallback reuse of existing `gcp_relative.csv`. If absent, it pauses in a loop instructing the user to upload coordinating passpoints via the drag&drop dashboard before allowing execution to continue. This prevents down-the-road photogrammetric crashes.
- LaTeX gotcha (`Themenfindung/Expose_PA_BA.tex`): pdflatex breaks on any literal `_` inside `\texttt{}` outside verbatim/math (e.g. `guided_matching`, `single_camera`, `use_gpu`) -> must escape as `\_`. Always recompile with `pdflatex -interaction=nonstopmode -halt-on-error Expose_PA_BA.tex` (from within `Themenfindung/`) after editing to catch these before considering the edit done.
- **SuGaR object-only workflow:** Stock SuGaR uses unmasked full RGB images for `l1+dssim`, so the full-scene `point_cloud.ply` remains the baseline and is never replaced. The standard geometry-first route uses `prepare_sugar_input.sh`: it writes the genuinely filtered `point_cloud_filtered.ply`, then writes `point_cloud_filtered_opacity999999.ply` with every retained opacity set to sigmoid alpha `0.999999` for mask-aware SuGaR initialization. `run_pipeline.sh`, `run_from_sts.sh`, `run_from_colmap.sh`, and `pipeline_lib.sh` all preserve the full-scene checkpoint and route object reconstruction through `run_masked_sugar.sh`, which stages a private checkpoint and enables masked RGB/DN/UV supervision. Historical `point_cloud_cable.ply` artifacts are retained but are no longer generated by the active scripts.
- **Local SuGaR development:** `third_party/SuGaR` is a pinned local submodule at upstream `7c10c4ae4a267dece512f5c7f40ed212a0a2ab44`; `docker-compose.sugar-dev.yml` overlays it at `/opt/sugar` without rebuilding or re-downloading. `run_masked_sugar.sh` automatically includes that overlay. The `sugar-meshing` container already includes Open3D and Pillow, so no extra container is needed for `src/python/crop_mesh_multiview.py`.
- **Multi-view cropper OBJ edge case:** SuGaR's textured OBJ can lack a terminal newline; Open3D/Assimp then silently omits its final face (960,731 instead of 960,732 for the 7000-step mesh). `crop_mesh_multiview.py` now creates a temporary newline-normalized OBJ only for geometry loading and always terminates output lines. This preserves the original input and aligns raycast face IDs with OBJ face records.
- **Crop profiles:** `run_multiview_crop.sh` defaults to `CROP_PROFILE=conservative`, which deliberately retains under-observed faces. For the dense 7000-step full-scene mesh use `CROP_PROFILE=semantic-core`; it runs at 0.5 scale with one-pixel/one-view semantic support and `--remove-underobserved`. The validated `*_semantic_core.obj` retains 6,277 of 960,732 faces and is compacted to 920 KB (texture remains a separate 22 MB PNG).
- Upstream SuGaR defaults relevant to quality: internal opacity pruning at 0.5, `poisson_depth=10`, and Poisson density cleanup `vertices_density_quantile=0.1`; the external STS filter's `min_opacity=0.01` is independent. `run_from_sugar.sh` is the correct full SuGaR rerun entrypoint; `run_sugar_only.sh` is obsolete because it calls `extract_mesh.py --regularization`.
- `run_masked_sugar.sh` now refuses a reused tag when either its output directory or private staged checkpoint exists. A fresh `SUGAR_RUN_TAG` keeps the full-scene checkpoint, filtered PLY, and prior runs untouched. It exposes `MESH_VERTICES` and optional `COARSE_ITERATIONS` for `dn_consistency`; the latter must exceed 9000 because depth-normal consistency and SDF terms begin only after iteration 9000.
- Use `run_coarse_mesh_ablation.sh` for fast diagnosis from an existing mask-aware coarse `.pt` checkpoint. It skips coarse optimization, refinement, UV baking, and crop; each output is isolated under `data/sugar_output/<source-tag>/coarse_mesh_ablation/<ablation-tag>`. It supports `MESH_VERTICES`, `SURFACE_LEVEL`, `POISSON_DEPTH`, `VERTICES_DENSITY_QUANTILE`, and `PROJECT_MESH_ON_SURFACE_POINTS`.

- **Current mask-aware SuGaR diagnostics (2026-07-16):** `SURFACE_SAMPLE_COUNT` is wired through `run_masked_sugar.sh`, `run_coarse_mesh_ablation.sh`, `train.py`, and `extract_mesh.py`; it controls the pre-Poisson camera-surface sampling target (10,000,000 reference). With `--eval=True`, the 699 registered views split into 611 training and 88 held-out eval views; actual valid samples can be lower. `STOP_AFTER_COARSE_MESH=1` on `run_masked_sugar.sh` exits after Coarse mesh extraction and skips refinement, UV baking, and crop, enabling a focused full-training RGB-dilation test.
- **Eval split nuance:** `GaussianSplattingWrapper` puts every camera with `i % 8 == 0` into the test list, giving 88 eval and 611 training images from 699. Coarse and refinement training receive `args.eval` (the runner passes `True`); `coarse_mesh.py` currently hardcodes the same split. Keep it unchanged for reference-comparable ablations; an all-view run is a separate experiment.
- **Verified SuGaR input/representation (2026-07-17):** The 7000-step full STS cloud contains 766,230 records; the middle object-ID file selects 38,196 records and the current standard filter (`min_opacity=0.01`, `black_threshold=0.08`) retains 6,175. `point_cloud_filtered.ply` preserves those original opacity values, while `point_cloud_filtered_opacity999999.ply` keeps the same records and stores the near-one initialization alpha. The mask-aware runner stages an SHA-256 byte-identical copy of the selected input as the private checkpoint's `point_cloud.ply`; `GaussianSplattingWrapper` loads exactly that path. With `gaussians_per_triangle=1`, refinement creates one mesh-bound Gaussian per coarse mesh face, so the refined PLY count is not a one-to-one continuation of the STS count.
- **Coarse iteration / opacity finding (2026-07-17):** Controlled `default + 0 px`, `middle` DN, 5M samples, 200k target series: c9001 checkpoint has 2,363 Gaussians, all alpha>0.5; c10000 has 2,368, all alpha>0.5; c18000 still has 2,368 internally but only 1,358 alpha>0.5. The hard coarse prune happens at iteration 9001 before rendering/loss; c9001 gets only one DN/SDF update. Extractor independently prunes with fixed alpha>0.5 before surface sampling, so c18000 discards 1,010 checkpoint Gaussians. Mesh counts are c9001 98,891V/190,988F, c10000 101,242V/192,670F, c18000 101,559V/195,771F; refined PLY count equals faces. Longer c18000 qualitatively improves temple continuity but stabilizes the same contact-region artifacts. `LOW_OPACITY_GAUSSIAN_THRESHOLD` is now wired from `run_coarse_mesh_ablation.sh` through `extract_mesh.py` into `coarse_mesh.py`; repeat the alpha>0 test using a new ablation tag because the older `opacity00` run was a no-op at the fixed 0.5 threshold.
- **Input-opacity distinction (2026-07-17):** `create_opacity_diagnostic_ply.py` overwrites every retained PLY opacity with a near-1 value. In the current project decision this is intentional geometry-first SuGaR initialization, not a physical opacity interpretation. Genuine object filtering still uses `filter_cable_pc.py --min_opacity` on the full STS PLY because an already filtered object PLY has no object-id field. The standard helper now writes `point_cloud_filtered.ply` plus `point_cloud_filtered_opacity999999.ply`; historical `point_cloud_cable_opacity*.ply` files remain useful comparison artifacts only.

---

# Agent Memory (Session-derived Project Knowledge)

Source: opencode session 2026-07-18 (centerline, B-spline, OCR, georeferencing, pipeline analysis)
Author: opencode assistant (glm-5.2)

## Projekt & Bachelorarbeit

- **Thema:** "KI-gestützte 3D-Rekonstruktion linearer Infrastruktur: Evaluierung einer Docker-basierten Scan-to-BIM Pipeline mittels SAM 3 und Gaussian Splatting" — Bachelor- und Projektarbeit an der THWS.
- **Ziel:** Drohnenvideo → SAM-3-Masken → COLMAP SfM → STS objektspezifisches 3DGS → SuGaR-Meshing → DGtal-Centerline → georeferenziertes GeoJSON (EPSG:25832) für GIS-Import (ArcGIS Pro). Toleranzrahmen ±10 cm.
- **Auftraggeber-Bezug:** TenneT (Kabeltrassen-Vermessung). Testdatensatz: `Alurohr_THWS.mp4` (Alurohr-Gestell im Labor), zusätzlich Sonnenbrillen-Experimente im Exposé.
- **Nutzer:** Martin (GitHub: MartinRapps). SuGaR auf eigenen Fork (`https://github.com/MartinRapps/SuGaR`) gepinnt mit maskenbewussten Modifikationen (Commit `48bbfdd "masked SuGaR updates"`).
- **Exposé:** `Themenfindung/Expose_PA_BA.tex` (754 Zeilen, article-Klasse, Deutsch). Kompiliert mit `pdflatex -interaction=nonstopmode -halt-on-error`. Hat `[GELÖST: ...]`- und `[NEUE ERKENNTNIS: ...]`-Einträge im Risikomanagement-Abschnitt für gelöste Probleme. LaTeX-Gotcha: `_` in `\texttt{}` muss als `\_` escaped werden.

## Container-Architektur (Stand 07/2026)

| Container | Base Image | Zweck | GPU |
|---|---|---|---|
| A (sam3-preprocess) | `nvidia/cuda:12.6.3-cudnn-devel-ubuntu24.04` | SAM-3-Masken, ffmpeg, GCP-Prep, STS-Scene-Prep, OCR (früher) | ja |
| B (colmap-sfm) | `colmap/colmap:latest` (fuer die PA bewusst ungepinnt) | COLMAP SfM | ja |
| C (sts-training) | `pytorch/pytorch:2.3.1-cuda12.1-cudnn8-devel` | STS 3DGS-Training, PLY-Filtering | ja |
| D (sugar-meshing) | `nvidia/cuda:11.8.0-devel-ubuntu22.04` + Miniconda | SuGaR Meshing (CUDA 11.8, PyTorch 2.0.1, pytorch3d 0.7.4) | ja |
| E (post-processing) | `ubuntu:22.04` | DGtal-Centerline, GDAL, tesseract OCR, B-Spline | nein |

- Alle Container mounten `./data:/data` und `./src:/app/src` (außer E, das `src/cpp` für den Build reinkopiert). Container D zusätzlich `./data/sugar_output:/opt/sugar/output`.
- `docker-compose.yml` nutzt sowohl `gpus: all` (legacy) als auch `deploy.resources.reservations.devices` (redundant).
- `docker-compose.sugar-dev.yml` mountet `./third_party/SuGaR:/opt/sugar` und wird von `run_masked_sugar.sh` **immer** mit `-f` geladen.
- **Kein `.dockerignore`** vorhanden → `build context: .` schickt `data/`, Logs, `.venv/` an den Daemon.

## Pipeline-Ablauf (Autopilot-tauglich seit 07/2026)

```
Step 0: GCP-Prep (prepare_gcp.py → anchor.txt + gcp_relative.csv)
Step 1: SAM3-Masken (extract_masks_notebook_flow.py)
Step 2: COLMAP SfM (run_sfm.sh → sparse/0, points3D.ply)
  → Breakpoint: CloudCompare Point-Picking (Autopilot überspringt)
Step 3: STS-Training (prep_sts_scene.py → train.py, 7000 Gesamtiterationen: 5000 Objekt-/Maskenphase + 2000 All-Object-Phase)
Step 4: SuGaR-Meshing (filter_cable_pc.py → run_masked_sugar.sh → refined.obj)
Step 5: Postprocess (postprocess.sh → Centerline + B-Spline + GeoJSON)
```

- **Autopilot-Modus (seit 26.08.2026):** `run_pipeline.sh` fragt als ERSTES nach Autopilot y/n; bei y bleiben nur zwei Fragen offen: Lauf-Preset (Auflösung) und Text-Prompt. Alles Weitere automatisch (Video-Komprimierung, SAM3-Auflösung preset-gekoppelt 1280/960/640, STS/SuGaR-Parameter, CloudCompare-Breakpoint, GCP-Reuse).
- **Lauf-Preset (seit 08/2026):** Abfrage nach Autopilot y/n wählt `RUN_RESOLUTION` = `720p` (1280x720, Standard) | `qhd` (960x540) | `low` (640x360). Bei qhd/low werden die Zielbreiten-/Höhenfragen im Video-Preprocessing fest vorbesetzt. Der Prompt zeigt GEMESSENE GESAMTlaufzeiten (Route A, 5 FPS, OPENCV; Quelle `matrix_e2e_verifikation_260826`, unabhängig bestätigt durch `matrix_qualitaetsvergleich_20260818`): 720p ≈ 40 min, qhd ≈ 34 min, low ≈ 24 min — aufgeschlüsselt in Kopf SAM3+COLMAP+Warp (5–8 min), STS→Postprocess (32/26/18 min), Schwanz Render/Archiv (~1 min). Analyse via `tools/analyze_e2e_times.py`. WICHTIG: Container-Logs (SAM3-Python, COLMAP-glog) schreiben UTC, Runner-Echos Lokalzeit — ohne Zeitzonen-Normierung entstehen Schein-Pausen von exakt 2 h.
- **Produktionsstand (seit 08/2026):** `COLMAP_CAMERA_MODEL`-Default ist nun `OPENCV` (statt `SIMPLE_RADIAL`) — aus der Matrixauswertung als Standard gewählt; Route A (`SUGAR_MESH_MODE=original_gs`) und 5 FPS bleiben Default. Geändert in `run_pipeline.sh`, `src/scripts/pipeline_lib.sh`, `src/scripts/run_sfm.sh`, `.env.example`.
- **Vor Autopilot-Auswahl bleiben 3 Eingaben:** HuggingFace-Token (einmalig, dann in `.env`), Text-Prompt (was segmentieren), Autopilot y/n.

## Centerline-Extraktion (Container E, `src/cpp/src/main.cpp`)

- **Modi:** `single` (Default, robust) und `network` (experimentell).
- **`single`-Modus:** Voxeliert Mesh (0,1 m), Flood-Fill, topologieerhaltendes Thinning (DGtal `asymetricThinningScheme`), dann `extract_diameter()` = BFS vom ersten Skeleton-Voxel (scan-order-abhängig!) zum weitesten, nochmal BFS, kürzester Pfad dazwischen. EIN Pfad, ignoriert Spurs automatisch. Startpunkt ist willkürlich (bounding-Box-Ecke), nicht strukturell.
- **`network`-Modus:** Zerlegt Skeleton-Graphen an Junction-Voxeln in Äste. Schreibt `branch_id,component_id,x,y,z`. Bei reinen Zyklen (alle Knoten Grad 2) wird der Loop geschlossen (Start==Ende).
- **Skeleton-Qualität auf verrauschten Meshes:** Bei 0,1 m Voxeln und dünnen, unebenen Röhren erzeugt das 2D-Isthmus-erhaltende Thinning bushy Skeletons (2D-Medialflächen + Stachel → Junction alle 1–2 Voxel → 302 Mikro-Äste, alle < 0,75 m → `MIN_PATH_LENGTH`-Filter verwirft alles → 0 Pfade im network-Modus). `single` funktioniert, weil der BFS-Diameter-Pfad Spurs ignoriert.
- **`--one-isthmus`-Flag (neu, 07/2026):** Wechselt das Thinning auf `DGtal::functions::oneIsthmus<Complex>` (nur 1D-Isthmus, kollabiert 2D-Medialflächen zu Kurven). Skeleton: 508→261 Voxel, saubere 1D-Kurven, aber fragmentiert (Lücken 0,5–1 m, Röhren-Enden rezidivieren). Baustein für network-Modus-Experimente; begrenzender Faktor bleibt Mesh-Qualität.
- **Gotcha:** `std::function`-Lambda mit Referenz-Capture von lokalen Variablen (`isthmus_table`, `point_map`) → Dangling-Reference-Segfault, wenn das Lambda nach dem Block verwendet wird. Fix: Variablen vor dem `if` deklarieren.
- **Extractor-Pfade:** `centerline_local_raw.csv` (Roh-Pfad, `x,y,z` im single-Modus; `branch_id,component_id,x,y,z` im network-Modus) → `centerline_local.csv` (B-Spline-geglättet).

## B-Spline (`src/python/centerline_bspline.py`)

- **Implementierung:** Geklemmter uniformer B-Spline via De-Boor-Algorithmus (`uniform_bspline_point`). Padding: `[points[0]] * degree + points + [points[-1]] * degree`. Endpunkte werden interpoliert (geklammert).
- **Degree einstellbar** (`--degree`, Default 10): Der aktuelle Alurohr-/lineare-Objekt-Standard nutzt Grad 10 fuer eine moeglichst glatte Kurve; Grad 1 bleibt linear, hoehere Grade sind zulaessig. Env-Var `BSPLINE_DEGREE`. Endpunkte bleiben durch die geklemmte Konstruktion erhalten.
- **Eckensegmentierung** (`--segment-corners`, im Produktionspfad Default aus): Die fruehere fensterbasierte Corner-Detection bleibt als Experiment verfuegbar, wird fuer die sanften linearen Erdkabelkurven aber nicht mehr verwendet. Env-Vars: `SEGMENT_CORNERS`, `SEGMENT_CORNER_WINDOW`, `SEGMENT_CORNER_ANGLE`.
- **Punktdichte:** `--samples-per-segment` (Default 4), Env `BSPLINE_SAMPLES_PER_SEGMENT`.
- **CSV-Schema:** `branch_id,component_id,x,y,z`. Wird von `transform_centerline.py` (Branch-Spalten durchgereicht), `centerline_geojson.py` (1 LineString pro Branch) konsumiert.
- **4× duplizierte CSV-Parsing-Logik** in `transform_centerline.py`, `centerline_bspline.py`, `centerline_geojson.py`, `centerline_graph_simplify.py` → faktorisieren in `centerline_io.py` (geplant).

## Georeferenzierung (`src/scripts/postprocess.sh`, umstrukturiert 07/2026)

- **Neuer Ablauf:** (1) Extractor → raw, (2) B-Spline → local, (3) lokales GeoJSON (`local_output.geojson`, SRS=LOCAL), (4) Georeferenzierung am ENDE.
- **Georeferenzierung-Priorität:** matrix.txt + anchor.txt vorhanden → volle 4×4-Transformation → `centerline_utm.csv` + `final_output.geojson` (EPSG:25832). Sonst → Fallback-Translation zu `FALLBACK_ANCHOR` (Default `567028.563,5516784.082,177`) → `centerline_fallback_georeferenced.csv` + `final_output_fallback_georeferenced.geojson`. Bricht **nicht** mehr ab.
- **OCR-Fallback:** Wenn `matrix.txt` fehlt aber `data/01_raw/matrix_screenshot.png` existiert und tesseract verfügbar → `ocr_matrix.py` läuft automatisch → `matrix.txt`.
- **`matrix.txt`-Format:** 16 Werte in 4 Zeilen (Komma oder Leerzeichen), letzte Zeile `0,0,0,1`, `#`-Kommentare erlaubt. Beispiel (real):
  ```
  -0.979,0.157,-0.123,-2.287
  -0.194,0.599,-0.776,2.658
  -0.048,0.784,0.618,-3.049
  0.000,0.000,0.000,1.000
  ```
- **`anchor.txt`-Format:** Exakt 3 Zahlen (Rechtswert, Hochwert, Höhe in m), Komma oder Leerzeichen. Zonen-Präfix `32U` NICHT in Datei (CRS wird erst bei GeoJSON-Export gesetzt). Wird von `prepare_gcp.py` aus erstem GCP der `gcp_coordinates.csv` erzeugt. Beispiel: `567028.563,5516784.082,175.230`.

## OCR / Tesseract (`src/python/ocr_matrix.py`)

- **Warum OCR nicht funktionierte (zwei Ursachen):**
  1. Container A (sam3-preprocess) hatte `tesseract-ocr` + `pytesseract` im Dockerfile, aber Image wurde nie neu gebaut → `tesseract: command not found`.
  2. Whitelist `-c tessedit_char_whitelist=0123456789.,-+ \n\r` unterdrückte Leerzeichenerkennung → alle Zahlen einer Zeile verschmolzen zu einem String; Timestamp `17:11:04` (Doppelpunkte nicht in Whitelist) wurde mit erster Zahl verbunden.
- **Fix (07/2026):** Whitelist entfernt (`--psm 6` allein), Timestamp-Präfix `[...]` wird herausgefiltert. Tesseract + pytesseract + pillow in **Container E** installiert (Dockerfile), OCR läuft dort automatisch am Ende. Rohe Tesseract-Ausgabe ohne Whitelist ist fast perfekt.
- **Container A** hat weiterhin tesseract im Dockerfile (für eigenständige OCR-Nutzung), aber Image muss neu gebaut werden (`docker compose build sam3-preprocess`).

## Perspektiventäuschung (Centerline-Loop)

- **Beobachtung:** Single-Mode-Pfad bildet Loop nur aus zwei exakt gegenüberliegenden Blickrichtungen. Erklärung: Start- und Endpunkt liegen ca. 24 cm auseinander in 3D. Blickrichtung (anti-)parallel zum Verbindungsvektor → beide projizieren auf denselben Bildpunkt → offener Bogen sieht wie geschlossener Loop aus. Von jeder anderen Richtung ist die Lücke sichtbar. Reine 3D→2D-Projektion, kein Code-Bug.

## COLMAP (`src/scripts/run_sfm.sh`)

- 4 Stagen: `feature_extractor` → `sequential_matcher` (overlap 20, guided_matching 1) → `mapper` (abs_pose_min_num_inliers 15, min_num_matches 10) → `model_converter` (bash-Loop sucht größtes Teilmodell).
- Dense MVS korrekt übersprungen.
- **Fehlende Optimierungen:** kein `--num_threads`, kein `--SiftExtraction.max_image_size` (Default 3200), `max_num_features 16384` (sehr hoch), kein `--ImageReader.mask_path` (Masks sind upstream vorhanden!), `database.db` wird每次 neu erzeugt, `colmap/colmap:latest` ungepinnt.
- **Geschätzter Speedup bei Optimierung: 50–70 %.**

## STS / SuGaR

- **Defaults (Autopilot):** `ITERATIONS=7000` Gesamtiterationen im STS-Curriculum (`STAGE2_ITERS=5000` Objekt-/Maskenphase, danach 2000 All-Object-Iterationen), `COARSE_ITERATIONS=9000`, `MESH_VERTICES=200000`, `SURFACE_SAMPLE_COUNT=5000000`, `REFINEMENT_TIME=medium` (=7000 Refinement-Iter), `REGULARIZATION=dn_consistency`, `MASK_LEVEL=default`, `NORMAL_MASK_LEVEL=middle`, `TEXTURE_MASK_LEVEL=default`, RGB/UV-Dilatation `0`.
- **`STOP_AFTER_COARSE_MESH=1`** existiert, ist im Autopilot nicht verfügbar → skippt ~7000 Refinement + UV + Crop. Potenzieller „Screening"-Modus.
- **6 sequenzielle `docker compose run` zwischen STS→SuGaR** (object_init, train, copy-ply, filter_cable, opacity-rewrite, filter_cameras, sugar_train) → jeweils ~10–30 s CUDA-Init.
- **PLY wird 4× kopiert:** STS-Save → Full-Scene → gefiltert → Opazitäts-Rewrite → gestaged.
- **`filter_cable_pc.py` + `create_opacity_diagnostic_ply.py`** laden beide die volle PLY, könnten verschmolzen werden.
- **`prep_sts_scene.py`:** `cv2.imread(frame)` nur um Shape zu lesen → `PIL.Image.open().size` spart ~700 JPEG-Decodes.
- **Docker:** STS git clone nicht auf SHA gepinnt (SuGaR macht es richtig via `SUGAR_REF`). `TORCH_CUDA_ARCH_LIST="7.0;7.5;8.0;8.6;8.9;9.0"` baut 6 Architekturen → Build ~6× langsamer als nötig. Container D ~10 GB (Miniconda + devel-CUDA + pytorch3d).

## Shell-Orchestrierung — Duplikation

- **`pipeline_lib.sh`** existiert mit `run_step_*`-Funktionen + `run_pipeline_from <step>`, wird aber von **keinem** Skript gesourced → tote Code.
- **`run_from_colmap.sh` / `run_from_sts.sh`** sind byte-identische Teilmengen von `run_pipeline.sh`.
- **`explain_*`-Helfer** 5× kopiert. **`ask_value`/`ask_config_value`/`ask_yes_no`** 3× kopiert.
- **Postprocess-Aufruf** 5× identisch. **Inline-Python „preserve full-scene PLY"** 4× kopiert mit `(_ for _ in ()).throw(...)`-Idiom.

## Python-Skripte — Code-Kultur

- **Produktionsreif (argparse, dataclasses, Fehlerbehandlung):** Centerline-Familie (`centerline_bspline.py`, `centerline_geojson.py`, `transform_centerline.py`, `centerline_graph_simplify.py`), `crop_mesh_multiview.py`, `filter_sugar_cameras_by_mask.py`, `create_opacity_diagnostic_ply.py`.
- **Explorativ (hardcodierte Pfade, `os._exit()`, `print("Error")+return`):** `extract_masks.py` (tot), `extract_masks_notebook_flow.py`, `prep_sts_scene.py`, `prepare_gcp.py`, `generate_hierarchical_masks.py` (tot), `evaluation.py` (Stub, tot), `ocr_matrix.py` (manuelles `sys.argv`).
- **Tote Skripte (kein Pipeline-Aufruf):** `extract_masks.py`, `generate_hierarchical_masks.py`, `evaluation.py`, `generate_synthetic_gcp.py`, `export_mask_review_samples.py`, `centerline_graph_simplify.py`.
- **Keine Tests** vorhanden (`tests/` fehlt).

## Daten-Verzeichnisse

| Verzeichnis | entsteht wie? |
|---|---|
| `data/01_raw/` | manuell (Eingabevideo + GCP-CSV) |
| `data/02_frames/` bis `data/09_evaluation/` | automatisch (Pipeline) |
| `data/hf_cache/` | automatisch (HuggingFace-Cache) |
| `data/sugar_output/` | automatisch (SuGaR-Checkpoints) |

## Repo-Umzug-Plan (in `PIPELINE_ANALYSE_PLAN.md` dokumentiert, nicht ausgeführt)

- Fresh `git init`, ein Initial-Commit mit Verweis auf Ursprungsrepo.
- `third_party/SuGaR` als Git-Submodule (`.gitmodules` verweist auf `MartinRapps/SuGaR @ 48bbfdd`).
- `ui/` und `docs/agent-memory-repo.md` werden mit übernommen.
- 6 tote Skripte nach `tools/`.
- Refactorings: `centerline_io.py`/`mask_paths.py`/etc. faktorisieren, `pipeline_lib.sh` ausbauen, `run_from_*.sh` zu `--from`-Wrappern, `.dockerignore`/`.gitignore`/`tests/`.

## Wichtige Env-Vars (Postprocess)

| Var | Default | Zweck |
|---|---|---|
| `CENTERLINE_MODE` | `single` | Extractor-Modus (single/network) |
| `VOXEL_SIZE` | `0.1` | Voxelgröße in m |
| `MIN_PATH_LENGTH` | `0.75` | Mindestastlänge in m |
| `BSPLINE_DEGREE` | `10` | B-Spline-Grad (mindestens 1; aktueller glatter Standard) |
| `BSPLINE_SAMPLES_PER_SEGMENT` | `4` | Punkte pro Segment |
| `SEGMENT_CORNERS` | `0` | Eckensegmentierung an/aus |
| `SEGMENT_CORNER_WINDOW` | `4` | Fenstergröße Corner-Detection |
| `SEGMENT_CORNER_ANGLE` | `30` | Min-Winkel in Grad |
| `FALLBACK_ANCHOR` | `567028.563,5516784.082,177` | Fallback-Translation bei fehlender Georeferenzierung |
| `GEOJSON_SRS` | `EPSG:25832` | SRS für GeoJSON-Export |
| `ONE_ISTHMUS` | (CLI-Flag) | 1D-only-Thinning im Extractor |

## Wichtige Dateien (geändert in dieser Session)

| Datei | Änderung |
|---|---|
| `src/cpp/src/main.cpp` | `--one-isthmus`-Flag, Dangling-Reference-Fix |
| `src/python/centerline_bspline.py` | De-Boor-Implementierung (Grad >=1, Standard 10), optionale Eckensegmentierung, `--degree`/`--segment-corners` |
| `src/python/centerline_graph_simplify.py` | NEU (Spur-Pruning, Junction-Clustering für network-Modus) |
| `src/scripts/postprocess.sh` | Georeferenzierung ans Ende, lokales GeoJSON, Fallback, OCR-Integration, Fehlerbehandlung |
| `src/python/ocr_matrix.py` | Whitelist entfernt, Timestamp-Filter |
| `docker/container-e-postprocess/Dockerfile` | tesseract-ocr + pytesseract + pillow |
| `run_pipeline.sh` | Autopilot-Absicherung (GCP/Breakpoint), OCR-Dialog durch Hinweis ersetzt |
| `README.md` / `setup_guide.md` | Centerline-Ablauf, B-Spline-Degree, Georeferenzierung, Fallback |
| `Themenfindung/Expose_PA_BA.tex` | Centerline-Abschnitt, Dateiformate matrix/anchor, [GELÖST]-Eintrag Skeleton, OCR-Abschnitt aktualisiert |
| `PIPELINE_ANALYSE_PLAN.md` | NEU (Master-Plan Analyse + Umzug) |

## Gotchas & Lessons Learned

- **Voxel-Skeleton auf verrauschten Meshes:** 2D-Isthmus-erhaltendes Thinning erzeugt bushy Graphen (Sheets + Spurs). `single`-Modus robust (BFS-Diameter ignoriert Spurs). `network`-Modus braucht Junction-Clustering + Spur-Pruning + Gap-Bridging → fragil. Coarsere Voxelgröße (0,15–0,25 m) fragmentiert stattdessen.
- **`set -e` + nicht-leere Fehler-Datei:** Extractor schreibt CSV-Header, dann Exception → Datei nicht leer → `[[ ! -s ]]`-Check passiert → Pipeline fährt mit leerer CSV fort. Fix: `[[ $(wc -l) -lt 2 ]]` prüfen + stderr ausgeben.
- **Docker `--break-system-packages`:** Ubuntu 22.04's pip (22.0.2) kennt diesen Flag nicht → Build fehlschlägt. Auf 22.04 weglassen, auf 24.04 notwendig.
- **Float-Repräsentation Container vs. Host:** Dieselbe De-Boor-Berechnung liefert `-1.48082` (Host) vs. `-1.4808199999999998` (Container) — 1-ulp-Unterschied durch Summationsreihenfolge. Für Geometrie irrelevant (1e-15).
- **SuGaR-Submodule:** Der Parent-Gitlink und das Dockerfile verwenden `MartinRapps/SuGaR@48bbfdd` (Martins Fork mit Masken-Mods). Das Submodul muss nach einem frischen Clone mit `git submodule update --init --recursive` initialisiert werden, weil der Runner den lokalen Stand fuer den mask-aware Pfad ueber das Dev-Overlay mountet. `third_party/SuGaR/train.py` besitzt aktuell zusaetzlich eine uncommitted Working-Tree-Aenderung fuer die c9000-Zulassung; vor einem Release muss diese Aenderung in Martins Fork committed und der Parent-Gitlink aktualisiert werden.
- **Exposé-Kompilieren:** Auf dem Host ist kein `pdflatex` installiert. Die offizielle MiKTeX-Docker-Idee ist korrekt, aber `miktex/miktex:essential` beziehungsweise `basic` (MiKTeX 23.10) scheitert am 04.08.2026 beim Aufbau von `pdflatex.fmt`, weil das geladene `miktex-latex`-Paket die erwartete `pdflatex.ini` nicht enthält. Verifiziert funktionierend ist `texlive/texlive:latest-small` mit `--user $(id -u):$(id -g)`, `HOME=/tmp`, `TEXMFVAR=/tmp/texlive-var`, `TEXMFCONFIG=/tmp/texlive-config` und `TEXMFHOME=/tmp/texlive-home`: aus `docs/` `pdflatex -file-line-error -interaction=nonstopmode -halt-on-error Expose_PA_BA.tex` ausführen.

## Entscheidungen nach FAQ (08/2026)

- **Projektumfang:** Das Alurohr ist der aktuelle lineare Testdatensatz fuer die Projektarbeit. Sonnenbrillen-Laeufe dienten vor allem der SuGaR-Entwicklung. Reale Rohr-/Kabelaufnahmen in Graeben gehoeren zur spaeteren Bachelorarbeit; die +/-10-cm-Metrik gilt dort, nicht als aktueller Projektarbeitsnachweis.
- **Produktionsweg:** Docker mit GPU ist der Zielweg. Die Windows-11-COLMAP-Laeufe ohne CUDA sind getrennte Vergleichstests. In der aktuellen Ubuntu-Umgebung sind RTX 4000 Ada, Docker und `--gpus all` funktionsfaehig; `nvidia-smi` meldet rund 20 GB VRAM.
- **Bind-Mount-Berechtigungen:** Der Ubuntu-Benutzer verwendet UID `190290584` und GID `190200513`, waehrend Compose ohne gesetzte Variablen auf `1000:1000` zurueckfaellt. Bei Eingabedateien mit Modus `600` fuehrt das zu `Permission denied`. `run_pipeline.sh` und `pipeline_lib.sh` exportieren deshalb standardmaessig die aktuelle `id -u`/`id -g`; `prepare_gcp.py` beendet sich bei Lese- oder Schreibfehlern jetzt mit einem Fehlercode statt die Pipeline fortzusetzen.
- **Per-Run-Logging:** Jeder Masterlauf erzeugt `data/10_runs/<video>_<YYYYMMDD_HHMMSS>/run.log` mit kompletter Terminal-/Docker-Ausgabe und `run.md` mit Input, Konfiguration, Schrittzeitpunkten, Status und Laufzeiten. Das Logging wird auch bei Fehlern ueber einen EXIT-Trap abgeschlossen.
- **Frame-/COLMAP-Standard:** Der aktuelle Default ist 1280x720, 5 FPS, unmaskierte Bilder, `SIMPLE_RADIAL`, 4096 Plain-SIFT-Merkmale, Sequential-Overlap 15, Guided Matching aus und Peak-Threshold 0.003. Nach dem SfM erzeugt `run_sfm.sh` automatisch `data/04_sfm/undistorted/` mit idealen `PINHOLE`-Kameras fuer STS; das originale radiale Modell bleibt fuer GCP/UI und SfM-Auswertung erhalten. Spaetere Fast-/High-Quality-Profile sind Erweiterungen, nicht der Projektarbeitsstandard.
- **SuGaR-Standard:** STS laeuft mit 7000 Gesamtiterationen: 5000 Iterationen fuer die Objekt-/Maskenphase und anschliessend 2000 Iterationen fuer alle Objekte. Der mask-aware SuGaR-Standard nutzt `dn_consistency`, Coarse-Zielzaehler `9000`, `MASK_LEVEL=default`, `NORMAL_MASK_LEVEL=middle`, `TEXTURE_MASK_LEVEL=default`, null RGB-/UV-Dilatation, 200000 Mesh-Vertices, 5000000 Oberflaechenstichproben, mittleres Refinement und keinen Consensus-Crop. Die fruehere harte `>9000`-Sperre wurde aufgehoben. Fuer `c9000` werden die spaeteren DN-/SDF-Terme nicht erreicht; sie bleiben fuer Vergleichslaeufe oberhalb 9000 verfuegbar. Ein schnellerer `density`-Modus ist fuer spaeter vorgesehen.
- **Centerline-Standard:** Der `single`-Modus bleibt fuer die einzelne Trasse im Scope. Der aktuelle Produktionspfad verwendet keine Eckensegmentierung und einen geklemmten uniformen B-Spline mit Grad 10; der Grad ist im Code ab 1 frei waehlbar. Der Network-Modus bleibt ausserhalb des Projektarbeitsumfangs.
- **GCP/UI:** Die UI markiert GCPs in registrierten COLMAP-Bildern, trianguliert sie und berechnet die relative SfM-zu-UTM-Aehnlichkeitstransformation. `prepare_gcp.py` setzt standardmaessig den ersten GCP als Anchor und subtrahiert ihn fuer `gcp_relative.csv`. Observationen werden serverseitig auf bekannte relative GCPs, registrierte Frames und endliche Bildkoordinaten begrenzt; bei einer Aenderung werden alter Report und `matrix.txt` invalidiert. Eine explizite Anchor-Auswahl in der UI ist noch ein Verbesserungsziel. Die aktuelle Test-CSV ist ein synthetisches lokales Raster und daher kein echter UTM-Nachweis.
- **`postprocess_mesh`:** Die SuGaR-Funktion ist eine optionale Bereinigung des finalen refined OBJ. Sie entfernt iterativ topologische Randdreiecke mit niedriger Gaussian-Dichte und kann dadurch duenne Strukturen oder relevante Raender verlieren. Sie ist nicht mit dem Multi-View-Crop identisch und bleibt bis zu einer kontrollierten Ablation deaktiviert.
- **SuGaR-Output-Berechtigungen:** Der mask-aware Runner schreibt seine Ausgaben unter `/data/sugar_output/<run-tag>` statt unter dem vom lokalen Fork-Overlay verdeckten `/opt/sugar/output`. Der verschachtelte Compose-Mount wurde entfernt, damit `docker compose up -d` kein root-owned `data/sugar_output` anlegt.
- **Poisson-Hintergrundschutz:** Bei der Alurohr-Coarse-Extraktion kann die kamera-basierte Bounding-Box fast alle Surface-Samples als Foreground klassifizieren; der Background enthielt im Befund nur 1--2 Punkte. `sugar_extractors/coarse_mesh.py` ueberspringt Poisson jetzt bei zu kleinen oder ungueltigen Punktwolken/Normalen und verwendet das gueltige Foreground-Mesh weiter.
- **SuGaR-Recovery:** `EXPORT_ONLY=1 REPLACE=1 ./run_pipeline.sh --from sugar` kopiert einen bereits vorhandenen OBJ/MTL/Texture-Export nach `data/06_mesh/` und startet danach Container E ohne erneutes SuGaR-Training. Eine Refined-PLY ist fuer die Centerline nicht erforderlich.
- **STS-Curriculum-Logging:** `stage2_iters=5000` liegt innerhalb von `iterations=7000`: Iterationen 1--5000 rendern Small/Middle-Objektmasken, Iterationen 5001--7000 rendern alle Objekte. Container C verwendet `PYTHONUNBUFFERED=1`, damit die Stage-2-/Stage-3-Marker im Run-Log zeitlich korrekt sichtbar sind.
- **COLMAP-Image:** Fuer die Projektarbeit bleibt `colmap/colmap:latest` bewusst bestehen. Der dokumentierte Tag `4.0.4-cuda` ist im offiziellen Repository nicht vorhanden; ein beobachteter `latest`-Digest vom 04.08.2026 war `sha256:b809882552887b6471094dcadd2f2eb01656b010663564c43a5e7f04c0a08f2f`.

## Finaler Abgabestand & Korrekturen (Stand: 03.09.2026)

### 1. Repository-Architektur (Zwei Repositories)
- **`scan2bim-pipeline` (Arbeits-/Entwicklungs-Repo, Branch `pa-fertigstellung`):**
  - Beinhaltet die komplette Entwicklungs- und Revisionshistorie, alle internen Arbeitsnotizen (`Korrekturplan_Kommentare.md`, `Arbeitsdatei_Fertigstellung.md`), unkomprimierte Artefakte und Zwischenstände.
  - Bleibt als privates Entwicklungsarchiv bestehen.
- **`scan2bim-abgabe` (Abgabe-Repo, Branch `main`, Remote `https://github.com/MartinRapps/scan2bim.git`, privat):**
  - Aufgeräumtes, schlankes Abgabe-Repository für die Prüfer ohne internen Entwicklungsballast und ohne >100-MB-Dateien (vollständig GitHub-konform).
  - Quell-Commit der Abgabe: `8f46953b9747e1399b8e39a404c45673bebadd5e` (im `ABGABE_Index.md` stabil referenziert).
  - Enthält die kompilierbare PA (`PA/`), Pipeline-Code (`src/`, `tools/`, `docker/`), den lokalen SuGaR-Fork (`third_party/SuGaR/` Quellstand `a0fc37b`), Grafiken und das `ABGABE/`-Prüferpaket.
  - Die 31 GB Rechendaten (`data/`) und Schwerlast-Dateien aus `ABGABE/04_Run-Archive/` (z. B. 1,1-GB-Checkpoints) werden per Cloud-Download bzw. USB-Datenträger ausgeliefert (PABA 3.7).

### 2. Stand der Projektarbeit (`pa.pdf` und `pa_anonym.pdf`)
- **Seitenzahl & Kompilierung:** 65 Seiten (64 S. anonym), fehlerfrei kompilierbar via `bash build_pa.sh` und `bash build_pa_anonym.sh`.
- **Titelblatt:** Vollständig ausgefüllt ohne eckige Klammern (Martin Rapps, Matrikel 6323014, B. Eng. Geovisualisierung, Erstprüfer Dr. Markus Müller, Zweitprüfer Andreas Rupp, Abgabetermin 04.09.2026).
- **Eigenständigkeitserklärung (S. II):** Exakter Wortlaut der offiziellen PABA-Anlage 3 inklusive der vollständigen KI-Klausel und dem Satz: *„Ich versichere, dass ich ausschließlich KI-Werkzeuge verwendet habe, deren Nutzung vom Prüfer oder der Prüferin als Hilfsmittel zugelassen wurden.“*
- **PlagAware-Einwilligung (S. III):** 1:1 Nachbau der offiziellen PABA-Anlage 4 mit den Daten des Verfassers vorausgefüllt (Name, Vorname, Matrikel, Studiengang, Titel). Der einschränkende Hinweis *„Diese Einwilligung ist freiwillig...“* wurde wunschgemäß entfernt. Handschriftlich nachzutragen: Adresse, studentische E-Mail, Ort/Datum, Unterschrift.
- **Anonymisierte Fassung (`pa_anonym.pdf`):** Deckblatt ohne Name und Matrikelnummer; PlagAware-Seite ausgeblendet (entsprechend PABA Fußnote 13: PlagAware-Einwilligung macht Anonymisierung überflüssig, dennoch als Fallback generiert). Textstand ist 100 % identisch zur Hauptfassung.
- **Kurzfassung:** Auf eine einzige Überschrift bereinigt (*„Kurzfassung“*, die doppelte `abstract`-Überschrift *„Zusammenfassung“* wurde entfernt). Beinhaltet konkrete Kernergebnisse (240/240 Bilder registriert, 29,62 dB PSNR, 9 erfolgreiche Autopilot-Volläufe).
- **Anhang G (KI-Nutzung):** Formuliert als *„in sechs Bereiche gegliederte Dokumentation“*. Der veraltete Baustein *„Offen vor Abgabe: Die vollständige Eigenständigkeitserklärung…“* wurde ersatzlos entfernt.

### 3. Fachliche & Stilistische Korrekturen
- **GSD (Ground Sampling Distance / Bodenauflösung):** In Kapitel 8.3 sauber als *„Bodenauflösung (Ground Sampling Distance, GSD: reale Objektgröße eines Bildpixels)“* eingeführt. Die Argumentation bleibt relativ (720p feiner als low), da ohne geodätische Maßstabsreferenz keine absoluten Millimeterangaben zulässig sind.
- **„zweifach“-Satz (Kapitel 8.3):** Präzisiert zu: *„Daraus folgen zwei Konsequenzen: Erstens dürfen Auflösungen nicht in einer globalen Rangliste verglichen werden. Zweitens sind nur gepaarte Vergleiche von STS gegen SuGaR innerhalb derselben Auflösung belastbar.“*
- **SuGaR-Historie (Kapitel 5.2):** Die unübersichtliche 6-Zeilen-Tabelle mit Git-Commits (`48bbfdd` bis `a0fc37b`) wurde gestrafft und durch eine prägnante funktionale Aufzählung der Kernänderungen des finalen Forks ersetzt. Die Panels (Abb. 2, 3 in 5.7 und Abb. 8 in 7.8) bleiben im Text erhalten; ihre Kacheln sind verständlich erklärt und auf Anhang D verwiesen.
- **Zeichensetzung & Grammatik:** Über 150 Semikola satzweise aufgelöst, faule Konnektor-Doppelpunkte durch Punkte ersetzt, Tausender-Punkte in Prosa durchgängig gesetzt (`4.096`, `7.000`, `9.000`, `2.011`, `1.650`, `1.199`, `8.192`).
- **Begriffe:** *stdin* als *„Standardeingabe (stdin)“* definiert; *„führt … Entscheidungen durch“* und *„…und Kapitel 4 das Konzept fest.“* korrigiert.
- **Widerspruchsbereinigung:**
  - Dilatations-Widerspruch gelöst: Überall verbindlich als Erosionshierarchie (`default`, `middle`, `small`) ohne Dilatation definiert (1.2 und Tab. 3 korrigiert).
  - Autopilot-Zählung korrigiert: Genau 9 erfolgreiche archivierte Volläufe (die restlichen 5 Ordner dokumentieren transparente Fehlversuche).
  - Centerline-Werte auf den beiliegenden Golden Run abgeglichen: 85 Rohpunkte, 372 B-Spline-Punkte (`centerline_local_raw.csv` bzw. `centerline_local.csv`).
  - Fehlverweis *„Anhang 9“* korrigiert zu *„Tabelle 9 im Anhang A“*.

### 4. Laufzeitmessung & E2E-Zeiten
- **Zeitzonen-Befund:** Container loggen intern UTC, Runner-Echos in Lokalzeit (+0200, CEST). Ohne Normierung entstanden Scheinpausen von exakt 2 Stunden. `tools/analyze_e2e_times.py` normiert alle Zeitstempel auf UTC-Epochen.
- **Gemessene Gesamtlaufzeiten (Verifikationsbatch `matrix_e2e_verifikation_260826`):**
  - 720p: 40:25 min (Kopf 7:49, STS→Post 32:23, Nachlauf ≤0:52)
  - qHD: 33:52 min (Kopf 7:17, STS→Post 26:24, Nachlauf ≤0:44)
  - low: 23:46 min (Kopf 5:27, STS→Post 18:11)
  - Unabhängig bestätigt durch Gegenprobe-Batch `matrix_qualitaetsvergleich_20260818` (40:16 / 34:35 / 24:02 min).
- **Preset-Dialog:** In `run_pipeline.sh` und PA-Kapitel 4.5/5.4/6.7 auf diese gemessenen Werte aktualisiert.
- **Grafik `metric_vs_runtime`:** x-Achse und Untertitel ehrlich auf *„Archivierte Laufzeit STS→Postprocess (min)“* korrigiert, Caption verweist auf die E2E-Tabelle 7.6.

### 5. KI-Anlage & Dokumentation
- **`Anlage_KI-Nutzung.pdf` / `.tex` / `.md`:** 6 Seiten, 6 Bereiche inklusive des kleinschrittigen Prüfer-Persona-Workflows (Erstellung von `persona.md`, Ordnerstruktur-Review, Root-Dateien, kapitelweise Prüfung, Konsolidierung).
- Modellliste: `GPT-5.6 Luna (max)`, `Gemini 3.5 Flash (max)`, `Gemini 3.7 Flash (max)`, `Kimi K3 (max)`, `GLM 5.3 Flash (max)`, `GPT-5.6 Sol (max)`.
- Vollständige Prüfer-Simulation als methodischer Qualitätssicherungsschritt vor der Einreichung durchgeführt und in der KI-Anlage dokumentiert.
