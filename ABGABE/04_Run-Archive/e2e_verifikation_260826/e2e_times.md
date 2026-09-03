# E2E-Laufzeiten aus matrix.log

Quelle: `data/10_runs/matrix_e2e_verifikation_260826/matrix.log`

| Experiment | Kopf (SAM3+COLMAP+Warp) | STS→Post | Nachlauf (Render/Archiv) | Gesamt (Wall) | Rechenzeit o. Pausen | Pausen >5 min |
|---|---|---|---|---|---|---|
| 5fps / 720p | 07:49 | 32:23 | 00:52* | 40:25 | 40:25 | 30:57 ab 20:16:48 |
| 5fps / qhd | 07:17 | 26:24 | 00:44* | 33:52 | 33:52 | 25:17 ab 20:57:30 |
| 5fps / low | 05:27 | 18:11 | - | 23:46 | 23:46 | 17:30 ab 21:30:11 |

Hinweis: Kopf- und Nachlaufphase nutzen die ersten bzw. letzten Zeitstempel
des Segments; Containerstart-Dauer von wenigen Sekunden ist enthalten.
* = Obergrenze: Nachlaufphase bis zum Folgesegmentbeginn geschätzt
(enthält Cleanup und Folgestart). Pausen ueber 5 Minuten ohne Logaktivitaet
gelten als Maschinen-Idle und werden von der Rechenzeit abgezogen, aber
ausgewiesen. Von ffprobe-Metadaten (creation_time) stammende Datumsangaben
werden ignoriert. Container-Logs (UTC) und Runner-Echos (Lokalzeit) werden
auf eine gemeinsame Zeitzonen-Basis normiert.
