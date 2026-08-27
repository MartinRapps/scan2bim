# Gesamt-Auswertung der COLMAP-Experimente

## Kurzfazit

Die derzeit beste Einstellung fuer die vorliegenden Aufnahmen ist:

```text
SIMPLE_RADIAL
5 FPS
720p
Plain-SIFT
4096 Merkmale
Sequential Matching
Overlap 15
```

Diese Einstellung erzeugt viele stabile Punkte bei deutlich geringerer
Laufzeit als 1080p oder 20 FPS.

Die getestete DSP-SIFT-Variante mit Guided Matching war in diesem Datensatz
nicht besser. Sie war zwar schneller, erzeugte aber deutlich weniger Punkte
und hatte einen hoeheren Reprojektionsfehler.

---

## Ausgangslage

Das Eingangsvideo besitzt:

- Aufloesung: 1920x1080
- Original-Framerate: 30 FPS
- Dauer: ungefaehr 48 Sekunden
- 5 FPS: 240 Frames
- 10 FPS: 480 Frames
- 20 FPS: 960 Frames

Verwendete Software und Umgebung:

- COLMAP 4.1.1
- FFmpeg 8.1.2
- OpenImageIO
- Faiss-CPU
- Windows PowerShell
- CPU-only-COLMAP
- keine erkannte NVIDIA-CUDA-GPU

Dadurch wurden Sparse-Punktwolken erzeugt. COLMAPs Dense-PatchMatch-
Rekonstruktion ist mit dem installierten CPU-Build nicht moeglich.

Die Pipeline besteht aus:

1. Frame-Extraktion mit FFmpeg
2. SIFT-Merkmalsextraktion
3. Sequential Matching und geometrische Verifikation
4. Sparse-Mapping mit dem inkrementellen COLMAP-Mapper
5. PLY-Export
6. Modellanalyse und TXT-Report

Fuer ein einzelnes Video wird `single_camera=1` verwendet. Das ist auch bei
bewegter Kamera korrekt, solange Kamera und Aufnahmeparameter innerhalb des
Videos gleich bleiben.

---

## Hauptbenchmark

Quelle:

```text
04_benchmark\benchmark_report.txt
```

### Ergebnisse

| FPS | Aufloesung | Bilder | Punkte | Tracks | Beobachtungen/Bild | Reproj. | Laufzeit |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 480p | 240 | 41.363 | 6,44 | 1.110,0 | 0,527 px | 4:22 min |
| 10 | 480p | 480 | 66.868 | 9,57 | 1.333,8 | 0,512 px | 9:58 min |
| 20 | 480p | 960 | 89.072 | 15,44 | 1.432,7 | 0,501 px | 32:32 min |
| 5 | 720p | 240 | 95.651 | 6,70 | 2.671,6 | 0,725 px | 11:08 min |
| 10 | 720p | 480 | 139.899 | 9,94 | 2.896,0 | 0,735 px | 53:51 min |
| 20 | 720p | 960 | 197.042 | 16,42 | 3.370,8 | 0,679 px | 1:37:57 h |
| 5 | 1080p | 240 | 95.216 | 6,48 | 2.571,0 | 0,973 px | 17:10 min |
| 10 | 1080p | 480 | 149.566 | 9,63 | 3.001,4 | 0,962 px | 52:54 min |
| 20 | 1080p | 960 | 201.476 | 15,38 | 3.227,5 | 0,925 px | 2:29:03 h |

Alle vollstaendigen Hauptlaeufe registrierten 100 Prozent der Eingabebilder.

### Aufloesung

Der Vergleich von 720p und 1080p zeigt, dass 1080p fuer dieses Video kaum
mehr Sparse-Punkte liefert:

- 5 FPS/720p: 95.651 Punkte
- 5 FPS/1080p: 95.216 Punkte

Die 1080p-Rekonstruktion benoetigte jedoch 1.030 Sekunden statt 668 Sekunden.
Das sind etwa 54 Prozent mehr Laufzeit ohne erkennbaren Gewinn bei der
Punktanzahl.

Bei 20 FPS ergibt sich ein aehnliches Bild:

- 20 FPS/720p: 197.042 Punkte
- 20 FPS/1080p: 201.476 Punkte

1080p liefert nur etwa 2 Prozent mehr Punkte, benoetigt aber rund 52 Prozent
mehr Zeit.

**Ergebnis:** 720p ist fuer dieses Video deutlich effizienter als 1080p.

### FPS

Bei 480p steigen die Punkte mit der FPS-Zahl:

- 5 FPS: 41.363 Punkte
- 10 FPS: 66.868 Punkte
- 20 FPS: 89.072 Punkte

20 FPS liefert gegenueber 10 FPS etwa 33 Prozent mehr Punkte, benoetigt aber
mehr als die dreifache Laufzeit.

Bei 720p:

- 5 FPS: 95.651 Punkte
- 10 FPS: 139.899 Punkte
- 20 FPS: 197.042 Punkte

Die absolute Punktanzahl steigt deutlich, aber die Punktzahl pro registriertem
Bild sinkt:

- 5 FPS/720p: 399 Punkte pro Bild
- 10 FPS/720p: 291 Punkte pro Bild
- 20 FPS/720p: 205 Punkte pro Bild

Die zusaetzlichen Frames liefern daher nicht proportional neue Geometrie.

### Registrierungsquote

Alle vollstaendigen Hauptlaeufe erreichten 240/240, 480/480 oder 960/960
registrierte Bilder. Die Sequenz ist somit grundsaetzlich gut fuer COLMAP
geeignet. Der wichtigste Unterschied zwischen den Einstellungen ist nicht die
Registrierbarkeit, sondern Punktdichte, Laufzeit und geometrische Stabilitaet.

### Reprojektionsfehler

Der Reprojektionsfehler lag bei allen vollstaendigen Hauptlaeufen unter einem
Pixel. Das ist grundsaetzlich gut.

Der rohe Pixelwert ist zwischen verschiedenen Aufloesungen aber nur begrenzt
vergleichbar. Deshalb wird im Benchmark zusaetzlich der Fehler relativ zur
Bilddiagonale betrachtet.

Ein niedriger Reprojektionsfehler beweist ausserdem nicht automatisch eine
metrisch korrekte Punktwolke. Ein Modell kann trotz niedrigem Fehler falsche,
duplizierte oder unvollstaendige Geometrie enthalten.

---

## 480p-Zusatzbenchmark

Quelle:

```text
04_benchmark_480p_extra\benchmark_report.txt
```

| FPS | Punkte | Tracks | Reproj. | Laufzeit |
|---:|---:|---:|---:|---:|
| 10 | 66.882 | 9,57 | 0,512 px | 619 s |
| 20 | 89.072 | 15,44 | 0,501 px | 1.952 s |

20 FPS verbessert die Punktanzahl um etwa 33 Prozent und die Track-Laenge
deutlich. Dafuer wird mehr als die dreifache Laufzeit benoetigt.

**Bewertung:**

- 10 FPS/480p eignet sich fuer schnelle Vorschauen.
- 20 FPS/480p eignet sich nur, wenn die hoehere Punktzahl die lange Laufzeit
  rechtfertigt.

---

## CRF-Benchmark

Quelle:

```text
05_crf_benchmark\crf_benchmark_report.txt
```

Verglichen wurden das Originalvideo sowie H.264/x264 mit CRF 18, 23, 28 und
35 bei 5 und 10 FPS in 720p.

### CRF bei 5 FPS

| Variante | Videogroesse | Punkte | Punktveraenderung | Gesamtzeit | Zeitveraenderung |
|---|---:|---:|---:|---:|---:|
| Original | 178,20 MB | 95.656 | Referenz | 683 s | Referenz |
| CRF 18 | 51,45 MB | 94.616 | -1,1 % | 706 s | +3,4 % |
| CRF 23 | 25,08 MB | 86.082 | -10,0 % | 1.471 s | +115,3 % |
| CRF 28 | 12,17 MB | 93.703 | -2,0 % | 747 s | +9,3 % |
| CRF 35 | 4,91 MB | 82.103 | -14,2 % | 637 s | -6,8 % |

CRF 18 war praktisch gleichwertig zur Originalquelle.

CRF 28 reduzierte die Videogroesse stark und verlor in diesem Lauf nur etwa
2 Prozent Punkte. Dieses Ergebnis sollte wegen der nicht monotonen Ergebnisse
von CRF 23 und CRF 28 noch mehrfach wiederholt werden.

CRF 35 war schneller, verlor aber rund 14 Prozent Punkte und verschlechterte
den Reprojektionsfehler.

### CRF bei 10 FPS

| Variante | Punkte | Gesamtzeit | Bewertung |
|---|---:|---:|---|
| Original | 150.172 | 2.325 s | Referenz |
| CRF 18 | 150.336 | 2.316 s | praktisch identisch |
| CRF 23 | nur 1.978 | 2.151 s | ungueltig |
| CRF 28 | 150.607 | 2.003 s | sehr interessant |
| CRF 35 | fehlgeschlagen | nicht vorhanden | Datentraeger voll |

Der CRF23/10-FPS-Lauf wurde urspruenglich faelschlich als 100 Prozent
registriert bewertet. Tatsachlich enthielt das Modell nur 5 von 480 Bildern.
Der niedrige Reprojektionsfehler war deshalb nicht aussagekraeftig.

CRF 28/10 FPS ist interessant:

- praktisch gleiche Punktzahl wie das Original
- rund 14 Prozent weniger Gesamtzeit
- deutlich kleinere Videodatei

Dieses Ergebnis muss jedoch mit Wiederholungen bestaetigt werden.

CRF35/10 FPS ist wegen des Fehlers
`database or disk is full` nicht bewertbar.

### CRF-Empfehlung

Fuer eine sichere Einstellung:

```text
CRF 18
```

Fuer einen platzsparenden Versuch:

```text
CRF 28
```

CRF 35 wird fuer die eigentliche Rekonstruktion nicht empfohlen.

---

## SIFT-Varianten A und B

Beide Varianten wurden unter denselben Rahmenbedingungen getestet:

- 5 FPS
- 1280x720
- `SIMPLE_RADIAL`
- 240 Bilder
- Sequential Matching
- Overlap 15

### Variante A: Plain-SIFT mit 4096 Merkmalen

Einstellungen:

```text
SIFT
4096 Merkmale
kein DSP-SIFT
kein Guided Matching
```

Ergebnisse:

| Metrik | Wert |
|---|---:|
| Registrierte Bilder | 240/240 |
| 3D-Punkte | 139.449 |
| Punkte pro Bild | 581 |
| Mittlere Track-Laenge | 6,69 |
| Beobachtungen pro Bild | 3.884,6 |
| Reprojektionsfehler | 0,693 px |
| Laufzeit | 876,2 s |
| PLY-Groesse | 2,09 MB |

### Variante B: DSP-SIFT und Guided Matching

Einstellungen:

```text
2048 Merkmale
DSP-SIFT
affine Formmodellierung
Guided Matching
```

Die Rekonstruktion wurde tatsaechlich erfolgreich erzeugt. Der Wrapper hatte
den Unterprozess nur wegen eines falsch interpretierten PowerShell-Exit-Codes
als fehlgeschlagen markiert.

Korrigierte Ergebnisse:

| Metrik | Wert |
|---|---:|
| Registrierte Bilder | 240/240 |
| 3D-Punkte | 75.339 |
| Punkte pro Bild | 314 |
| Mittlere Track-Laenge | 6,75 |
| Beobachtungen pro Bild | 2.120,0 |
| Reprojektionsfehler | 0,785 px |
| Laufzeit | 721,4 s |
| PLY-Groesse | 1,13 MB |

### Direkter Vergleich A gegen B

Variante A erzeugt:

- rund 85 Prozent mehr 3D-Punkte
- rund 85 Prozent mehr Beobachtungen pro Bild
- etwa 12 Prozent niedrigeren Reprojektionsfehler
- nur rund 21,5 Prozent mehr Laufzeit

Variante B ist:

- etwa 17,7 Prozent schneller
- etwa 46 Prozent kleiner als PLY-Datei
- minimal besser bei der mittleren Track-Laenge
- aber deutlich duennter und weniger vollstaendig

**Fazit:** Variante A ist fuer eine moeglichst vollstaendige Punktwolke klar
besser.

DSP-SIFT und Guided Matching haben mit nur 2048 Merkmalen keinen Vorteil gegen
Plain-SIFT mit 4096 Merkmalen gezeigt. Ein wirklich fairer Zusatztest waere
DSP-SIFT mit ebenfalls 4096 Merkmalen. Aufgrund des hoeheren Speicher- und
Zeitbedarfs ist aber nicht sicher, dass dieser Test den Vorteil ausgleicht.

---

## Bewertung der Qualitaets-Scores

Die Qualitaets-Scores einzelner Reports sind nicht direkt miteinander
vergleichbar.

Wenn ein Report nur einen Lauf enthaelt, wird dieser Lauf automatisch zur
internen Referenz und erhaelt oft den Wert 100.

Fuer Vergleiche sind deshalb wichtiger:

- absolute Punktzahl
- Punkte pro registriertem Bild
- Beobachtungen pro Bild
- mittlere Track-Laenge
- normalisierter Reprojektionsfehler
- Registrierungsquote
- Laufzeit
- Anzahl verbundener Modelle
- Vollstaendigkeit des Modells

Der heuristische Score ist nur innerhalb eines gemeinsamen Reports mit mehreren
vergleichbaren Laeufen sinnvoll.

---

## Wissenschaftliche Einschraenkungen

### Keine Ground Truth

Ohne Referenzscan kann nicht bestimmt werden:

- absolute Positionsgenauigkeit
- tatsaechliche Oberflaechenabweichung
- Massstabstreue
- absolute Vollstaendigkeit
- absolute Punktwolkenqualitaet

Fuer eine belastbare Bewertung waeren beispielsweise erforderlich:

- eine Referenzpunktwolke
- Laserscannerdaten
- ein strukturiertes Referenzmodell
- mehrere bekannte Abstaende oder Messpunkte

Dann koennten folgende Metriken verwendet werden:

- Chamfer-Distanz
- Hausdorff-Distanz
- Precision
- Recall
- F-Score
- Oberflaechenvollstaendigkeit
- absolute Massstabsabweichung

### Unterschiedlicher zeitlicher Match-Overlap

Der aktuelle Matcher verwendet immer `SequentialMatching.overlap=15`.

Das entspricht ungefaehr:

- 5 FPS: 3 Sekunden
- 10 FPS: 1,5 Sekunden
- 20 FPS: 0,75 Sekunden

Die FPS-Vergleiche sind dadurch nicht vollstaendig fair. Bei hoeherem FPS
werden zeitlich viel naehere Bilder gematcht.

Ein fairer Vergleich mit konstantem Zeitfenster waere beispielsweise:

- 5 FPS: Overlap 15
- 10 FPS: Overlap 30
- 20 FPS: Overlap 60

Overlap 60 bei 20 FPS wird allerdings sehr langsam.

### Speicherplatz

Der CRF-Benchmark lief zeitweise in einen fast vollen Datentraeger. Fuer
weitere grosse Testreihen sollten mindestens 20 bis 30 GB freier Speicher
vorhanden sein.

### Reproduzierbarkeit

Der Mapper-Seed ist inzwischen fest auf `42` gesetzt. Aeltere Reports koennen
noch mit der frueheren Konfiguration erzeugt worden sein und sind deshalb nicht
vollstaendig gleich reproduzierbar.

Der Benchmark markiert unvollstaendige Modelle inzwischen als `INCOMPLETE`,
wenn weniger als 90 Prozent der Eingabebilder registriert wurden.

---

## Handlungsempfehlung

### Standard fuer zukuenftige Videos

```text
SIMPLE_RADIAL
5 FPS
720p
Plain-SIFT
4096 Merkmale
Guided Matching aus
DSP-SIFT aus
Sequential Matching
Overlap 15
Mapper-Seed 42
```

### Wenn moeglichst viele Sparse-Punkte benoetigt werden

```text
SIMPLE_RADIAL
10 FPS
720p
Plain-SIFT
4096 Merkmale
```

20 FPS/720p erzeugt zwar mehr Punkte, steht aber nur dann im Verhaeltnis zur
Laufzeit, wenn diese zusaetzlichen Punkte fuer die konkrete Anwendung wirklich
benoetigt werden.

### Wenn Geschwindigkeit wichtiger ist

```text
SIMPLE_RADIAL
5 FPS
480p oder 720p
Plain-SIFT
2048 bis 4096 Merkmale
```

### Empfohlene naechste wissenschaftliche Tests

1. Die Baseline 5 FPS/720p/4096 SIFT dreimal wiederholen.
2. Median und Streuung der Punktzahl, Laufzeit und des Reprojektionsfehlers berechnen.
3. `SIMPLE_RADIAL` gegen `OPENCV` vergleichen.
4. Overlap 15 gegen 30 testen.
5. DSP-SIFT plus Guided Matching mit ebenfalls 4096 Merkmalen testen.
6. JPEG-Qualitaet der Frames getrennt vom H.264-CRF untersuchen.
7. Bewegungsunschaerfe pro Frame messen und schlechte Frames ausschliessen.
8. Eine Referenzpunktwolke oder bekannte Messpunkte aufnehmen.
9. Erst danach LightGlue oder ALIKED als alternative Merkmalsextraktoren testen.

---

## Endgueltige Empfehlung

Nach allen bisher durchgefuehrten Tests ist folgende Konfiguration der beste
praktische Kompromiss:

```text
SIMPLE_RADIAL + 5 FPS + 720p + Plain-SIFT mit 4096 Merkmalen
```

Sie liefert deutlich mehr Geometrie als die DSP-SIFT-Variante, ist wesentlich
schneller als 1080p/20 FPS und registriert die gesamte vorliegende Sequenz
vollstaendig.

Fuer die Kompression ist CRF 18 die sichere Wahl. CRF 28 ist ein interessanter
Speicherplatz-Kompromiss, muss aber durch Wiederholungen und idealerweise einen
Ground-Truth-Vergleich bestaetigt werden.

Metrikbasis und COLMAP-Dokumentation:

- https://colmap.github.io/features.html
- https://colmap.github.io/faq.html
