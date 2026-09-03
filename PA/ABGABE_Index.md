# ABGABE_Index.md – Digitaler Anlagenindex (Abgabeordner)

> Diese Datei gehört in die Wurzel des abgegebenen Anlagenordners (ZIP bzw.
> Datenträger). Sie ersetzt den früheren LaTeX-Anhang „Digitaler Anlagenindex“;
> im PDF der PA steht nur noch ein Kurzverweis auf diese Datei.
>
> Stand: 25.08.2026 · Prüfsummen sind vor Abgabe je Ordner zu ergänzen
> (`sha256sum` je Manifest/CSV).

## Strukturvorschlag für den Abgabeordner

```
ABGABE/
├── ABGABE_Index.md                     ← diese Datei
├── pa.pdf                              ← finale PA
├── Anlage_KI-Nutzung.pdf               ← separate KI-Dokumentation
├── 01_Rohdaten/
│   └── Alurohr_THWS.mp4                ← H.264, 1920x1080, 30 FPS, ~48 s
├── 02_COLMAP_Tests/                    ← Rohberichte der Voruntersuchung
│   ├── <lauf>/report.txt, sparse-Statistiken
│   └── colmap_vorstudie.csv
├── 03_Grafiken/
│   ├── matrix_repeat_2026-08-17/       ← sts_masked_*.pdf/csv, sugar_coarse_*.pdf/csv,
│   │                                      per_frame/, metric_vs_runtime.pdf
│   └── verwendet_verbessert/           ← historische gemeinsame CSV-/Methodikquellen
├── 04_Run-Archive/                     ← Auszüge, keine Vollarchive (s. Empfehlung unten)
│   ├── autopilot_720p/                 ← kanonischer Produktionslauf (OPENCV/5FPS/720p/A)
│   ├── autopilot_qhd/  autopilot_low/  ← weitere Autopilot-Vollläufe
│   ├── e2e_verifikation_260826/        ← 3 gemessene E2E-Läufe + e2e_times.csv/md
│   ├── followup_12/                    ← 12 SuGaR-Coarse-Läufe (Manifeste + Metriken + Mesh)
│   ├── matrix_24/                      ← Statusmanifeste der historischen Batches
│   └── qualitaetsvergleich_20260818/   ← Golden-Run-Arm 5fps/720p/opencv_a (+ weitere Arme nach Bedarf)
├── 05_SuGaR-Fork/
│   ├── sugar_fork_diff_48bbfdd_a0fc37b.diff
│   └── FORK_README.md                  ← Commit-Kette 48bbfdd → a0fc37b
└── 06_Panels/                          ← pa_panel_*.png in Auflösung der PDF-Version
```

## Zu jedem Eintrag: Herkunft und Zweck

| Bereich | Inhalt und Zweck | Nachweis |
|---|---|---|
| `01_Rohdaten/` | Eingangsvideo; keine metrisch validierte GNSS-Referenzkurve | Datei + Medieneigenschaften |
| `02_COLMAP_Tests/` | Sparse-SfM-Voruntersuchungen; begründet Plain-SIFT 4096 ohne Guided Matching | Berichte je Lauf |
| `03_Grafiken/` | Getrennte STS-/SuGaR-Coarse-Auswertungen, Boxplots, Delta-, Laufzeitgrafik; CSV-Quellen | PDF-Grafiken + CSV |
| `04_Run-Archive/` | Manifeste (`manifest.json`, `parameters.json`, `run.log`, `run.md`), Metriken (`sts_masked.json`, `sugar_coarse_masked.json`), Meshes, Centerlines | je Lauf-Ordner |
| `05_SuGaR-Fork/` | Fork-Diff ab 48bbfdd bis a0fc37b (= `SUGAR_REF` = Parent-Gitlink) | Diff-Datei |
| `06_Panels/` | Historische Entwicklungs- und Endprodukt-Panels aus der PA | PNG |

## Empfehlung: Welche vollständigen Läufe abgeben? (S.28-Rückfrage)

**Mindestumfang (konsistent mit dem Text der PA):**

1. **Kanonischer Produktionslauf** – Autopilot-Vollauf `Alurohr_THWS.mp4`,
   OPENCV / 5 FPS / 720p / Route A (mit Centerline-Nachweis 85/372 Punkte).
2. **Autopilot-Volläufe der übrigen Stufen** – qHD und low (belegt
   Erfolgskriterium 6 über alle drei Auflösungsstufen).
3. **Golden-Run-Arm** `matrix_qualitaetsvergleich_20260818/5fps/720p/opencv_a`
   – Produktionskonfiguration im Matrixverbund, failed=0.
4. **SuGaR-Folgematrix `matrix_sugar_followup_12`** – alle zwölf Läufe
   (Manifeste + Metriken + Coarse-Mesh); belegt die Vergleichsroute vollständig.
5. **E2E-Verifikationsbatch `matrix_e2e_verifikation_260826`** – drei
   gemessene Gesamtlaufzeiten (720p 40:25, qHD 33:52, low 23:46 min) mit
   Phasenaufteilung; Quelle der Laufzeitangaben in Kapitel 4/5 und Tabelle
   `e2e_times.csv`/`e2e_times.md`.

**Optional, wenn Speicherplatz erlaubt:**

6. Ein Arm je weiterer Auflösung aus dem Qualitätsvergleichsbatch
   (`qhd/opencv_a`, `low/opencv_a`) für den gepaarten Vergleich innerhalb der
   Auflösungen.
7. Vierfeld-Ablation-Artefakte (A–D) inklusive Seed-42-Manifeste.

**Nicht mehr abgeben:** Der frühere Smoke-Lauf
`matrix_smoke_low_pipe_full` existiert nicht mehr im Archivbestand und ist im
Text auch nicht mehr referenziert.

## Projektimplementierung (GitHub)

Die vollständige Projektimplementierung (Pipeline-Orchestrierung `run_pipeline.sh`,
`src/`, `tools/`, Containerdefinitionen, SuGaR-Fork als Submodul) ist im
GitHub-Repository abgelegt:

- **URL:** <https://github.com/MartinRapps/scan2bim>
- **Branch:** `main`
- **Commit-Stand dieser Abgabe:** `2eb124fee9113441e96aeacfd9c48a5e2f0ad2b0` (finaler Abgabe-Stand, Fassung 08.09.2026 — inkl. Korrektur-Commits)
- **SuGaR-Fork-Commit:** `a0fc37b` (siehe `05_SuGaR-Fork/`, dort auch das
  vollständige Diff zur Vanilla-Basis `48bbfdd`)

Der im Anlagenband enthaltene Pflichtnachweis (Manifeste, Parameter, Logs,
Metriken) entspricht genau diesem Commit-Stand; die Replays sind über die im
Repository enthaltenen Skripte reproduzierbar. Falls das Repository zum
Abgabezeitpunkt privat ist, ist hier den Zugang für die Prüfer zu dokumentieren.

## Umgesetzter Stand

Der Ordner `ABGABE/` ist nach dieser Struktur befüllt:

| Ordner | Inhalt | Prüfsummen |
|---|---|---|
| `/` | `ABGABE_Index.md`, `pa.pdf` (Arbeitsfassung, 63 S. inkl. Erklärung + PlagAware-Einwilligung), `pa_anonym.pdf` (ohne Name/Matrikel — Fallback, falls die PlagAware-Einwilligung nicht erteilt wird; Fußnote 13 PABA), `Anlage_KI-Nutzung.pdf` + `.tex`, `Korrekturbericht_ProfPersona.md` + `Korrektur_Persona_und_Plan.md` (Prüfer-Simulation, siehe KI-Anlage) | – |
| `01_Rohdaten/` | `Alurohr_THWS.mp4` (H.264, 1920×1080, 30 FPS) | ✓ |
| `02_COLMAP_Tests/` | Rohberichte der Voruntersuchung | ✓ |
| `03_Grafiken/` | `matrix_repeat_2026-08-17/` (inkl. korrekt gelabelter `metric_vs_runtime.pdf`) + `verwendet_verbessert/` | ✓ |
| `04_Run-Archive/e2e_verifikation_260826/` | Pflichtnachweis aller drei Läufe (Manifeste, Parameter, run.md/log, matrix.log, Metriken, eval_frames, Coverage-Reports) + `e2e_times.csv`/`.md` + Batch-Prüfsummen | ✓ |
| `04_Run-Archive/autopilot_laeufe/` | `run.md`/`run.log` der archivierten Autopilot-Läufe | ✓ |
| `04_Run-Archive/followup_12/` | vollständige `sugar_output`-Ordner der zwölf Folgematrix-Läufe (inkl. interner Refined-Mesh-Extraktion; Bewertung laut PA nur Coarse-Stufe — siehe README im Ordner) | ✓ |
| `04_Run-Archive/golden_run_720p_opencv_a/` | **vollständiger** Arm aus `matrix_qualitaetsvergleich_20260818` (3,1 GB, inkl. live/) | ✓ |
| `04_Run-Archive/sugar_vergleichsarm_720p/` | **vollständiger** SuGaR-Coarse-Vergleichslauf `opencv_sugar` (3,4 GB) | ✓ |
| `05_SuGaR-Fork/` | `sugar_fork_diff_48bbfdd_a0fc37b.diff` + `FORK_README.md` (Commit-Kette) | ✓ |
| `06_Panels/` | `pa_panel_*.png` | ✓ |

Historische Batches (`matrix_full_pipe`, `matrix_rest`,
`matrix_sugar_followup_12`, `matrix_repeat_20260812`) liegen nicht mehr im
Live-Archivbestand; ihre Metrik-/Statusnachweise sind über die
Grafikquellen-CSVs in `03_Grafiken/` und die komprimierten externen Backups
abgedeckt. Die Vierfeld-Ablation-Meshes (Position 7) liegen ebenfalls im
komprimierten Band; Parameter und Seed sind in der PA dokumentiert.

## Abgabe-Hinweis (PABA 3.7)

Die Arbeit ist **zweifach in digitaler Form** an Betreuer sowie Erst- und
Zweitprüfer abzugeben (i. d. R. Cloud-Download). Die PlagAware-Einwilligung
liegt unterschriftsbereit als Seite III in `pa.pdf` bei; damit ist eine
anonymisierte Fassung laut Fußnote 13 nicht erforderlich — `pa_anonym.pdf`
liegt dennoch als Fallback bereit.

## Offene Pflichten vor Abgabe

- [x] Prüfsummen je Archivordner ergänzen (`SHA256SUMS.txt` je Ordner)
- [x] Tatsächliche Ordnerstruktur gegen diese Datei abgleichen
- [x] `pa.pdf` mit finalen Angaben (Deckblatt, fixes Datum) neu gebaut und ersetzt
- [x] Externes Backup der komprimierten historischen Batches auf externem Datenträger dokumentiert
