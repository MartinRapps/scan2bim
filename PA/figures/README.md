# PA-Grafiken

Die PA verwendet die zentral archivierten Grafiken aus
`../docs/grafiken/verwendet_verbessert` und
`../docs/grafiken/matrix_repeat_2026-08-17`. Die PDF-Dateien werden nicht in
diesen Ordner kopiert, sondern über `\graphicspath` in `main.tex` aus den
zentralen Quellen eingebunden.
So werden die Grafiken nicht doppelt gepflegt. Für die Arbeit sind insbesondere
relevant:

- `matrix_repeat_2026-08-17/sts_masked_overview.pdf`: getrennte STS-7000-
  Bildmetriken;
- `matrix_repeat_2026-08-17/sugar_coarse_masked_overview.pdf`: ausschließlich
  SuGaR-Coarse-9000-Bildmetriken;
- `matrix_repeat_2026-08-17/*boxplots.pdf`: Einzelansichtsstreuung;
- `matrix_repeat_2026-08-17/sugar_coarse_vs_sts_delta.pdf`: gepaarter
  Rendervergleich;
- Die Matrixstatuswerte stehen weiterhin als Tabelle im Matrixanhang; die
  separate Statusgrafik ist bewusst nicht Bestandteil der PA.

## Screenshot-Panels (`PA/figures/`)

Die aus den historischen Screenshots (`PA/Screenshots/`) generierten Panels
dienen als Entwicklungsnachweise:

- `pa_panel_sts_entwicklung.png` (6 Bilder): STS-Entwicklung und
  Fehlerbefunde — Kapitel Implementierung, Abschnitt "Historische
  Zwischenstände der STS- und Objektfilterungsroute";
- `pa_panel_mesh_filterung.png` (7 Bilder): Meshgewinnung und
  Objektfilterung — ebenda;
- `pa_panel_sugar_iteration.png` (5 Bilder): SuGaR-Coarse-Iterationsstände
  (9001/9200/9000er-Vergleiche) — Kapitel Ergebnisse, Abschnitt
  "Abgeschlossene SuGaR-Coarse-Folgeprüfung";
- `pa_panel_alurohr_endprodukt.png` (2 Bilder): Alurohr-Mesh und Centerline —
  Kapitel Ergebnisse, Abschnitt "Funktionsnachweis der Endstufen".

Die Panels werden durch ein Python-/Pillow-Skript erzeugt; die zugrunde
liegenden Dateinamen dokumentieren Datum und (teils nicht verifizierte)
Zählerstände.
