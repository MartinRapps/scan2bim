# Projektarbeit (PA)

Dieser Ordner enthält eine fokussierte, wissenschaftliche Projektarbeit zur
Machbarkeit der Scan-to-BIM-Pipeline. Er ist bewusst **keine vollständige
technische Repository-Dokumentation**. Der Inhalt beschränkt sich auf:

- Problem, Ziel und Forschungs-/Arbeitsfragen;
- notwendige Grundlagen;
- die Pipeline-Idee und die elementaren Datenübergaben;
- den Versuchsaufbau;
- die für die Projektarbeit relevanten COLMAP- und Matrix-Ergebnisse;
- die abgeschlossene zwölfteilige SuGaR-Coarse-Folgematrix mit
  stage-getrennten Grafiken;
- eine vorsichtige Diskussion der Grenzen und des erreichten Funktionsnachweises.

Die Bachelorarbeit mit realen Rohr-/Kabeldaten, GNSS-Referenz und ±10-cm-
Genauigkeitsnachweis bleibt davon getrennt.

## Struktur

- `main.tex`: zentraler LaTeX-Einstieg.
- `sections/02_datengrundlage.tex`: Datensatz, linearer Scope und verfügbare
  beziehungsweise fehlende Referenzen.
- `Zielrahmen.md`: aus dem THWS-PDF abgeleitete Ziel-, Umfangs- und
  Formvorgaben für die Projektarbeit.
- `Arbeitsstand_Langfassung.md`: bestätigte Leitentscheidungen, bereits
  umgesetzte Struktur und verbleibende Nachweise.
- `PA_Aussagenpruefung.md`: quellenbasierter Audit der PA-Aussagen gegen Code,
  Runarchive, README, Memory und Exposé.
- `Archivierungsempfehlung_Matrix.md`: Empfehlung für Pflichtnachweise,
  Golden Runs, kompakte Matrixarchive und eine spätere Wiederholungsmatrix.
- `Struktur_und_Vorgehen_Langfassung.md`: markierte Herkunft jeder
  Strukturentscheidung und konkrete Erstellungsreihenfolge.
- `Vergleich_Kollegenarbeit_und_Fokusfragen.md`: Bewertungsrahmen für die
  Kollegenarbeit und Fragen zur persönlichen Schwerpunktsetzung.
- `Watzke_PA.pdf`: bereitgestellte Vergleichsarbeit des Kommilitonen.
- `references.bib`: BibTeX-Literatur und repository-interne Referenzen.
- `sections/`: fokussierte Kernkapitel.
- `appendices/`: optionale technische Anhänge für COLMAP, Matrix und Reproduktion.
- `figures/`: Quellenverzeichnis für die PA-relevanten Grafiken. Die PDF-Dateien
  werden nicht dupliziert; LaTeX bindet sie direkt aus `../docs/grafiken` ein.
- `results/`: Hinweise auf die archivierten Ergebnisquellen; keine Kopie der
  großen 10-Runs-Daten.
- `docs/grafiken/verwendet_verbessert/`: weiterhin verwendete Statusgrafiken
  und historische gemeinsame Matrixquellen.
- `docs/grafiken/matrix_repeat_2026-08-17/`: aktuelle vollständige Repeat-
  Serie mit STS-/SuGaR-Coarse-Übersichten, Einzelansichtsboxplots, gepaarter
  Delta- und Laufzeitgrafik.
- `docs/grafiken/neu_metriken_2026-08-12/`: historischer Grafikstand; nicht
  mehr die primäre PA-Datenquelle.
- `docs/grafiken/archiv_alt_2026-08-12/`: ältere, nicht mehr eingebundene
  Tabellen- und Grafikstände.
- `build/`: lokales LaTeX-Buildverzeichnis, nicht für Ergebnisse verwenden.

## Kompilieren

Aus dem Repository-Stamm:

```bash
bash PA/build_pa.sh
```

Das erzeugte Dokument liegt anschließend unter `PA/build/pa.pdf`.

Die optionalen Anhänge sind in `main.tex` über `\includeappendicestrue` aktiviert.
Für eine kürzere Fassung kann diese Zeile auf `\includeappendicesfalse` geändert
werden.

Bibliographische Metadaten werden mit `biber` verarbeitet. Die zentrale
Implementierung und die großen Ergebnisarchive bleiben außerhalb dieses Ordners
und werden über Referenzen beziehungsweise relative Grafikpfade eingebunden.

## Wissenschaftliche Abgrenzung

Die Bildmetriken sind ausschließlich objektmaskierte PSNR-, SSIM- und
LPIPS-Werte. Sie sind ein Nachweis der visuellen Rekonstruktionsqualität auf
gehaltenen Ansichten, aber kein geometrischer Genauigkeitsnachweis. Für die
spätere Bachelorarbeit sind Centerline-RMSE, Hausdorff-Distanz und GNSS-
Referenzmessung erforderlich.
