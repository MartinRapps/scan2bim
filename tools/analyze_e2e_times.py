#!/usr/bin/env python3
"""Rekonstruiert End-to-End-Laufzeiten aus dem matrix.log eines Matrix-Batches.

Der Matrixrunner protokolliert SAM3, COLMAP und Maskenwarp im Batch-Log, waehrend
pipeline_run/run.md nur die STS-bis-Postprocess-Schritte enthaelt. Dieses Skript
gliedert je Experiment (MATRIX START bis MATRIX END) die Laufzeit in:

- Kopfphase:  Segmentbeginn bis Marker [5/11] (SAM3 + COLMAP + Warp + Coverage)
- RUN-Fenster: [RUN] RUN START bis [RUN] RUN END (STS bis Postprocess)
- Nachlaufphase: RUN-Ende bis Segmentende (Render, Eval, Archiv, Cleanup)
- Gesamt (Wall) und Rechenzeit ohne erkannte Pausen (Idle-Schutz).

Pausenlaengen ueber GAP_WARN_S Sekunden werden separat ausgewiesen und aus der
Rechenzeit entfernt, damit Maschinen-Idle (z. B. unterbrochene Batches) die
Messwerte nicht aufblaeht.

Verwendung:
    python3 tools/analyze_e2e_times.py [pfad/zur/matrix.log]
Ohne Argument wird das neueste data/10_runs/*/matrix.log verwendet.
Ausgabe: e2e_times.csv und e2e_times.md neben der Log-Datei.
"""

import calendar
import csv
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

GAP_WARN_S = 300

# Container (SAM3-Python-Logs, COLMAP-glog) schreiben UTC; die Runner-Echos
# ([RUN]/[STEP]) tragen lokale Zeit mit Offset; die run.log-Kopie nutzt naive
# lokale Zeit in Klammern. Alle Zeiten werden auf UTC-Epochen normiert.
TS_ISO = re.compile(
    r"\[?(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
    r"(?:[.,]\d+)?(?:\s*([+-]\d{4}))?\]?")
TS_GLOG = re.compile(r"[IWEF](\d{4})(\d{2})(\d{2})\s+(\d{2}):(\d{2}):(\d{2})")
MATRIX_START = re.compile(r"MATRIX START: (\S+) / (\S+)")
MATRIX_END = re.compile(r"MATRIX END:")
STEP_MARKER = re.compile(r"\[(\d+[a-z]?/\d+)\]")
RUN_START = re.compile(r"\[RUN\] RUN START:")
RUN_END = re.compile(r"\[RUN\] RUN END:")


def parse_ts(line, local_off=0):
    # ffprobe metadaten (z. B. creation_time des Eingabevideos) enthalten
    # Datumsangaben, die keine Logzeitpunkte sind und muessen ignoriert werden.
    if "creation_time" in line:
        return None
    m = TS_ISO.search(line)
    if m:
        y, mo, d, h, mi, s, off = m.groups()
        try:
            epoch = calendar.timegm((int(y), int(mo), int(d), int(h), int(mi), int(s)))
        except ValueError:
            return None
        if off:
            sign = 1 if off[0] == "+" else -1
            off_s = sign * (int(off[1:3]) * 3600 + int(off[3:5]) * 60)
            return epoch - off_s
        if line.startswith("["):
            # run.log-Kopie: naive Zeit in Klammern ist lokal.
            return epoch - local_off
        return epoch  # uebrige naive Zeiten (Python-Logging) sind UTC
    m = TS_GLOG.search(line)
    if m:
        y, mo, d, h, mi, s = m.groups()
        try:
            return calendar.timegm((int(y), int(mo), int(d), int(h), int(mi), int(s)))
        except ValueError:
            return None
    return None


def find_local_offset(log_path):
    for raw in log_path.read_text(errors="ignore").splitlines()[:4000]:
        m = re.search(r"\[\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}([+-]\d{4})\]", raw)
        if m:
            off = m.group(1)
            sign = 1 if off[0] == "+" else -1
            return sign * (int(off[1:3]) * 3600 + int(off[3:5]) * 60)
    return 0


def fmt_hms(epoch, offset_s):
    if epoch is None:
        return "-"
    dt = datetime.fromtimestamp(epoch + offset_s, tz=timezone.utc)
    return dt.strftime("%H:%M:%S")


def fmt_mmss(seconds):
    if seconds is None:
        return "-"
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes:02d}:{secs:02d}"


def collect_segments(log_path, local_off=0):
    segments = []
    cur = None
    pending_markers = []
    for raw in log_path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        m = MATRIX_START.search(line)
        if m:
            if cur:
                segments.append(cur)
            cur = {"label": f"{m.group(1)} / {m.group(2)}", "ts": [], "markers": {}}
            pending_markers = []
            continue
        if MATRIX_END.search(line):
            if cur is not None:
                t = parse_ts(line, local_off)
                if t:
                    cur["ts"].append(t)
                    for mk in pending_markers:
                        cur["markers"].setdefault(mk, t)
                    pending_markers = []
                segments.append(cur)
                cur = None
            continue
        if cur is None:
            continue
        t = parse_ts(line, local_off)
        if t:
            cur["ts"].append(t)
            for mk in pending_markers:
                cur["markers"].setdefault(mk, t)
            pending_markers = []
        else:
            mk = STEP_MARKER.search(line)
            if mk:
                # Runner-Echos tragen keine eigene Zeit; der letzte gesehene
                # Container-Zeitstempel ist der beste Schaetzwert. Nur vor dem
                # allerersten Zeitstempel bleibt der Marker pending.
                if cur["ts"]:
                    cur["markers"].setdefault(mk.group(1), cur["ts"][-1])
                else:
                    pending_markers.append(mk.group(1))
        if RUN_START.search(line) and t:
            cur.setdefault("run_start", t)
        if RUN_END.search(line) and t:
            cur["run_end"] = t
    if cur:
        segments.append(cur)
    return segments


def analyze_segment(seg):
    ts = seg["ts"]
    result = {"label": seg["label"], "head_s": None, "run_s": None,
              "tail_s": None, "wall_s": None, "compute_s": None,
              "idle_s": None, "gaps": [], "timestamps": len(ts)}
    if not ts:
        return result
    first, last = ts[0], ts[-1]
    result["wall_s"] = (last - first)
    idle = 0.0
    for a, b in zip(ts, ts[1:]):
        delta = (b - a)
        if delta > GAP_WARN_S:
            result["gaps"].append((a, b, delta))
            # Luecken INNERHALB des RUN-Fensters sind stille Rechenzeit (STS
            # trainiert ohne Logausgabe ins Batch-Log), kein Maschinen-Idle.
            rs, re_ = seg.get("run_start"), seg.get("run_end")
            inside_run = rs and re_ and a >= rs and b <= re_
            if not inside_run:
                idle += delta
    result["idle_s"] = idle

    head_end = seg["markers"].get("5/11") or seg.get("run_start")
    if head_end is not None and head_end > first:
        result["head_s"] = (head_end - first)
    if seg.get("run_start") and seg.get("run_end"):
        result["run_s"] = (seg["run_end"] - seg["run_start"])
        tail_end = last
        if tail_end > seg["run_end"]:
            result["tail_s"] = (tail_end - seg["run_end"])
    return result


def main():
    if len(sys.argv) > 1:
        log_path = Path(sys.argv[1])
    else:
        candidates = sorted(Path("data/10_runs").glob("*/matrix.log"),
                            key=lambda p: p.stat().st_mtime)
        if not candidates:
            sys.exit("Keine matrix.log unter data/10_runs/ gefunden.")
        log_path = candidates[-1]
    local_off = find_local_offset(log_path)
    raw_segments = collect_segments(log_path, local_off)
    segments = [analyze_segment(s) for s in raw_segments]
    if not segments:
        sys.exit(f"Keine MATRIX-START/END-Segmente in {log_path} gefunden.")

    # In-Segment-Schwaenze fehlen oft, weil die Archiv-/Rendermarker keine
    # eigenen Zeitstempel tragen. Ersatz: Lauf von RUN-Ende bis zum ersten
    # Zeitstempel des Folgesegments (enthaelt Cleanup + Folgestart, gilt als
    # Obergrenze und ist entsprechend gekennzeichnet).
    for i, r in enumerate(segments):
        if r["tail_s"] is None and r["run_s"] is not None:
            run_end = raw_segments[i].get("run_end")
            nxt = raw_segments[i + 1]["ts"][0] if i + 1 < len(raw_segments) \
                and raw_segments[i + 1]["ts"] else None
            if run_end and nxt and nxt > run_end:
                r["tail_s"] = (nxt - run_end)
                r["tail_is_upper"] = True
            else:
                r["tail_is_upper"] = False
        else:
            r["tail_is_upper"] = False

    # Rechenzeit = Wandzeit bereinigt um Pausen ausserhalb des RUN-Fensters.
    # Luecken INNERHALB des RUN-Fensters sind stille Rechenzeit und bleiben.
    for r in segments:
        if r["wall_s"] is not None:
            r["compute_s"] = r["wall_s"] - (r["idle_s"] or 0.0)

    out_dir = log_path.parent
    local_off = find_local_offset(log_path)
    csv_path = out_dir / "e2e_times.csv"
    md_path = out_dir / "e2e_times.md"
    fields = ["experiment", "head_s", "run_s", "tail_s", "wall_s",
              "compute_s", "gaps_over_5min_s", "timestamps"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for r in segments:
            writer.writerow({
                "experiment": r["label"],
                "head_s": "" if r["head_s"] is None else round(r["head_s"]),
                "run_s": "" if r["run_s"] is None else round(r["run_s"]),
                "tail_s": "" if r["tail_s"] is None else round(r["tail_s"]),
                "wall_s": "" if r["wall_s"] is None else round(r["wall_s"]),
                "compute_s": "" if r["compute_s"] is None else round(r["compute_s"]),
                "gaps_over_5min_s": round(sum(g[2] for g in r["gaps"])),
                "timestamps": r["timestamps"],
            })

    lines = [
        "# E2E-Laufzeiten aus matrix.log",
        "",
        f"Quelle: `{log_path}`",
        "",
        "| Experiment | Kopf (SAM3+COLMAP+Warp) | STS→Post | Nachlauf (Render/Archiv) | Gesamt (Wall) | Rechenzeit o. Pausen | Pausen >5 min |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in segments:
        gap_txt = ", ".join(
            f"{fmt_mmss((b - a))} ab {fmt_hms(a, local_off)}"
            for a, b, _ in r["gaps"]) or "-"
        tail_mark = "*" if r.get("tail_is_upper") else ""
        lines.append(
            f"| {r['label']} | {fmt_mmss(r['head_s'])} | {fmt_mmss(r['run_s'])} "
            f"| {fmt_mmss(r['tail_s'])}{tail_mark} | {fmt_mmss(r['wall_s'])} "
            f"| {fmt_mmss(r['compute_s'])} | {gap_txt} |")
    lines += [
        "",
        "Hinweis: Kopf- und Nachlaufphase nutzen die ersten bzw. letzten Zeitstempel",
        "des Segments; Containerstart-Dauer von wenigen Sekunden ist enthalten.",
        "* = Obergrenze: Nachlaufphase bis zum Folgesegmentbeginn geschätzt",
        "(enthält Cleanup und Folgestart). Pausen ueber 5 Minuten ohne Logaktivitaet",
        "gelten als Maschinen-Idle und werden von der Rechenzeit abgezogen, aber",
        "ausgewiesen. Von ffprobe-Metadaten (creation_time) stammende Datumsangaben",
        "werden ignoriert. Container-Logs (UTC) und Runner-Echos (Lokalzeit) werden",
        "auf eine gemeinsame Zeitzonen-Basis normiert.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(md_path)
    print()
    print("\n".join(lines[4:]))


if __name__ == "__main__":
    main()
