# Wiederholungsmatrix-Grafiken (2026-08-17)

- 30 erfolgreiche Läufe aus `matrix_repeat_20260812/` (Vollarchive extern komprimiert; verifizierbare Quelle sind die CSV-Dateien in diesem Ordner).
- STS-/Original-GS-Kameras: `SIMPLE_RADIAL`, `PINHOLE` und `OPENCV`.
- SuGaR-Coarse-Kameras: `SIMPLE_RADIAL` und `OPENCV`.
- Alle Konfigurationen enthalten 2/5 FPS sowie 720p/QHD/Low.
- STS-Übersicht und STS-Boxplots enthalten nur vollständige `original_gs`-Läufe.
- SuGaR-Coarse verwendet ausschließlich `sugar_coarse_masked.json`.
- Boxplots verwenden die `per_frame`-Werte; y-Ranges umfassen alle Einzelwerte.
- Die Laufzeitgrafik verwendet die archivierte Pipeline-Segmentzeit STS→Postprocess (run.md-Fenster; SAM3/COLMAP nicht enthalten).
- Grün/Lila kodieren STS/SuGaR-Coarse; kräftig/blass kodiert 5/2 FPS; Kreis/Quadrat/Dreieck kodiert 720p/QHD/Low.
- In den STS-Übersichten und -Boxplots kodieren Blau/Orange/Grau die
  Kameramodelle SR/OPENCV/PINHOLE.
- Die sechs Grafiken sind Rendering-/Ansichtsmetriken und kein Geometrienachweis.

## Files

- `sts_masked_overview.pdf` / `sugar_coarse_masked_overview.pdf`: aggregate per-run metric comparisons
- `sts_masked_per_frame_boxplots.pdf` / `sugar_coarse_masked_per_frame_boxplots.pdf`: per-view distributions
- `sugar_coarse_vs_sts_delta.pdf`: paired stage difference on identical follow-up runs
- `metric_vs_runtime.pdf`: exploratory metric/runtime relation
- `*_summary.csv`, `*_per_frame.csv`: provenance sources
