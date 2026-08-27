# E2E-Verifikationslauf – Startanleitung

Zweck: Gemessene **Gesamtlaufzeiten** (SAM3 + COLMAP + Maskenwarp + STS→Post +
Render/Archiv) der drei Lauf-Presets 720p / qhd / low in der
Produktionskonfiguration (Route A, OPENCV, 5 FPS) archivieren. Diese Werte
ersetzen die bisher rekonstruierten Schätzzeiten in `run_pipeline.sh` und der PA
und liefern die korrekte Grundlage für die Laufzeit-Diskussion (Kapitel 8.6).

## Vorbedingungen

- GPU frei (der Batch belegt sie exklusiv, ca. 2,5 h Gesamtrechenzeit);
- ca. 8–10 GB freier Plattenplatz unter `data/` (Live-Workspace + Archive);
- `.env` mit gültigem `HF_TOKEN` vorhanden (ist gesetzt);
- kein anderer Prozess nutzt `data/02_frames` bis `data/08_gis`
  (der Matrixrunner bereinigt den Live-Workspace zwischen den Läufen selbst).

## 1. Trockenlauf prüfen (ohne GPU, Sekunden)

```bash
MATRIX_CONFIG=tools/experiment_matrix_e2e_verifikation.tsv \
./tools/run_experiment_matrix.sh --fps 5 --dry-run
```

Erwartet: genau drei geplante Läufe `opencv_a` bei 720p, qhd und low (5 FPS).
Trotz des Namens „Verifikation" werden dieselbenvalidierten Defaults wie in der
Produktionsmatrix verwendet (4096 SIFT, Overlap 15, 7000/5000 Iterationen,
200k Vertices, Seed 42).

## 2. Batch starten

```bash
MATRIX_BATCH_ID=matrix_e2e_verifikation_$(date +%Y%m%d) \
MATRIX_CONFIG=tools/experiment_matrix_e2e_verifikation.tsv \
./tools/run_experiment_matrix.sh --fps 5
```

Hinweise:
- Der Batch läuft seriell (720p → qhd → low) und archiviert jeden Lauf unter
  `data/10_runs/matrix_e2e_verifikation_<datum>/5fps/<aufloesung>/opencv_a/`.
- Unterbrechungen sind unkritisch: Der Batch kann neu gestartet werden;
  bereits archivierte Läufe bleiben erhalten. Wichtig ist nur, Pausen
  (Maschinen-Idle) nach Möglichkeit zu vermeiden – das Auswerteskript weist
  sie separat aus, saubere Messwerte sind besser.
- Nach dem letzten Lauf wird der Live-Workspace automatisch bereinigt.

## 3. Auswerten (nach Abschluss)

```bash
python3 tools/analyze_e2e_times.py \
    data/10_runs/matrix_e2e_verifikation_<datum>/matrix.log
```

Ausgabe: `e2e_times.csv` und `e2e_times.md` im Batch-Ordner mit Kopf-/RUN-/Nachlauf-
Phase, Gesamt-Wandzeit und Rechenzeit ohne Pausen je Experiment.

Plausibilitätscheck: Kopf (SAM3+COLMAP+Warp) sollte bei 720p bei ca. 6–8 min
liegen (Vergleichswert aus `matrix_qualitaetsvergleich_20260818`), STS→Post bei
ca. 33 min, qhd ≈ 27 min, low ≈ 19 min. Größere Abweichungen sind verwertbar,
werden aber in der PA als Messergebnis (nicht als Erwartung) berichtet.

## 4. Danach (wird von der Nachbereitung übernommen)

- Preset-Zahlen in `run_pipeline.sh` (Tabelle + EXPLAIN) auf Messwerte setzen;
- PA-Kapitel 4.5/5.4 auf Messwerte umstellen, neue E2E-Tabelle ergänzen;
- Grafik `metric_vs_runtime` korrekt umlabeln (x-Achse = archivierte
  STS→Post-Laufzeit, nicht Gesamtlaufzeit);
- Anlagenindex/READMEs um den Batch inkl. Prüfsummen erweitern.
