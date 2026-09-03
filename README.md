# Scan-to-BIM Pipeline — Abgabe-Repository

Sauberes Abgabe-Repository der Projektarbeit „KI-gestützte 3D-Rekonstruktion
eines linearen Objekts" (THWS, Studienbereich Geo). Enthält genau das, was zum
**Ausführen der Pipeline** und zum **Kompilieren der Projektarbeit** nötig ist.

## Projektarbeit bauen

```bash
cd PA
bash build_pa.sh          # -> PA/build/pa.pdf
# bzw. Windows: powershell -File build_pa.ps1
```

Die abgegebene Fassung liegt unter `ABGABE/pa.pdf` (64 S., mit PlagAware-
Einwilligung) und `ABGABE/pa_anonym.pdf` (63 S., ohne Name/Matrikel).

## Pipeline ausführen (Überblick)

```bash
cp .env.example .env                 # HuggingFace-Token eintragen
docker compose build                 # Container bauen
./run_pipeline.sh                    # interaktiver Vollauf (Autopilot möglich)
./tools/run_experiment_matrix.sh     # Matrix-/Batchläufe
```

Details: `setup_guide.md`, Parameterdokumentation in `run_pipeline.sh`
(EXPLAIN-Texte), Auswertung via `tools/analyze_e2e_times.py`.

## Daten

`data/` (31 GB: Video, Frames, Masken, Checkpoints, Laufarchive) ist nicht
Teil des Repos und wird mit dem Anlagenband geliefert — siehe
`data/README.md` und `ABGABE/ABGABE_Index.md`.

## Struktur

| Pfad | Inhalt |
|---|---|
| `PA/` | Projektarbeit (Quelle + finale PDFs + Anlagenindex + KI-Anlage) |
| `ABGABE/` | Prüfer-Paket: PDFs, Grafiken, COLMAP-Tests, Panels, E2E-/Autopilot-Nachweise, Fork-Diff |
| `src/`, `tools/`, `docker/` | Pipeline-Code, Auswertung, Container |
| `third_party/SuGaR/` | lokaler mask-aware SuGaR-Fork (Commit-Kette siehe `ABGABE/05_SuGaR-Fork/`) |
| `docs/` | Grafiken, COLMAP-Tests, Agent-Memory |
| `data/` | Rechendaten (nicht im Git, via Cloud/USB) |
