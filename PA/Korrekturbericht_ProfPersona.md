# Korrekturbericht — Prüfer-Simulation (Prof-Persona)

> **Persona:** Professor, Geovisualisierung/Geoinformatik; CV-Grundlagen
> vertraut, keine Segmentierungs-Spezialität; keine Vorkenntnis der Arbeit.
> **Material:** ausschließlich der Ordner `ABGABE/` (Stand: 27.08.2026) und der
> dort genannte GitHub-Link. **Rahmen:** siehe
> `Korrektur_Persona_und_Plan.md` (Terminologie-Policy, Ledger, Schweregrade).
>
> **Kurzlegende:** 🔴 Blocker · 🟠 Fehler · 🟡 Unklar · ⚪ Style/Formales
> Notizzettel-Nummern fortlaufend (N1, N2, …).

---

## Phase 1 — Ordnerstruktur-Review

### Erwartung vor der Sichtung

Von einer Abgabe eines Geo-Informatikers erwarte ich auf der Wurzel: eine
Index-/Lesedatei, die mir als Einstieg dient; die Arbeit selbst als PDF; die
KI-Dokumentation als separate Anlage; darunter nummerierte, selbsterklärende
Anlagenordner (Rohdaten, Auswertungen, Run-Archive, Quellcode-Nachweise) und
Prüfsummen, damit ich Datenintegrität nachvollziehen kann. Dateinamen sollten
ohne Leerzeichen/Umlaute auskommen und einer nachvollziehbaren Konvention
folgen.

### Beobachtung

Wurzel: `ABGABE_Index.md`, `pa.pdf`, `Anlage_KI-Nutzung.pdf` (+ `.tex`),
Ordner `01_Rohdaten` bis `06_Panels`. Größen: Video 179 MB; Run-Archive
6,5 GB (davon zwei vollständige Läufe ~3,1/3,4 GB); Grafiken 1,8 MB;
Panels 2 MB. Jeder Anlagenordner enthält eine `SHA256SUMS.txt`. Die Ordner
folgen dem im Index beschriebenen Schema; Struktur und Index passen
auf den ersten Blick zusammen.

### Bewertung (Struktur-Impression)

Solide und durchdacht: Ich weiß ohne Anleitung, wo ich anfangen muss. Zwei
Dinge fallen bei genauerem Hinsehen heraus: Build-Artefakte in einem Grafikordner
und ein ungewöhnlicher Namensmix. Tendenz Struktur: **gut (2)**.

### Notizzettel

| # | Schwere | Fund |
|---|---|---|
| N1 | 🟡 | `03_Grafiken/matrix_repeat_2026-08-17/` enthält LaTeX-Build-Artefakte (`.aux`, `.log`, `.tex` neben den `.pdf`). Arbeitsdateien im Abgabepaket wirken unaufgeräumt; für die Lesbarkeit der Grafiken brauchen ich nur PDF + CSV. |
| N2 | 🟡 | `02_COLMAP_Tests/`: Dateinamen tragen das Präfix `06_variant_A_…`, obwohl der Ordner `02` heißt — wirkt wie aus einer anderen Struktur kopiert. Zudem liegen PowerShell-Skripte (`benchmark_colmap.ps1`, `benchmark_crf.ps1`) im Datenordner, ohne dass der Index ihren Zweck nennt. |
| N3 | ⚪ | Ordner-/Dateinamen mischen Deutsch und Englisch (`01_Rohdaten` vs. `06_Panels`, `sugar_vergleichsarm_720p` vs. `golden_run_720p_opencv_a`). Verständlich, aber inkonsistent. |
| N4 | ⚪ | Keine Prüfsummen für die Wurzel-Dateien (`pa.pdf`, `Anlage_KI-Nutzung.pdf`) — nur die Unterordner haben `SHA256SUMS.txt`. Für ein 6,5-GB-Paket wäre eine Gesamtprüfsumme der Kernartefakte erwartbar. |
| N5 | ⚪ | `golden_run_720p_opencv_a/` und `sugar_vergleichsarm_720p/` enthalten je ein `input_5fps.mp4` (~35 MB) — Redundanz zu `01_Rohdaten/Alurohr_THWS.mp4`. Verständlich (laufkomplett), nur erwähnenswert. |
| N6 | 🟡 | `04_Run-Archive/autopilot_laeufe/` enthält **14** Laufordner. Erinnere ich in der PA an „sechs Autopilot-Volläufe“? → Merker für die Kapitelprüfung (Ledger V1). |
| N7 | ⚪ | `04_Run-Archive/golden_run_720p_opencv_a/live/` — internes Arbeitsverzeichnis mit vielen technischen Unterordnern, keine README im Ordner. Der Index sagt „vollständiger Arm“, mehr Führung gibt es nicht. Prüfen in Phase 4, ob die PA den Aufbau erklärt. |

### Ledger-Initialisierung

**Begriffs-Ledger:** (leer — füllt sich ab Phase 2)

**Versprechen-Ledger:**
- **V1:** PA sagt laut Merker N6 vermutlich „sechs archivierte
  Autopilot-Volläufe“ — Paket enthält 14 `Alurohr_THWS_*`-Ordner. In der
  Kapitelprüfung (7.1 bzw. 6.3) abgleichen: Warum 14? Welche sind gemeint?
- **V2:** PA referenziert laut Index historische Batches
  (`matrix_sugar_followup_12`, `matrix_repeat_20260812`), die **nicht** im
  Paket liegen — nur Grafik-CSVs verweisen auf ihre Pfade. Prüfen: Sagt die
  PA, wo diese Nachweise auffindbar sind?

---

## Phase 2 — Root-Ebene

### 2.1 `ABGABE_Index.md`

**Erwartung:** Ein Einstiegsdokument, das mir in fünf Minuten sagt: Was ist was,
wo finde ich was, wie stelle ich Integrität fest, was ist der Stand der Dinge.
**Beobachtung:** Struktur, Inhalts-Tabelle, Empfehlungen und der Abschnitt
„Umgesetzter Stand" erfüllen das. Prüfsummen-Stichprobe: `03_Grafiken` 34/34 OK,
`e2e_verifikation_260826` 44/44 OK — Integrität ist tatsächlich nachprüfbar.
Offene Checkboxen sind ehrlich formuliert (pa.pdf final, externes Backup).
**Abweichungen:**
- 🟡 **N12:** Index sagt „pa.pdf (= Arbeitsfassung, **60 S.**)" — das beiliegende
  PDF hat **62 Seiten**. Klein, aber genau das nervt einen Prüfer beim Gegenprüfen.
- ⚪ **N4 (folgt):** Root-Dateien ohne Prüfsumme (siehe Phase 1).

### 2.2 `Anlage_KI-Nutzung.pdf`

**Erwartung:** Werkzeuge, Zeitraum, Einsatzbereiche, Beispiel-Prompts,
Eigenständigkeitserklärung; deckungsgleich mit dem, was die PA selbst zur KI sagt.
**Beobachtung:** Alles vorhanden; Bereiche mit Prompts, Modellliste, Prüfhinweise.
Deckblatt enthält ebenfalls die Klammer-Platzhalter. Signaturenzeile offen
(druckbedingt akzeptabel).
**Abweichungen:**
- 🔴 **N8:** Deckblatt-Platzhalter in eckigen Klammern (`[Martin Rapps]`,
  `[6323014]`, `[08.09.2026]`) — so ist die Anlage nicht einreichbar.
  Betrifft identisch das `pa.pdf`-Deckblatt. **Abgabeblocker.**
- ⚪ **N14:** Datum auf dem Titelblatt ist das Build-Datum („27. August 2026"),
  nicht das Abgabedatum — `\today`-Effekt, zusammen mit N8 zu fixen.

### 2.3 `pa.pdf` — Formalien und Verzeichnisse

**Erwartung:** Deckblatt nach Hochschulmuster, Erklärung, Kurzfassung (vor dem
Inhaltsverzeichnis, mit Aussagekraft), TOC mit max. 3–4 Ebenen, Abb.-/Tab.-
Verzeichnis (>3 Abbildungen), saubere Numerierung.

**Beobachtung:** Aufbau folgt der Erwartung: Deckblatt (I), Erklärung (II),
Kurzfassung (III), TOC (IV–VI), Abbildungs- und Tabellenverzeichnis, dann
arabische Zählung ab Kapitel 1. TOC-Tiefe: zwei Ebenen — gut. Anhang A–G und
Literatur im TOC. `??`-Scan: **0** Treffer — keine kaputten Referenzen. PDF
technisch sauber (Fonts eingebettet, Text extrahierbar, 62 S.).

Die **Kurzfassung** enthält inzwischen konkrete Ergebnisse (240/240 registriert,
29,62 dB objektmaskiert PSNR, Produktionskonfiguration) — das ist stark und
erfüllt die Erwartung „wesentliche Ergebnisse in der Kurzfassung".

**Abweichungen:**
- 🟡 **N9:** Die Kurzfassung trägt zwei Überschriften übereinander: „Kurzfassung"
  (Kapitelüberschrift) und direkt darunter „Zusammenfassung" (abstract-Umgebung).
  Wirkt unfertig; eins von beiden reicht.
- 🟠 **N10:** Kurzfassung: „die sechs Autopilot-Volläufe … sind … archiviert".
  Das Paket enthält **14** `Alurohr_THWS_*`-Laufordner (vier vom 18.08., zwei vom
  20.08., acht vom 26.08.). Entweder Zahl oder Sammelbegriff anpassen — so
  stimmt die Kurzfassung nicht mit der Anlage überein. *(V1 aufgelöst —
  Inkonsistenz bestätigt.)*
- 🟡 **N11:** Kurzfassung: „alle zwölf SuGaR-Coarse-Folgeläufe … sind mit
  Manifeststatus success archiviert" — aber **wo**? Im Paket liegen die zwölf
  Läufe nicht; nur der SuGaR-Vergleichsarm 720p und die Grafik-CSVs. Der
  Prüfer fragt: „Zeig's mir." → bleibt offen bis Kapitel 7.8 *(V2 aktiv)*.
- 🟠 **N15:** Einleitung 1.2: „…angepasste Maskenlogik: **Dilatation und Erosion**
  sowie die promptbasierte Auswahl …" — das widerspricht Kapitel 3.1/5.1
  („verbindlich: default unverändert, middle erodiert, small zweifach erodiert,
  **ohne Dilatation**"; Dilatation nur historisch). Merker für die
  Kapitel-1-Wertung; Widerspruch wird bei 3.1 formalisiert.
- 🟡 **N13:** Die PA enthält die Anhänge F (Anlagenindex) und G (KI-Nutzung) —
  parallel dazu `ABGABE_Index.md` und die separate `Anlage_KI-Nutzung.pdf`.
  Doppelführung ist erklärbar (Kurzverweis vs. Vollfassung), muss aber
  konsistent bleiben; G und separate Anlage überlappen inhaltlich.

### Ledger-Stand nach Phase 2

**Begriffe neu eingeführt (Auswahl):** Scan-to-BIM, SAM 3.1, COLMAP, STS
(Segment-then-Splat), SuGaR, Route A (in 1.2 noch unbenannt — siehe
Kapitel-1-Prüfung), Datenverträge, Eval-Split, objektmaskierte Metriken,
Centerline, B-Spline. Bisher plausibel eingeführt; Kurzfassung nutzt Begriffe
vorab, was üblich ist.

**Versprechen:** V1 ✅ bestätigt als Inkonsistenz (N10). V2 offen (7.8).
Neu: **V3** (aus 1.2): „Dilatation und Erosion" vs. Kapitel 3.1/5.1 — Klärung
bei Kapitel 3. **V4** (aus TOC): Anhang B heißt „Matrix-Status und
Auswertungsregeln" — erwartet Statusübersicht der 24 Läufe + Auswertungsregeln.

### Zwischenbewertung Root-Ebene

Inhaltlich deutlich stärker als die Formalien: Zahlen sind da, Ergebnisse sind
da, Struktur stimmt. Die Formalien (N8 🔴, N9, N12, N14) sind schnell fixbar,
müssen aber VOR Abgabe raus. **Tendenz Root/Anlagen: gut (2)**, mit Abgabeblocker.

---

## Phase 3 — Kapitel 1: Einleitung (S. 7–8)

**Erwartung (vor Lektüre):** Motivation des Problems, Aufgabenstellung/Ziel,
Mehrwert, Abgrenzung zur Bachelorarbeit, Leseführung durch die Arbeit;
Forschungsfragen wären ein Plus.

**Beobachtung 1.1 (Motivation):** Kompakt: dünne lineare Objekte, drei
Teilprobleme (Kamerastabilität, konsistente Segmentierung, nutzbare
3D-Repräsentation), kontrollierter Labordatensatz, BA-Ausblick. Für mich als
Geo-Prof ohne Segmentierungshintergrund nachvollziehbar. ✅

**Beobachtung 1.2 (Zielsetzung und Eigenbeitrag):** Ziel klar
(Machbarkeitsnachweis Video → Centerline), die ±10-cm-Abgrenzung ist ehrlich
und zeigt, dass die Arbeit ihre eigene Grenze kennt. Der Eigenbeitrag wird
konkret benannt (Integration, Domänentrennung, Datenverträge, Maskenlogik,
automatisierte Tests). ✅

**Beobachtung 1.3 (Forschungsfragen):** Vier präzise, beantwortbare Fragen.
✅ — mit zwei Begriffs-Anmerkungen: F3 nennt „Original-STS-GS-**Route A**",
ohne dass die Namensgebung bis hierhin erschlossen wurde (warum „A"?
Vergleichsroute heißt „SuGaR-Coarse", nicht „Route B"?) — 🟡 Mini, wird in
3.4 aufgelöst, ich notiere es. F4 nennt CLI/Replay/Autopilot/Matrixrunner —
Begriffe hier noch unerklärt, in einer Fragestellung aber zulässig. ⚪

**Beobachtung 1.4 (Abgrenzung und Aufbau):** Die Abgrenzung ist vorbildlich
deutlich (was NICHT Gegenstand ist). Aber der Titel verspricht „…**und
Aufbau**" — ein Leseführungs-Absatz („Kapitel 2 klärt die Datengrundlage,
Kapitel 3 …") **fehlt vollständig**. 🟡 **N16** — der Leser tappt ohne
Kapitelführung durch die Arbeit; das TOC allein ersetzt das nicht.

**Notizzettel Kapitel 1:**
- 🟡 **N15 (Verdacht, Bestätigung in Kap. 3):** 1.2 nennt als Eigenbeitrag
  „angepasste Maskenlogik: **Dilatation und Erosion** …" — eine Segmentierungs-
  Einführung ist das hier nicht, und ich erinnere mich an nichts, was
  „Dilatation" bis hierhin erklärt. Prüfen, ob das zu den Grundlagen passt.
- 🟡 **N16:** Fehlender Aufbau-Absatz trotz Kapiteltitel „Abgrenzung und
  Aufbau".

**Kapiteltendenz Einleitung: gut (2).** Motivation, Ziel, Fragen und
Abgrenzung sitzen; die Leseführung fehlt, und eine Maskenlogik-Formulierung
ist zu prüfen.

**Wissensstand nach Kapitel 1:** Ich weiß, WAS die Arbeit will
(Machbarkeit Video→Centerline an einem Alu-Rohr) und was sie NICHT will
(±10 cm, reale Trasse, Web-UI). Ich weiß NOCH NICHT: wie die Pipeline
technisch aufgebaut ist, was STS/SuGaR intern tun, wo die Daten herkommen
und wie „Route A" zu ihrem Namen kommt. Alle vier Forschungsfragen sind offen
— korrekt für eine Einleitung.

---

## Phase 3 — Kapitel 2: Datengrundlage und Anwendungsrahmen (S. 8–10)

**Erwartung (vor Lektüre):** Welches Eingabematerial (Video: Quelle, Format,
Länge, Aufnahmekonfiguration), warum dieser Testdatensatz statt realer Trassen,
was der Scope der Nachverarbeitung ist, und wo die Aussagegrenzen liegen
(keine GNSS-Referenz → keine absolute Genauigkeit).

**Beobachtung 2.1:** Alu-Rohr als kontrollierter Labordatensatz; klare
Aussage, dass es kein maßstäblicher Kabel-Ersatz ist. ✅

**Beobachtung 2.2:** Aufnahmekonfiguration ungewöhnlich doku­mentiert —
Smartphone (Pixel 8 Pro, Hauptkamera), OpenCamera, fester Belichtung,
1920×1080, Auto-Level aus, mit Hersteller- und App-Quellen belegt
(Google 2026; Open Camera Project 2026). Dass die Arbeit die Ehrlichkeit
wahrt („kein Rohsensordatensatz", Stabilisierungszustand nicht nachweisbar),
ist überdurchschnittlich sauber. ✅

**Ledger:** Neu und korrekt eingeführt: Eval-Split-Kontext, 5-/2-FPS-Profile,
Auflösungsvarianten (2.1), „Medialflächen" (2.3, mit Fußnote erklärt ✅),
Translation-Fallback (2.4). Der Begriff **„sparse point cloud"** bleibt
erwartungsgemäß englisch — konsistent mit der Terminologie-Policy. ✅

**Beobachtung 2.2 (Fortsetzung):** Die Datei-Eigenschaften (H.264, 1920×1080,
nominal 30 FPS, 1441 Bilder, ~48 s) sind im Text zugesagt. Verifikation:
Container-Länge per Metadaten **48,01 s** ✅; Codec/Auflösung/Framezahl
erfordern den Docker-Container (Vermerk, Phase 4/Stichprobe). 🟡 **N17:**
Der Dateiname bricht im PDF unschön um („…Alurohr_TH / WS.mp4") — Zeile „WS.mp4"
beginnt isoliert. ⚪ **N18:** Anführungszeichen um „unverfälschtes Video" sind
englisch gesetzt (``…''), im Übrigen Text wird die csquotes-Konvention genutzt —
inkonsistent. 🟠 **N19:** Die Arbeit nennt sich im Fließtext selbst „**die
PA**" (fünf Fundstellen: 2.2, 2.3, 2.4, 6.x zweimal). In einer Abgabe heißt es
„die vorliegende Arbeit/Projektarbeit" — „die PA" ist Teamjargon und fällt
einem Prüfer negativ auf.

**Beobachtung 2.3 (Scope):** Klare Begrenzung auf ein Einzelobjekt;
„Medialflächen" bekommt eine mustergültige Fußnote (genau richtig für einen
Nicht-Segmentierer). Produkt-Hierarchie (Centerline+B-Spline primär, Gaussians/
Mesh wichtig, Masken/COLMAP Zwischenprodukt, GeoJSON als Fallback nicht global
genau) ist präzise. ⚪ Die „ESRI-Suite" taucht spontan auf — für Geo-Leser
verstehbar, ohne Einführung tolerierbar.

**Beobachtung 2.4 (Referenzlage):** Vorbildliche Ehrlichkeit: keine GNSS-
Referenz, GCP-Dateien „Approximationen der Wirklichkeit" (nur Transformationstest),
Translation-Fallback mit klarer Definition dessen, was er NICHT prüft. ✅

### Kapitel-2-Wertung

Inhaltlich sehr stark: Datengrundlage, Ehrlichkeit der Grenzen und
Produktabgrenzung sind besser als bei vielen Bachelorarbeiten. Die Formale
(N17 Selbstbezeichnung, N18 Zitatzeichen, N19 Zeilenumbruch) ziehen ab.
**Tendenz Kapitel 2: sehr gut bis gut (1–2).**

**Wissensstand nach Kapitel 2:** Ich kenne das Eingabematerial (Video +
Aufnahmeparameter + Profile), den Scope (Einzelobjekt, Centerline+B-Spline als
Produkte) und die Aussagegrenzen (keine GNSS, Fallback deklariert). Ich weiß
NOCH NICHT: wie Segmentierung/SfM/Splatting technisch zusammenspielen und was
„Route A" ist. Genau richtig für Kapitel 3.

---

## Phase 3 — Kapitel 3: Technische und methodische Grundlagen (S. 4–9)

**Erwartung (vor Lektüre):** Nur die Verfahren einführen, die für Verständnis
und Bewertung nötig (Zielrahmen §2.3): Segmentierung, SfM/Kameramodelle,
Gaussian Splatting, Meshrouten, Centerline, Bildmetriken. Kein Lehrbuchcharakter.
Als CV-Leser kenne ich SfM, Kameramodelle, PSNR/SSIM — ich muss hier primär die
segmentierungsnahen Teile erklärt bekommen.

**Beobachtung 3.1 (Segmentierung):** Promptbarkeit verständlich motiviert.
Die Maskenhierarchie ist sauber definiert (default unverändert, middle 5×5-
Erosion, small zweifach) mit Begründung der 5×5-Wahl. **Bestätigung V3/N15:**
„in der aktuellen Projektfassung wird **keine Dilatation** angewendet; historisch
war die default-Maske zwischenzeitlich dilatiert" — im Widerspruch zu 1.2
(„Eigenbeitrag … **Dilatation und Erosion**"). 🟠 **N15 formalisiert:** Die
Einleitung beschreibt die Maskenlogik falsch bzw. in einem veralteten Stand;
entweder 1.2 auf „Erosionshierarchie" korrigieren oder die historische
Dilatation dort weglassen.

**Beobachtung 3.2 (SfM/Kameramodelle):** Für mich als CV-Leser stimmig:
PINHOLE/SIMPLE_RADIAL/OPENCV korrekt charakterisiert; die Erläuterung, warum
mehr Freiheitsgrade nicht automatisch besser sind (schlechte Konditionierung →
Overfitting auf Rauschen), ist fachlich korrekt und ehrlich. „sparse
3D-Punktwolke" englisch — policy-konform. 🟡 **N20:** Der Code-Bezeichner
bricht mitten im Wort um: „ImageReader.si / ngle_camera=1" — schlecht lesbar,
Bezeichner sollte ununterbrochen gesetzt werden.

**Beobachtung 3.3 (3DGS/STS):** Maskenrollen sauber je Komponente getrennt
(STS: Zuordnung+Supervision; middle: Coverage/Eval-Split; SuGaR-Verlustpfade
bewusst an 3.4 delegiert) — Verweis funktioniert. ✅

**Formel-Check (alle Formeln des Kapitels):**
- (1) Σi = Ri·Si·Si⊤·Ri⊤ — korrekte Standard-Zerlegung, die auch die
  Positiv-Definitheit sicherstellt. ✅
- (2) Sigmoid αi = 1/(1+exp(−oi)) — korrekt; die Begründung, warum über den
  Logit statt über α gefiltert wird, ist nachvollziehbar. ✅
- (3) Maskierter Loss ℓM = ΣM·ℓ / (ΣM+ε) — korrekt normiert, ε-Schutz
  erklärt. ✅
- (4) B-Spline C(u) = Σ Ni,p·Pi — Standardformel für geklemmte uniforme
  Splines; Grad 10 als rein algorithmischer Glättungsparameter deklariert —
  ehrlich. ✅
- (5) MSE_M = 1/(3N_M)·Σ‖I−Î‖² — kanalweise Mittelung korrekt (Faktor 3),
  Summation nur über Maske. ✅
- (6) PSNR_M = 10·log10(1/MSE_M) — korrekt bei Maximalwert 1. ✅
Alle Symbole sind im Text aufgelöst; keine nicht definierten Größen. **Der
Formel-Check ergibt keine Beanstandung** — selten genug.

**Beobachtung 3.6 (Metriken):** Hervorhebenswert: Die SSIM-Randpixel-
Problematik wird **quantifiziert** („rund fünf Randpixel bei 40 px Rohrbreite
(720p) → ~12 % Randanteil; bei 20 px (low) → ~25 %"). Genau so macht man eine
Grafik für einen Nicht-Segmentierer interpretierbar — ohne Segmentierungs-
Vorwissen nachvollziehbar. ✅ Die PLY/PT-Erklärung (CloudCompare, SuperSplat)
hilft mir als Prüfer tatsächlich bei der Archivsichtung.

**Notizzettel Kapitel 3:**
- 🟠 **N15 (formalisiert, siehe oben):** Widerspruch 1.2 ↔ 3.1 zur Dilatation.
- 🟡 **N20:** Umbruch im Bezeichner `ImageReader.single_camera=1`.

**Kapiteltendenz Grundlagen: sehr gut (1).** Formeln korrekt und vollständig
aufgelöst, Ehrlichkeit an den kritischen Stellen (keine Kalibrierung, Grad 10
nur Glättung), Nicht-Segmentierer werden gezielt mitgenommen. Nur N20 ist
rein technisch.

**Wissensstand nach Kapitel 3:** Ich verstehe jetzt, wie Maskenhierarchie,
Kameramodelle, Splatting, Objektfilterung, Mesh-Extraktion und Metriken
zusammenhängen — und ich weiß, dass „Route A" die Abweichung vom SuGaR-
Standardweg ist. Offen für mich: die Gesamtarchitektur (Container, Datenflüsse)
— das verspricht Kapitel 4, und dort steht auch die erste Abbildung.

---

## Phase 3 — Kapitel 4: Konzept und Pipeline-Idee (S. 10–13)

**Erwartung (vor Lektüre):** Die Idee hinter dem Aufbau (warum diese
Architektur?), ein Datenfluss-Diagramm, die zentrale Designentscheidung
(hier: Domänentrennung), Meshrouten-Begründung, Ausführungsformen und der
Georeferenzierungs-Endpunkt. Erste Abbildung der Arbeit sollte den Datenfluss
zeigen.

**Beobachtung 4.1 (Leitprinzip, Abbildung 1):** Die 7-Schritt-Aufzählung und
die Abbildung erzählen dieselbe Geschichte — konsistent. Die Abbildung ist
sauber: keine Überlappungen, Container farblich getrennt, der GCP-Zweig als
optional und „PA-seitig nicht validiert" markiert, Caption präzise. Für einen
Nicht-Segmentierer lesbar, weil die Knoten Fachbegriffe nur mit already
eingeführten Begriffen verwenden. 🟡 **N21:** Die Abbildung beschriftet
Container A, B, C und E — ein **„Container D" fehlt als Label**. Der SuGaR-
Knoten („SuGaR-Coarse-Vergleich, mask-aware Fork") ist inhaltlich vorhanden,
aber unbeschriftet; Kapitel 5.1 spricht jedoch durchgängig von „fünf
Containern" (A–E, Tabelle 5.1: D = SuGaR-Fork). Ein Leser zählt im Bild A, B,
C, E und sucht D. Fix: SuGaR-Knoten als „Container D" beschriften.

**Beobachtung 4.2 (Domänentrennung):** Die Kernidee (SfM/GCP im Originalraum,
STS/SuGaR in der idealen Domäne; Undistorter wendet das gelöste Modell an statt
ein neues zu schätzen) ist präzise und für CV-Leser ohne Segmentierungs-
Spezialwissen verständlich. Die Nachweis-Aussage deckt Matrix-, Replay- und
Inline-Pfad ab und stimmt mit dem Verhalten der Skripte überein (Warp +
Coverage-Prüfung, Replay-Regeln je Startstufe). ✅ 🟡 **N22 (gleiche Klasse wie
N20):** Pfad bricht um: „data/03_mask / s_ideal" — unschöner Bruch in einem
Kernpfad des Datenvertrags.

**Beobachtung 4.3 (Semantische Objektkette):** Wichtige Grenzaussage sauber:
„mehrfache Nutzung der Masken ≠ geometrische Garantie". ✅

**Beobachtung 4.4 (Routen):** Trennung Gaussian-Geometrie vs. Mesh-Extraktion
klar; „das Mesh ist ein abgeleitetes Produkt; die Gaussian-Wolke bleibt die
primäre geometrische Hypothese" ist die zentrale, gut formulierte
Designentscheidung. ✅

**Beobachtung 4.5 (Ausführungsformen):** Preset mit **gemessenen**
Gesamtlaufzeiten (40/34/24 min inkl. SAM/COLMAP/Render/Archiv), Autopilot-
Verhalten (nur Preset+Prompt), SAM3-Breite preset-gekoppelt (720p→1280 etc.),
Diagnoseprofil colmap-stop mit Warp-Garantie und Replay-Fortsetzung — alles
deckungsgleich mit dem Skriptstand (Verifikation gegen `run_pipeline.sh`/
`pipeline_lib.sh` erfüllt). ✅

**Beobachtung 4.6 (Georeferenzierung):** Fallback-Mechanik und Suffix
`_fallback_georeferenced` klar; „nicht als Genauigkeitsnachweis" konsistent
mit 2.4. ✅

**Notizzettel Kapitel 4:**
- 🟡 **N21:** Container-D-Label fehlt in Abbildung 1 (fünf Container im Text,
  vier beschriftete im Bild).
- 🟡 **N22:** Pfadbruch „data/03_mask s_ideal" (gleiche Klasse wie N20 —
  zusammen fixen: `\path`-Umbruchstellen oder kürzere Formulierung).

**Kapiteltendenz Konzept: sehr gut (1).** Die Kernidee ist herausgearbeitet,
alle Designaussagen sind im Skript verifizierbar, die Abbildung trägt. Abzüge
nur formaler Natur (N21/N22).

**Wissensstand nach Kapitel 4:** Ich kenne die Architektur inkl. Domänen-
trennung und deren Begründung, die Ausführungsformen mit echten Laufzeiten und
den Georeferenzierungs-Vertrag. Offen: konkrete Implementierung (Container,
Codeänderungen) — Kapitel 5; und ob die behaupteten Nachweise (Matrix-, Smoke-,
Replaypfad) tatsächlich archiviert sind — die Stichproben kommen in Phase 4.

---

## Phase 3 — Kapitel 5: Implementierung (S. 13–22)

**Erwartung (vor Lektüre):** Konkrete Umsetzung der in Kapitel 4 versprochenen
Architektur: Container/Tabellen, Codeänderungen (Fork), Begründung der
Datenablagen, CLI-Verhalten, Quality-Gates, und die Brücke zu den Panels
(historische Fehlerbelege).

**Beobachtung 5.1:** Containertabelle (A–E) präzise; UID/GID- und Bind-Mount-
Erklärung mit Fußnote auch für Nicht-Infrastruktur-Leser verständlich. ✅
Aber: Siehe N21 — Tabelle nennt Container D, die Abbildung 1 nicht.

**Beobachtung 5.2 (Fork-Tabelle):** Änderungen je Commit dokumentiert
(48bbfdd bis eca4ea1) — nachvollziehbar, im Paket über den Fork-Diff (Anlage
05) gegenprüfbar. ✅

**Beobachtung 5.3 (Ablagen-Tabelle):** Beantwortet genau die Frage, die ich
als Prüfer beim ersten Blick in `data/` gehabt hätte („warum liegt alles
mehrfach?"). Die Zusatz-Ehrlichkeit („in allen Läufen dieser Arbeit war der
erste Prompt bereits erfolgreich; die Fallback-Kette greifte nie") ist
stark. 🟠 **N15 (dritte Fundstelle):** Die Hierarchie-Zeile der Tabelle 3
schreibt „…plus morphologische Ableitungen **(Dilatation und Erosion)**" —
wieder im Widerspruch zu 3.1 („keine Dilatation"). Die Widerspruchsstellen
sind jetzt: 1.2, 5.3-Tabelle (falsch) vs. 3.1/5.1 (korrekt). Systematische
Korrektur nötig. 🟡 **N23 (erweitert):** Auch Tabellenpfade brechen unschön
(`data/04_sfm/undist orted/…`, `data/03_masks/_att empts/…`).

**Beobachtung 5.4 (CLI/Autopilot):** Deckungsgleich mit dem Skript
(Verifikation gegen `run_pipeline.sh`): Autopilot-Defaults, Preset-Reihenfolge,
qHD/low-Vorbesetzung. ✅

**Beobachtung 5.7 (Panels, Abbildungen 2 und 3):** Beide Panels als Bild
gesichtet. Konzept (Fehlerbelege als Entwicklungsnachweis) ist legitim, die
Teilbild-Erzählung im Text ist konkret. Aber zwei wesentliche Punkte:
- 🟡 **N26:** Die Panels zeigen **nicht das Alu-Rohr** — erkennbar eine
  Pflanze im Korb, ein Kran, Fisch-artige Meshes vor blauem Hintergrund
  (Vorgängerobjekte der Entwicklung). Weder Caption noch Text sagen das. Für
  einen Prüfer, der gerade Kapitel 2 („Testdatensatz = Alurohr") gelesen hat,
  ist die Diskrepanz verwirrend: „Zeigt mir das Panel meine Testdaten?"
  Fix: halber Satz in der Caption („Belege aus der Entwicklung an
  Vorgängerobjekten").
- 🟡 **N27:** Die Teilbild-4-Aussage („Zielzähler 15.000, DN-Consistency
  bewusst deaktiviert") ist im Text ohne Nachweislage-Marker; die Panel-Labels
  sind in Druckgröße nicht lesbar, eine Zählerstände-Tabelle (wie in der
  Hauptfassung vorhanden) gibt es in dieser Fassung nicht. Empfehlung:
  „laut Entwicklungsnotizen" ergänzen oder die Zählerstands-Tabelle
  nachziehen.

**Beobachtung 5.8 (Metrik-Dateien):** Die Drei-Dateien-Aufschlüsselung
(sts_masked / sugar_coarse_masked / sugar_refined_masked) ist eine der
stärksten Stellen für die Nachvollziehbarkeit — inklusive der ehrlichen
Aussage, dass sugar_refined in allen Läufen „skipped" ist. 🟠 **N24:** Das
JSON-Beispiel war im PDF **zeichenverstümmelt** („{ßtatus:ßkipped…",
`rreason:nno`): Ursache ist die babel-NGerman-Shorthand `"` („s → ß",
„r/„n → Umbruch-Hints), die innerhalb von \texttt zuschlägt. Root Cause
identifiziert und **behoben** (Lösung: \string"-Expansion; visuell im
neuen Build verifiziert: `{"status":"skipped","reason":"no refined.ply
exported"}` erscheint korrekt). Der Fix muss in die finale Fassung.
⚪ N25 (prozessual): Das im Paket enthaltene `pa.pdf` stammt von einem Stand
VOR dieser Korrektur (DN-Präzisierung aus Kapitel-5.7-Fix fehlt) — das ist
erwartet (Index-Checkbox „pa.pdf vor Abgabe neu bauen"), muss aber zwingend
vor Abgabe gezogen werden.

**Beobachtung 5.9–5.11:** refined.obj-Kompatibilitätsname ehrlich entzaubert
(„bedeutet ausdrücklich nicht, dass ein Refinement ausgeführt wurde") ✅;
Centerline-Parameter konsistent mit Kapitel 3.5 ✅; Robustheits-Tabelle 4
dupliziert nicht, sondern fasst zusammen und verweist auf die Chronologie im
Anhang ✅.

**Notizzettel Kapitel 5:** N15 (3. Fundstelle) · N20/N22/N23 (Umbruchklasse,
jetzt auch in Tabelle 3) · N24 (behoben, Fix dokumentieren) · N26 (Objekt-
Kontext der Panels) · N27 (Nachweislage Teilbild 4) · N25 (pa.pdf alt).

**Kapiteltendenz Implementierung: gut (2).** Inhaltlich die dichteste und
prüfbarste Stelle der Arbeit (Skript-Verifikation vollständig positiv); die
Mängel sind der systematische Dilatations-Widerspruch, das Zeichenproblem
(behoben) und die Panel-Kontextlücke.

**Wissensstand nach Kapitel 5:** Ich kann die Implementierung nachbauen und
die Behauptungen gegen das Paket prüfen. Offen: die Versuchsergebnisse selbst
(Kapitel 6/7) — und die Frage aus der Kurzfassung, wo die zwölf Folgeläufe
nachweisbar sind (V2).

---

## Phase 3 — Kapitel 6: Versuchsaufbau (S. 22–25)

**Erwartung (vor Lektüre):** Testdesign so vollständig, dass ich die Versuche
reproduzieren könnte: konstante vs. varierte Parameter, Versuchsreihen-Überblick,
Ablationslogik, Evaluationsprotokoll, Erfolgskriterien.

**Beobachtung 6.1:** Tabelle 5 ist exakt das, was ich erwarten würde — und sie
enthält die KORREKTE Masken-Zeile („RGB default, DN middle, **keine zusätzliche
Dilatation**") plus den ehrlichen Vereinheitlichungs-Absatz („historisch war
die default-Maske dilatiert; verbindlich gilt …"). Damit ist der Widerspruch
N15 endgültig lokalisiert: **Tabelle 5 und 3.1 sind korrekt; falsch stehen
1.2 und die Tabelle-3-Zeile (5.3).** Zahlen in Tabelle 5 mit Tausenderpunkten
(200.000 / 5.000.000) — konsistent. ✅ Die Trennung middle-Coverage vs.
default-Metrik mit `mask_level=default`-Dokumentation im JSON ist sauber. ✅

**Beobachtung 6.2 (COLMAP-Voruntersuchung):** Verweist auf die Volltabelle im
Anhang — 🟠 **N28:** Die Referenz lautet im PDF „steht in **Anhang 9**". Die
Anhänge heißen A–G; „9" ist die Tabellennummer der COLMAP-Tabelle, weil im
Quelltext `\ref{tab:colmap-vorstudie}` hinter dem Wort „Anhang" steht.
Referenztyp falsch; korrekt wäre „Tabelle 9 im Anhang A".

**Beobachtung 6.3 (Autopilot/Produktionslauf):** Kanonischer Produktionslauf
definiert (OPENCV/5FPS/720p/Route A, „als Autopilot-Vollauf archiviert") +
„Daneben existieren archivierte Autopilot-Volläufe für die übrigen
Auflösungsstufen". Verträglich mit dem Paket (14 Laufordner: 720p/qhd/low +
Entwicklungsstände) — aber die Kurzfassung (N10) sagt „sechs". Bleibt als
N10 bestehen.

**Beobachtung 6.4 (Matrix):** 🟠 **N17 (verschärft, zweite Ursache):** „Insgesamt
umfasst **die PA** drei Versuchsreihen" — sechste „die PA"-Stelle. Inhaltlich:
Die drei Reihen werden namentlich genannt (`matrix_full_pipe`, `matrix_rest`,
`matrix_sugar_followup_12`) — **diese Archive liegen nicht im Paket**; ihre
Metrik-/Statusnachweise sind nur über die CSVs in `03_Grafiken/` erreichbar.
Das ist durch den Index (externes Backup) gedeckt, aber der Satz in 6.4
verspricht „Detailtabellen in den Anhängen" — Anhang B muss das einlösen
(V2/V4-Prüfung in Phase 4).

**Beobachtung 6.5/6.6:** Vierfeld-Definition sauber (konstante Faktoren
aufgezählt), Diamond-Fußnote von Kapitelanfang trägt hier ✅. 6.6 mit der
ehrlichen Einschränkung („nur Coarse-Route, kein refined.ply") und dem
DN-Nachtragssatz — konsistent mit 3.1/5.1. ✅

**Notizzettel Kapitel 6:**
- 🟠 **N28:** „Anhang 9" — falscher Referenztyp (Tabellennummer statt
  Anhangsbuchstabe).
- 🟠 **N17 (zählt jetzt 6 Fundstellen):** „die PA"-Selbstbezeichnung auch
  in 6.4.
- 🟡 (V2-Verstärkung) 6.4 nennt die drei historischen Batches namentlich und
  verspricht „Detailtabellen in den Anhängen" — Einlösung in Anhang B prüfen;
  im Paket existieren die Batch-Archive selbst nicht (nur CSV-Nachweise).

**Kapiteltendenz Versuchsaufbau: sehr gut (1).** Tabelle 5 ist die beste
Einzel-Tabelle der Arbeit; Reproduzierbarkeit wäre bei mir als Prüfer ohne
Rückfrage gegeben. Abzüge nur für N28 und die Selbstbezeichnung.

**Wissensstand nach Kapitel 6:** Ich weiß genau, welche Versuche es gibt, mit
welchen Konstanten, und woran „erfolgreich" gemessen wird. Offen: die
Ergebnisse (7) und die Einlösung der Tabellen-/Anhangsversprechen (Anhang B).

---

## Phase 3 — Kapitel 7: Ergebnisse (S. 26–40)

**Erwartung (vor Lektüre):** Darstellung der Versuchsergebnisse nach den in
Kapitel 6 definierten Reihen: End-to-End-Kette, Auflösungsvergleich,
COLMAP-Voruntersuchung, Metriken je Modellstufe, Produktionsentscheidung,
Vierfeld-Ablation, Folgematrix, Endstufen-Nachweis, negative Ergebnisse. Jede
Zahl muss gegen die beiliegenden CSVs/Archive prüfbar sein.

**Zahlenverifikation (Stichproben gegen Paket-CSVs):**
| PA-Aussage | Paketquelle | Ergebnis |
|---|---|---|
| OPENCV 720p/5FPS: 29,62 dB / 0,902 / 0,117 | sts_masked_summary.csv | ✅ exakt |
| SIMPLE_RADIAL 720p/5FPS: 29,43 / 0,897 / 0,122 | dito | ✅ exakt |
| Sugar-720p-Mittelwerte (6 Kombinationen, Anhang-B-Tabelle) | sugar_coarse_masked_summary.csv | ✅ alle 6 exakt |
| Beispiel 5FPS/720p SR: Sugar 21,22 / 0,778 / 0,151 | dito | ✅ exakt |
| E2E 40:25 / 33:52 / 23:46 | e2e_times.csv | ✅ exakt |
| 87 Rohpunkte / 380 B-Spline-Punkte | golden_run centerline CSVs | ❌ **85 / 372** (N29) |

Die Metrik-/Laufzeit-Verifikation bestand **vollständig**; nur die
Centerline-Zahlen weichen ab.

**Beobachtungen im Einzelnen:**

- **7.1:** ⚪ Der „hier genügt die Erinnerung…"-Satz steht noch im Paket-PDF
  (in der aktuellen Arbeitsfassung bereits korrigiert → Beleg für N25, das
  Paket-PDF ist veraltet). 🟡 N10 erneut: „Autopilotnachweis … über **sechs**
  archivierte Autopilot-Volläufe" vs. 14 Ordner im Paket.
- **7.2:** Konsequent als „visueller Befund" markiert, keine Überinterpretation
  (Punktwolken-Beobachtung explizit als Hypothese entzaubert). ✅
- **7.3:** 🟠 **N28 (erneut):** „die vollständige Tabelle steht in **Anhang 9**".
  Die inhaltliche Erklärung (warum Guided Matching den Reprojektionsfehler
  erhöht) ist fachlich sauber. ✅
- **7.4 (Abbildungen 4–8 gesichtet):** Farblogik korrekt (SR blau, OPENCV
  orange, PINHOLE grau; 5/2 FPS Intensität). 🟡 **N30:** Der Untertitel der
  STS-Overview enthielt den Copy-Paste-Rest „Laufzeit = vollständiger
  archivierter Pipeline-Lauf", obwohl die Grafik keine Laufzeit zeigt —
  **während der Prüfung behoben** (Untertitel → „Werte aus sts_masked.json,
  Pool: vollständige Original-GS-Läufe"; PDF neu gebaut, Paketkopie erneuert,
  Prüfsummen aktualisiert). Trennung der Modellstufen konsequent; globales
  Ranking über Auflösungen explizit vermieden. ✅ 🟡 N17 (7. Fundstelle):
  „Für die PA werden daher…".
- **7.5:** Produktionsentscheidung mit Verifikation gegen CSV ✅; Sparse-Analyse
  (240 Bilder, 133.723 Punkte, 0,706 px) ohne externe Prüfmöglichkeit im Paket
  (Werte plausibel, Herkunft „nachträgliche Analyse" — Repo-Nachweis).
  Reprojektions-Relativierung („kein absoluter Schwellenwert für ‚gute
  Anpassung'") — fachlich korrekt und angenehm uneitel. ✅
- **7.6 (E2E-Tabelle):** ✅ exakt wie e2e_times.csv; Nachlauf als Obergrenze
  gekennzeichnet.
- **7.7 (Vierfeld):** Provenienzsatz vorhanden („Ablationsmeshes liegen im
  komprimierten Archivband; deterministisch reproduzierbar bei
  Checkpoint-Vorliegen") — deckt die fehlenden Mesh-Dateien ehrlich ab. ✅
- **7.8 (Folgematrix):** 🟠 **N31:** „…sind für diese zwölf Konfigurationen
  archiviert" — aber weder PA noch Paket liefern die zwölf Archive: Der
  ABGABE_Index listet sie als Mindestumfang Position 4, der Ordner
  `04_Run-Archive/followup_12/` fehlt jedoch im Paket. Das Rohmaterial
  existiert (Coarse-Meshes/Outputs unter dem SuGaR-Submodul-Ablagepfad) —
  Empfehlung: Pflichtnachweis + Coarse-Meshes nachträglich in
  `04_Run-Archive/followup_12/` kopieren. Bis dahin ist „archiviert" für den
  Paket-Prüfer nicht einlösbar (V2 weiter offen, jetzt präzisiert).
- **7.9 (Endstufen):** 🟠 **N29:** „87 Rohpunkte / 380 Ausgabepunkte" stammen
  vom ursprünglichen Kanonischen Lauf, dessen CSVs **nicht** im Paket sind;
  der beiliegende Golden Run liefert 85/372. Entweder Zahlen auf den
  paketierten Lauf umstellen (85/372, mit Run-ID) oder die Original-CSVs in
  `autopilot_laeufe/` ergänzen. Die Centerline-CSVs im Golden Run sind
  übrigens vollständig auffindbar (raw + lokal + fallback) ✅.
- **7.10:** Kompakt, verweist auf Tabelle im Anhang D. ✅

**Kapiteltendenz Ergebnisse: gut (1–2).** Die Zahlenbasis ist ungewöhnlich
solide (fast alle Stichproben exakt bestätigt), Grafiken korrekt kodiert und
ehrlich beschriftet; die Mängel sind die 87/380-Zahldifferenz (N29), die
fehlenden Folgematrix-Archive (N31) und die Zähl-/Formalienreste (N10, N28).

**Wissensstand nach Kapitel 7:** Alle vier Forschungsfragen sind aus meiner
Sicht mit Daten beantwortet; ich konnte fast jede Zahl selbst gegen die
beiliegenden Dateien prüfen. Was mir fehlt: die zwölf Folgematrix-Archive
(N31) und die Original-CSVs zum kanonischen Lauf (N29).

---

## Phase 3 — Kapitel 8: Diskussion und Grenzen (S. 41–44)

**Erwartung (vor Lektüre):** Kritische Reflexion der eigenen Ergebnisse,
Grenzen der Aussagekraft, Einordnung der Kameramodell-/Auflösungseffekte,
Autopilot/Batch-Realismus, Laufzeit-Einordnung und die BA-Brücke.

**Beobachtung 8.1/8.2:** Gate-/Warp-Behauptungen decken sich mit dem
Skriptverhalten (Inline+Matrix+Warp, Replay-Regeln je Startstufe) ✅.
„Masken sind keine geometrische Referenz" — saubere Grenzziehung. ✅

**Beobachtung 8.3:** 🟠 **N32:** „Ein Pixel im 720p-Bild entspricht in der
realen Welt nur **wenigen Millimetern**, während ein Pixel in Low einen
deutlich größeren realen Lagefehler darstellt." Das ist eine **metrische
Bodenauflösungs-Aussage (GSD) ohne jede Aufnahmegeometrie** — Objektgröße,
Kameraabstand: nirgends angegeben. Sie widerspricht der eigenen Enthaltsamkeit
(2.4: keine Maßreferenz; 3.5: Voxelgröße „relative, keine metrische Größe").
Der argumentative Punkt (720p ist für BIM die bessere Wahl) trägt auch ohne
die mm-Behauptung; Formulierung relativieren („deutlich kleinere
Objektdetailgröße pro Pixel") oder als grobe Schätzung mit Herleitung
kennzeichnen. 🟡 **N33:** Der Folgeabsatz wiederholt Tiefpass-Argument und
„keine globale Rangliste" fast wörtlich aus demselben Unterkapitel — Redundanz.

**Beobachtung 8.4:** Delta-Grafik korrekt als Rendervergleich entzaubert.
⚪ **N34:** „stringent schlechter" — falscher Anglizismus im Deutschen
(gemeint: „durchgängig/konsequent"). 

**Beobachtung 8.5:** „Nutzerseitige Autonomie ist durch archivierte
Autopilot-Volläufe belegt" — ohne Zahl, verträglich mit dem Paket. ✅
Usability-Ehrlichkeit („keine formale Messung") ✅.

**Beobachtung 8.6:** LPIPS-Ranking-Klärung („Natur der Metrik, keine Inversion
der Daten") gut; E2E-Verweis auf 7.6 konsistent. ✅

**Beobachtung 8.7:** Scheitelachse-vs-Centerline-Diskussion und die bewusste
Netzwerk-Abgrenzung — präzise. ✅

**Beobachtung 8.8 (Fragen):** Alle vier Fragen werden datengestützt
beantwortet; Antwort 2 jetzt mit Maskenstabilität als Gegenpol. ✅
🟡 Antwort 4 nennt erneut „**sechs** archivierte Volläufe" (N10-Familie).

**Kapiteltendenz Diskussion: sehr gut bis gut (1–2).** Reflexionsqualität und
Grenzen-Transparenz auf hohem Niveau; N32 ist der einzige inhaltliche
Angriffspunkt (metrische Aussage ohne Basis), N33 Redundanz, N34 Sprache.

---

## Phase 3 — Kapitel 9: Fazit und Ausblick (S. 44–45)

**Erwartung:** Erreichte Ziele kompakt, Produktionsentscheidung, offene
BA-Schritte — keine neuen claims.

**Beobachtung:** Deckungsgleich mit dem Nachweisstand (Inline-Warp „durch die
archivierten Autopilot-Vollläufe nachgewiesen" — verträglich mit dem Paket).
Keine neuen unbelegten Aussagen; die COLMAP-Kalibrierungs-Einschränkung wird
wiederholt. ✅
- ⚪ **N35:** Die Fazit-Aufzählung „Interaktiver CLI-Betrieb, Autopilot und
  Matrixrunner" vergisst den **Replay**-Modus, obwohl 1.3-F4 alle vier
  Ausführungsformen verspricht.
- 🟠 N17 (letzte Fundstelle): „Die in **dieser PA** aufgebaute Struktur…"
  — Selbstbezeichnung nun 7+ mal im Text.

**Kapiteltendenz Fazit: sehr gut (1).** Kurz, ehrlich, ohne neue Anmaßung;
nur N35/N17-Formalia.

**Wissensstand nach Kapitel 9:** Die Arbeit hat ihre vier Fragen aus meiner
Sicht beantwortet; die BA-Brücke ist konkret. Ich verbleibe mit offenen
Paketwork-Fragen (V2/N29/N31), die die Anhänge und Phase 4 klären müssen.

---

## Phase 4 — Anhänge und Archiv-Stichproben

- **Anhang A (COLMAP):** Tabelle 9 vorhanden, Zahlen in DE-Notation (0,693
  Pixel) ✅; Paketverweis „02_COLMAP_Tests/" erfüllt ✅. Zitat COLMAP
  (Schönberger u. a. 2026) vorhanden ✅.
- **Anhang B (Matrix-Status):** Tabelle 10 (6/18/24, 16 erfolgreich) ✅;
  Auswertungsregeln ✅; followup_12 als „Ergebnistabellen im Haupttext (7.8)"
  + Zitat Rapps 2026a ✅. V4 eingelöst; die ARCHIVE selbst fehlen weiterhin
  (N31).
- **Anhang C (Querformat):** Layout sauber (eigene Kopfzeile funktioniert,
  2×3-Raster lesbar, Zoom-Zeile vorhanden). ⚪ Kontrast der Punktwolken
  dünn, aber Zoom hilft.
- **Anhang D (Fehlerchronologie):** Tabelle 11 löst die Verweise aus 5.11/7.10
  auf ✅. 🟠 **N36:** Anhang D verweist auf „PA/Screenshots/" — dieser Pfad
  existiert im Anlagenband nicht (dort: `06_Panels/` mit den 4 Panel-PNGs;
  Einzeldateien nur im Repository). Positiv: Anhang D nennt die
  Vorgängerobjekte (Sonnenbrillen/Gestell) — die Erklärung, die den Panels in
  Kapitel 5 fehlt (N26), existiert also, nur zu spät im Dokument.
- **Anhang E (Reproduzierbarkeit):** Fork-Kette „eca4ea1/a0fc37b" + Diff-Datei
  (im Paket vorhanden ✅) + Laufmanifest-Verweis auf ABGABE_Index.md ✅.
- **Anhang F (Anlagenindex):** 🟡 **N37:** Nutzt Repository-Pfade
  (`PA/figures/`, `data/10_runs/`, `PA/Screenshots/`) ohne Zuordnung zu den
  Paketordnernamen (`06_Panels/`, `04_Run-Archive/`) — ein Paket-Leser kann
  die Brücke nicht ohne Index-Rätsel ziehen.
- **Anhang G (KI-Nutzung):** deckungsgleich mit der separaten Anlage
  (Werkzeuge, Zeitraum, Modellliste) ✅.
- **Archiv-Stichprobe Golden Run:** manifest.json (success/opencv_a/720p) ✅;
  sts_masked.json mit 30 Eval-Frames und per_frame-Werten ✅; Centerline-CSVs
  (raw 85 / lokal 372 Zeilen) ✅ auffindbar.
- **Video:** Containerlänge 48,01 s ✅; Codec/Auflösung/Framezahl über
  Container-ffprobe nachprüfbar (Host ohne ffprobe — Vermerk).

## Phase 5 — Konsolidierung

### 5.1 Notizzettel-Register (nach Schwere)

**🔴 Blocker (1):** N8 Deckblatt-Platzhalter in pa.pdf und KI-Anlage
([Name]/[Matrikel]/[Datum]) + Build-Datum statt Abgabedatum (N14).

**🟠 Fehler (6):**
| # | Fund | Fix |
|---|---|---|
| N10 | „sechs Autopilot-Volläufe" (Kurzfassung, 7.1, 8.8) vs. 14 Ordner im Paket | Zahl korrigieren (14) oder sammelnd formulieren („archivierte Autopilot-Volläufe der Entwicklungs- und Verifikationsläufe") |
| N15 | „Dilatation und Erosion" in 1.2 und Tabelle 3 vs. verbindlich „ohne Dilatation" (3.1/5.1/6.1) | Beide Stellen auf Erosionshierarchie umstellen |
| N17 | „die PA" als Selbstbezeichnung, 7+ Stellen | „die vorliegende Arbeit/Projektarbeit" |
| N28 | „Anhang 9" (6.2 und 7.3) | „Tabelle 9 im Anhang A" |
| N29 | 87/380 vs. 85/372 im beiliegenden Golden Run | Zahlen auf den paketierten Lauf umstellen (+Run-ID) oder Original-CSVs nachliefern |
| N31 | followup_12 im Index als Mindestumfang Position 4 versprochen, Ordner fehlt | Pflichtnachweis + Coarse-Meshes aus dem Submodul-Ablagepfad nach `04_Run-Archive/followup_12/` kopieren, Index-Zeile ergänzen |

**🟡 Unklar (12):** N1 Build-Artefakte im Grafikordner · N2 COLMAP-Ordner-
Präfixe/PowerShell-Skripte · N6 14-vs-6-Frage (Teil von N10) · N7 live/-Führung ·
N9 Doppel-Überschrift Kurzfassung/Zusammenfassung · N11/N31 Archivlage
followup · N12 Index-Seitenzahl 60→62 · N13 Doppelstruktur Anhänge F/G vs.
separate Anlage/Index · N16 fehlender Aufbau-Absatz (oder Titelanpassung) ·
N20/N22/N23 Pfad-/Bezeichner-Umbrüche (4 Stellen) · N26 Panel-Objektkontext
in Caption vorziehen (Anhang D hat die Info) · N27 Teilbild-4-Nachweislage ·
N32 GSD-Millimeter-Aussage relativieren · N33 8.3-Redundanz · N36/N37
Paketpfad-Zuordnung in Anhang D/F.

**⚪ Style:** N3 Namensmix · N4 Root-Prüfsummen · N5 mp4-Duplikate · N18
Zitatzeichen · N19 Zeilenumbruch Dateiname · N34 „stringent" · N35 Replay im
Fazit ergänzen · ESRI-Suite ohne Einführung.

### 5.2 Versprechen-Ledger (Abgleich)

| ID | Ankündigung | Einlösung |
|---|---|---|
| V1 | Autopilot-Nachweis | ✅ durch N10 ersetzt: Nachweis existiert, nur Zählung inkonsistent |
| V2 | Nachweisfolge followup_12 | 🟠 offen: Grafiken/CSV ja, Archive nein (N31) |
| V3 | Maskenlogik-Definition | ✅ Klärung in 3.1/6.1; Rest: N15 an 2 Stellen |
| V4 | „Detailtabellen in den Anhängen" | ✅ Anhang A (Tabelle 9) + B (Tabelle 10/Regeln) |
| V5 | Anhang C visualisiert alle drei Auflösungen | ✅ (Querformat geprüft) |
| V6 | Fork-Diff im Anlagenband | ✅ 05_SuGaR-Fork/ |
| V7 | „finale Laufmanifest" (Anhang E) | ✅ ABGABE_Index.md enthält Repo/Commit-Abschnitt |
| — | Abbildung 1 „fünf Container" | 🟡 N21: Container-D-Label fehlt im Bild |
| — | 7.1 End-to-End-Kette „visuell dokumentiert" | ✅ Anhang C |
| — | 2.2 Videoeigenschaften | ✅ 48,01 s verifiziert; Codec/Framezahl via Container prüfbar |

### 5.3 Literatur-Audit

- Rapps 2026a/2026b: **zitiert** (Anhang B bzw. F) ✅ — keine \nocite-Leichen
  in der Arbeitsfassung.
- Kirillov/Meta AI, Schönberger (SfM + COLMAP-Anhang), Kerbl, Lu, Guédon,
  Kazhdan, DGtal, Wang, Zhang, Google, Open Camera: alle im Text zitiert ✅.
- Internetquellen mit „besucht am"-Datum ✅. Alphabetische Ordnung ✅.
- Einziges Minus: scan2bimImplementation notiert „lokaler Entwicklungsstand" —
  mit dem neuen ABGABE_Index-Abschnitt (Commit-Stand) ist das abgedeckt;
  GitHub-Link im Verzeichnis vorhanden ✅.

### 5.4 Kapitelnoten-Spiegel (Persona)

| Kapitel | Tendenz |
|---|---|
| Struktur/Anlagen | gut (2) |
| 1 Einleitung | gut (2) |
| 2 Datengrundlage | sehr gut bis gut (1–2) |
| 3 Grundlagen | **sehr gut (1)** |
| 4 Konzept | **sehr gut (1)** |
| 5 Implementierung | gut (2) |
| 6 Versuchsaufbau | **sehr gut (1)** |
| 7 Ergebnisse | gut (1–2) |
| 8 Diskussion | sehr gut bis gut (1–2) |
| 9 Fazit | **sehr gut (1)** |

### 5.5 Gesamteindruck (Persona, nach Zielrahmen-Kriterien)

Die Arbeit erfüllt den Zielrahmen in den kernigen Punkten über dem
Erwartungsniveau einer Projektarbeit: problemgerechte Methodenwahl und
-begründung (Kap. 3–6), enge Kopplung jeder Aussage an prüfbare Artefakte,
konsequente Ehrlichkeit bei Grenzen (keine ±10 cm, keine Kalibrierung, kein
Genauigkeitsnachweis), negative Ergebnisse als Teil der Argumentation und ein
Anlagenband, dessen Zahlen sich tatsächlich gegenprüfen lassen — die
Stichprobenverifikation der Metrik- und Laufzeitwerte bestand vollständig.
Schwächen: Der Haupttext liegt mit 62 Seiten über dem Richtwert, Formales
(Platzhalter-Deckblatt, Selbstbezeichnung „die PA", Doppelüberschrift
Kurzfassung) wirkt unfertig, drei textliche Widersprüche (Dilatation,
Autopilot-Zahl, 87/380) sind untrivial, und die Panels nutzen
Vorgängerobjekte ohne Kontextangabe.

**Gesamttendenz der Persona: sehr gut bis gut (1–2)** — mit der klaren
Auflage, N8 (Platzhalter) und die fünf 🟠-Punkte vor Abgabe zu beheben; danach
ist aus meiner Sicht nichts, was die Note im Kern belasten würde.

### 5.6 Vor-Abgabe-Fixliste (in dieser Reihenfolge)

1. 🔴 Deckblatt: Platzhalter + fixes Datum (pa.pdf **und** KI-Anlage), beide
   neu bauen, `ABGABE/pa.pdf` ersetzen, Index-Seitenzahl 60→62 (N8/N14/N12/N25).
2. 🟠 N15: 1.2 + Tabelle-3-Zeile auf Erosionshierarchie umstellen.
3. 🟠 N10: „sechs" → 14 bzw. Sammelbegriff (Kurzfassung, 7.1, 8.8).
4. 🟠 N28: „Anhang 9" → „Tabelle 9 im Anhang A" (6.2, 7.3).
5. 🟠 N29: 87/380 → 85/372 mit Run-ID des paketierten Golden Runs.
6. 🟠 N31: followup_12-Pflichtnachweis + Coarse-Meshes nach `04_Run-Archive/`
   kopieren, Index-Zeile ergänzen, Prüfsummen erneuern.
7. 🟠 N17: „die PA" global → „die vorliegende Arbeit/Projektarbeit".
8. 🟡: N9 Doppelüberschrift; N16 Aufbau-Absatz oder Titelfix; N26 Caption-
   Ergänzung Vorgängerobjekte; N27 „laut Entwicklungsnotizen"; N32 GSD-Satz;
   N33 Redundanz 8.3; N35 Replay im Fazit; N36/N37 Paketpfad-Zuordnung;
   N20/N22/N23 Umbrüche; N34 „stringent".
9. ⚪ nach Zeit: N1 Grafikordner säubern; N4 Root-Prüfsummen; N2/N3 Namens-
   konsistenz; N35; N18/N19.

*Während dieser Prüfung bereits behoben:* JSON-Shorthand-Fehler (N24),
STS-Overview-Untertitel (N30), Eval-Split-Erinnerungssatz, DN-Präzisierung
Teilbild 4, Nachlauf-Benennung.

---

## Nachtrag — Umsetzung der Fixliste (27.08.2026)

Die Vor-Abgabe-Fixliste (§5.6) wurde vollständig umgesetzt; Gegenprobe
bestanden (alle Regression-Greps = 0, `??` = 0, Overfull auf Baseline 4):

- 🔴 N8/N14: Deckblatt final (Name, Matrikel, Prüfer, fixes Datum 08.09.2026),
  Kurzfassungs-Doppelüberschrift aufgelöst (N9) — pa.pdf und KI-Anlage neu
  gebaut.
- 🟠 N15: 1.2 + Tabelle-3-Zeile auf Erosionshierarchie umgestellt
  (Regression: „Dilatation und Erosion" = 0 Treffer).
- 🟠 N10: Zählung verifiziert und korrigiert — **neun erfolgreiche**
  archivierte Autopilot-Volläufe (14 Ordner im Paket, davon 5 ohne
  SUCCESS-Abschluss: 2 FAILED, 1 manuell, 2 ohne Abschlussmarker). Die im
  Plan angenommene Zahl „14" hätte nicht der Datenlage entsprochen — die
  Verifikation vor dem Commit hat das abgefangen.
- 🟠 N28: „Anhang 9" → „Tabelle 9 im Anhang A" (6.2, 7.3).
- 🟠 N29: 87/380 → 85/372 mit Golden-Run-ID und CSV-Pfaden.
- 🟠 N31: followup_12 vollständig ins Paket (484 MB, 12 Ordner inkl. interner
  Refined-Mesh-Extraktion) + README mit der präzisen Einordnung (Coarse-
  Bewertung laut PA; Refined nicht gerendert/evaluiert).
- 🟠 N17: „die PA" → 0 Treffer; Flowchart-Knoten neutral formuliert.
- 🟡/⚪: N16 Aufbau-Absatz, N26 Panel-Kontext, N27 Nachweislage, N32
  GSD-Relativierung, N33 Redundanz, N34 „durchgängig", N35 Replay im Fazit,
  N36/N37 Paketpfad-Zuordnung, N18/N20/N22/N23 Umbrüche, N1 Grafikordner
  gesäubert, N12 Seitenzahl 63.

Kapitelnoten unverändert; die gemeldeten 🟠-Punkte sind damit alle geschlossen.
