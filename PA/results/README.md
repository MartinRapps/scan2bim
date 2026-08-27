# Ergebnisquellen

Die PA kopiert keine großen Trainings- oder Renderarchive. Die vollständigen
Experimente liegen unter:

- `../../data/10_runs/matrix_e2e_verifikation_260826/`: E2E-Verifikationsbatch
  (720p/qhd/low, Route A, OPENCV, 5 FPS) mit gemessenen Gesamtlaufzeiten
  (40:25/33:52/23:46 min); Auswertung in `e2e_times.csv`/`e2e_times.md`,
  Pflichtnachweis-Prüfsummen in `SHA256SUMS.txt`;
- `../../data/10_runs/matrix_qualitaetsvergleich_20260818/`: unabhängiger
  Gegenprobe-Batch (alle drei Kameramodelle Route A, SuGaR-Coarse-Arm,
  failed=0); Golden-Run-Quelle und Bestätigung der E2E-Zeiten;
- `../../data/10_runs/Alurohr_THWS_*`: archivierte Autopilot-Läufe
  (18./20./26.08.2026, Status SUCCESS);
- `../../data/10_runs/matrix_full_pipe/`, `matrix_rest/`,
  `matrix_sugar_followup_12/`, `matrix_repeat_20260812/`: historische Batches;
  die Vollarchive wurden nach externem Backup komprimiert (siehe
  `Archivierungsempfehlung_Matrix.md`); Metrik-/Statusnachweise liegen im
  Abgabepaket (`../Fertigstellung/ABGABE_Index.md`, Ordner `04_Run-Archive/`);
- `../../data/10_runs/matrix_qualitaetsvergleich_20260818`: Qualitätsvergleichs-
  batch (3 Kameramodelle × Route A × 3 Auflösungen + SuGaR-Arme, failed=0,
  Golden-Run-Quelle für den Arm 5fps/720p/opencv_a);
- `../../docs/grafiken/verwendet_verbessert/`: weiterhin verwendete
  Statusgrafiken und historische gemeinsame CSV-/Methodikquellen;
- `../../docs/grafiken/matrix_repeat_2026-08-17/`: aktuelle, getrennte
  STS-/SuGaR-Coarse-Übersichten, Einzelansichts-Boxplots, Delta- und
  Laufzeitgrafik. Die SuGaR-Coarse-Auswertung verwendet ausschließlich
  `metrics/sugar_coarse_masked.json`; übersprungene
  `sugar_refined_masked.json`-Dateien werden nicht als Refinement-Ergebnisse
  ausgegeben;
- `../../docs/grafiken/archiv_alt_2026-08-12/`: ältere, nicht mehr eingebundene
  Grafikstände.

**Ablagestand 23.08.2026:** `data/10_runs/` ist im Repository nicht vorhanden
(laufzeiterzeugt/gitignored). Die Archive liegen derzeit extern (Arbeits-VM
beziehungsweise V-Laufwerk); vor der Abgabe sind Prüfsummen zu dokumentieren,
siehe `appendices/appendix_anlagenindex.tex` in der Arbeitsfassung.

Die Kernkapitel verwenden nur zusammengefasste Werte. Einzelne Logs und
COLMAP-Benchmarkdateien werden in den optionalen Anhängen referenziert. Die
Empfehlung, welche Runbestandteile dauerhaft beziehungsweise nur für Golden
Runs gespeichert werden sollten, steht in
`../Archivierungsempfehlung_Matrix.md`.
