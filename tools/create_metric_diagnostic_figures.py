#!/usr/bin/env python3
"""Create stage-separated metric plots from archived matrix JSON files.

This module deliberately uses only the Python standard library. It creates
CSV provenance files and standalone PGFPlots/LaTeX sources; the build wrapper
compiles those sources to PDF. STS and SuGaR-Coarse are read from their own
metric JSON files and are never substituted for one another.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from pathlib import Path

FPS_ORDER = {"2": 0, "5": 1}
RESOLUTION_ORDER = {"720p": 0, "qhd": 1, "low": 2}
CAMERA_ORDER = {"SIMPLE_RADIAL": 0, "OPENCV": 1, "PINHOLE": 2}
METRICS = ("psnr_masked", "ssim_masked", "lpips_masked")
METRIC_LABELS = {
    "psnr_masked": r"PSNR (dB) $\uparrow$",
    "ssim_masked": r"SSIM $\uparrow$",
    "lpips_masked": r"LPIPS $\downarrow$",
}
CAMERA_SHORT = {
    "SIMPLE_RADIAL": "SR",
    "OPENCV": "OPENCV",
    "PINHOLE": "PH",
}
STAGE_FPS_COLORS = {
    ("sts", "2"): "stslightgreen",
    ("sts", "5"): "stsstronggreen",
    ("sugar_coarse", "2"): "sugarlightpurple",
    ("sugar_coarse", "5"): "sugarstrongpurple",
}
CAMERA_COLORS = {
    "SIMPLE_RADIAL": "srblue",
    "OPENCV": "opencvorange",
    "PINHOLE": "incompletegray",
}
RESOLUTION_MARKS = {"720p": "*", "qhd": "square*", "low": "triangle*"}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def read_runtime(exp: Path) -> float | None:
    """Read the complete archived pipeline-run duration."""
    candidates = [exp / "pipeline_run" / "run.md"]
    candidates.extend(sorted((exp / "pipeline_run").glob("*/run.md")))
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        start = re.search(r"^\- \*\*Start Lauf:\*\* `([^`]+)`", text, re.MULTILINE)
        end = re.search(r"^\- \*\*Ende Lauf:\*\* `([^`]+)`", text, re.MULTILINE)
        if start and end:
            from datetime import datetime

            started = datetime.fromisoformat(start.group(1))
            finished = datetime.fromisoformat(end.group(1))
            duration = (finished - started).total_seconds()
            if duration >= 0:
                return duration
        values = re.findall(r"^\|[^|]+\|[^|]+\|[^|]+\|\s*(\d+)\s*\|", text, re.MULTILINE)
        if values:
            return float(sum(int(value) for value in values))
    return None


def sort_key(row: dict) -> tuple:
    return (
        CAMERA_ORDER.get(row.get("camera_model", ""), 99),
        str(row.get("route", "")),
        FPS_ORDER.get(str(row.get("fps", "")), 99),
        RESOLUTION_ORDER.get(row.get("resolution", ""), 99),
    )


def keep_balanced_resolution_groups(rows: list[dict]) -> list[dict]:
    """Keep only complete 720p/QHD/Low groups in a resolution comparison."""
    required = {"720p", "qhd", "low"}
    groups: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        key = (str(row.get("camera_model", "")), str(row.get("fps", "")))
        groups.setdefault(key, set()).add(str(row.get("resolution", "")))
    valid_groups = {key for key, resolutions in groups.items() if required <= resolutions}
    return [
        row for row in rows
        if (str(row.get("camera_model", "")), str(row.get("fps", ""))) in valid_groups
    ]


def experiment_rows(batch: Path, metric_name: str, stage: str) -> list[dict]:
    rows: list[dict] = []
    for manifest_path in sorted(batch.glob("*/*/*/manifest.json")):
        exp = manifest_path.parent
        manifest = load_json(manifest_path)
        params = load_json(exp / "parameters.json")
        metrics_path = exp / "metrics" / metric_name
        metrics = load_json(metrics_path)
        if not metrics:
            continue
        camera = str(manifest.get("camera_model", params.get("camera_model", "")))
        resolution = str(manifest.get("resolution_id", params.get("resolution_id", exp.parents[1].name)))
        fps = str(manifest.get("fps", params.get("fps", exp.parents[2].name.replace("fps", ""))))
        variant = str(manifest.get("variant", params.get("variant", exp.name)))
        mesh_mode = str(manifest.get("mesh_mode", params.get("mesh_mode", "")))
        complete = manifest.get("status") == "success"
        route = "A" if mesh_mode == "original_gs" else "SuGaR*"
        if stage == "sugar_coarse":
            route = "SuGaR-Coarse"
        row = {
            "batch": batch.name,
            "experiment": str(exp.relative_to(batch)),
            "camera_model": camera,
            "camera_short": CAMERA_SHORT.get(camera, camera),
            "fps": fps,
            "resolution": resolution,
            "variant": variant,
            "mesh_mode": mesh_mode,
            "route": route,
            "stage": stage,
            "complete": complete,
            "metric_path": str(metrics_path),
            "runtime_s": read_runtime(exp),
            "evaluation_frame_count": metrics.get("evaluation_frame_count"),
            "psnr_masked": number(metrics.get("psnr_masked")),
            "ssim_masked": number(metrics.get("ssim_masked")),
            "lpips_masked": number(metrics.get("lpips_masked")),
            "per_frame": metrics.get("per_frame", []),
        }
        rows.append(row)
    return sorted(rows, key=sort_key)


def make_label(row: dict) -> str:
    route = row.get("route", "")
    route_short = "A" if route == "A" else ("SuGaR*" if route == "SuGaR*" else "SC")
    return f"{row.get('camera_short', '')}/{route_short} {row.get('fps', '')}fps {row.get('resolution', '')}"


def write_rows_csv(rows: list[dict], path: Path) -> None:
    fields = [
        "batch", "experiment", "stage", "camera_model", "camera_short", "route",
        "fps", "resolution", "complete", "evaluation_frame_count", "runtime_s",
        *METRICS, "metric_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_per_frame_csv(rows: list[dict], path: Path) -> None:
    fields = ["stage", "camera_model", "camera_short", "route", "fps", "resolution", "complete", "frame", *METRICS]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for item in row.get("per_frame", []):
                writer.writerow({
                    "stage": row["stage"],
                    "camera_model": row["camera_model"],
                    "camera_short": row["camera_short"],
                    "route": row["route"],
                    "fps": row["fps"],
                    "resolution": row["resolution"],
                    "complete": row["complete"],
                    "frame": item.get("frame", ""),
                    **{metric: number(item.get(metric)) for metric in METRICS},
                })


def write_graphics_data_bundle(
    sts_rows: list[dict],
    sugar_rows: list[dict],
    delta_rows: list[dict],
    output_dir: Path,
) -> None:
    """Write self-contained tabular/JSON inputs used by the graphics."""
    bundle = output_dir / "Datengrundlage"
    bundle.mkdir(parents=True, exist_ok=True)
    write_rows_csv(sts_rows, bundle / "sts_runs.csv")
    write_rows_csv(sugar_rows, bundle / "sugar_coarse_runs.csv")
    write_per_frame_csv(
        [row for row in sts_rows if row.get("complete") and row.get("mesh_mode") == "original_gs"],
        bundle / "sts_per_frame.csv",
    )
    write_per_frame_csv(
        [row for row in sugar_rows if row.get("complete")],
        bundle / "sugar_coarse_per_frame.csv",
    )
    delta_fields = ["stage", "camera_model", "camera_short", "fps", "resolution", *METRICS]
    with (bundle / "sugar_coarse_vs_sts_delta.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=delta_fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in delta_fields} for row in delta_rows)

    def compact(row: dict) -> dict:
        return {
            key: value for key, value in row.items()
            if key not in {"per_frame"} and key != "metric_path"
        }

    summary = {
        "schema": "scan2bim-metric-graphics-v1",
        "metric_scope": "object_masked_only",
        "metrics": list(METRICS),
        "stage_sources": {"sts": "sts_masked.json", "sugar_coarse": "sugar_coarse_masked.json"},
        "plot_rules": {
            "sts_overview": "complete original_gs runs only",
            "sts_boxplots": "complete original_gs runs only, per_frame values",
            "sugar_coarse_overview": "complete sugar_coarse runs only",
            "runtime": "Start Lauf to Ende Lauf from pipeline_run/run.md, fallback to recorded step sum",
        },
        "rows": {
            "sts": [compact(row) for row in sts_rows],
            "sugar_coarse": [compact(row) for row in sugar_rows],
            "delta": [compact(row) for row in delta_rows],
        },
    }
    (bundle / "matrix_graphics_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (bundle / "README.md").write_text(
        "# Datengrundlage der metrischen Grafiken\n\n"
        "Diese Dateien sind die verdichteten, außerhalb der historischen Run-Archive "
        "ausreichenden Eingaben für die sechs metrischen Grafiken. Die STS-Übersicht "
        "und STS-Boxplots enthalten nur vollständige Original-GS-Route-A-Läufe aus "
        "vollständigen 720p/QHD/Low-Gruppen. "
        "SuGaR-Coarse verwendet ausschließlich `sugar_coarse_masked.json`; "
        "historische STS-Zwischenmetriken aus fehlgeschlagenen SuGaR-Routen werden "
        "nicht geplottet.\n\n"
        "`matrix_graphics_summary.json` dokumentiert Schema, Quellen und Plotregeln. "
        "Die CSV-Dateien enthalten Lauf-, Einzelansichts- und Deltawerte; die "
        "ursprünglichen Runpfade dienen nur noch als Provenienz.\n",
        encoding="utf-8",
    )


def tex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in text)


def short_tick(row: dict, include_route: bool = True) -> str:
    camera = row.get("camera_short", "")
    route = row.get("route", "")
    route_token = "A" if route == "A" else ("Su*" if route == "SuGaR*" else "SC")
    if not include_route:
        return f"{camera}\\\\{row.get('fps', '')}/{row.get('resolution', '')}"
    return f"{camera}/{route_token}\\\\{row.get('fps', '')}/{row.get('resolution', '')}"


def all_metric_ranges(sts_rows: list[dict], sugar_rows: list[dict]) -> dict[str, tuple[float, float]]:
    ranges: dict[str, tuple[float, float]] = {}
    for metric in METRICS:
        values = [
            row[metric]
            for row in [*sts_rows, *sugar_rows]
            if row.get(metric) is not None
        ]
        low, high = min(values), max(values)
        if metric == "psnr_masked":
            ranges[metric] = (max(0.0, math.floor(low - 1)), math.ceil(high + 1))
        elif metric == "ssim_masked":
            ranges[metric] = (max(0.0, math.floor((low - 0.04) * 100) / 100), 1.0)
        else:
            ranges[metric] = (0.05, math.ceil((high + 0.04) * 100) / 100)
    return ranges


def per_frame_ranges(rows: list[dict]) -> dict[str, tuple[float, float]]:
    """Return padded y-ranges that include every per-frame point."""
    ranges: dict[str, tuple[float, float]] = {}
    for metric in METRICS:
        values = [
            number(item.get(metric))
            for row in rows
            for item in row.get("per_frame", [])
        ]
        values = [value for value in values if value is not None]
        if not values:
            ranges[metric] = (0.0, 1.0)
            continue
        low, high = min(values), max(values)
        if metric == "psnr_masked":
            ranges[metric] = (math.floor(low - 1), math.ceil(high + 1))
        elif metric == "ssim_masked":
            ranges[metric] = (
                max(0.0, math.floor((low - 0.03) * 100) / 100),
                min(1.0, math.ceil((high + 0.03) * 100) / 100),
            )
        else:
            ranges[metric] = (
                max(0.0, math.floor((low - 0.02) * 100) / 100),
                math.ceil((high + 0.02) * 100) / 100,
            )
    return ranges


def tex_preamble(title: str, subtitle: str, landscape: bool = True) -> list[str]:
    geometry = "a4paper,landscape" if landscape else "a4paper"
    title = title.replace("_", r"\_")
    subtitle = subtitle.replace("_", r"\_")
    return [
        r"\documentclass[10pt]{article}",
        rf"\usepackage[margin=1.0cm]{{geometry}}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        r"\usepackage{xcolor}",
        r"\usepackage{tikz}",
        r"\usepackage{pgfplots}",
        r"\usepgfplotslibrary{statistics}",
        r"\pgfplotsset{compat=1.18}",
        r"\definecolor{srblue}{HTML}{2F6B9A}",
        r"\definecolor{opencvorange}{HTML}{D97706}",
        r"\definecolor{fps2blue}{HTML}{B9D7EA}",
        r"\definecolor{fps5orange}{HTML}{F6C28B}",
        r"\definecolor{stslightgreen}{HTML}{A7D8B1}",
        r"\definecolor{stsstronggreen}{HTML}{208B3A}",
        r"\definecolor{sugarlightpurple}{HTML}{CBB7E8}",
        r"\definecolor{sugarstrongpurple}{HTML}{763A9B}",
        r"\definecolor{stsedge}{HTML}{1D4E89}",
        r"\definecolor{sugaredge}{HTML}{B45309}",
        r"\definecolor{incompletegray}{HTML}{9CA3AF}",
        r"\definecolor{deltared}{HTML}{B91C1C}",
        r"\definecolor{deltagreen}{HTML}{15803D}",
        r"\newcommand{\legendcircle}[1]{\tikz[baseline=-0.6ex]\node[draw=black,fill=#1,circle,minimum size=4.5pt,inner sep=0pt] {};}",
        r"\newcommand{\legendsquare}[1]{\tikz[baseline=-0.6ex]\node[draw=black,fill=#1,rectangle,minimum size=4.5pt,inner sep=0pt] {};}",
        r"\newcommand{\legendtriangle}[1]{\tikz[baseline=-0.6ex]\draw[draw=black,fill=#1,line width=0.4pt] (0,2.3pt)--(-2.3pt,-1.8pt)--(2.3pt,-1.8pt)--cycle;}",
        r"\newcommand{\legendbordercircle}[1]{\tikz[baseline=-0.6ex]\node[draw=#1,fill=white,circle,minimum size=4.5pt,inner sep=0pt,line width=0.8pt] {};}",
        r"\begin{document}",
        r"\pagestyle{empty}",
        r"\begin{center}",
        rf"{{\Large\bfseries {title}}}\\[3pt]",
        rf"{{\small {subtitle}}}\\[8pt]",
    ]


def tex_footer(legend: str) -> list[str]:
    return [
        r"\vspace{3pt}",
        rf"\begin{{minipage}}{{0.98\linewidth}}\scriptsize {legend}\end{{minipage}}",
        r"\end{center}",
        r"\end{document}",
    ]


def axis_options(
    metric: str,
    ranges: dict[str, tuple[float, float]],
    labels: list[str],
    height: str = "6.0cm",
    bars: bool = True,
    legend: bool = True,
) -> list[str]:
    low, high = ranges[metric]
    tick_labels = ",".join("{" + rf"\shortstack{{{label}}}" + "}" for label in labels)
    options = [
        rf"height={height}",
        r"width=0.98\linewidth",
        r"enlarge x limits=0.015",
        r"xmin=-0.7",
        rf"ymin={low}",
        rf"ymax={high}",
        r"xtick=data",
        rf"xticklabels={{{tick_labels}}}",
        r"x tick label style={font=\tiny,rotate=55,anchor=east}",
        r"ylabel style={font=\small}",
        r"tick label style={font=\scriptsize}",
        rf"ylabel={{{METRIC_LABELS[metric]}}}",
        r"grid=major",
        r"grid style={gray!20}",
    ]
    if bars:
        options[2:2] = [r"ybar", r"bar width=2.8pt"]
    if metric == "lpips_masked" and low >= 0:
        first = 0.05 if low >= 0.04 else 0.0
        ticks = []
        value = first
        while value <= high + 1e-9:
            ticks.append(value)
            value += 0.05
        options.extend([
            "scaled y ticks=false",
            "ytick={" + ",".join(f"{value:.2f}" for value in ticks) + "}",
            "yticklabels={" + ",".join("{" + f"{value:.2f}".replace(".", ",") + "}" for value in ticks) + "}",
        ])
    if legend:
        options.append(
            r"legend style={font=\scriptsize,at={(1.0,1.15)},anchor=south east,draw=none,fill=white,fill opacity=0.9,text opacity=1}"
        )
    return options


def overview_tex(rows: list[dict], title: str, subtitle: str, ranges: dict[str, tuple[float, float]], stage: str) -> str:
    rows = sorted(rows, key=sort_key)
    labels = [short_tick(row, include_route=stage == "sts") for row in rows]
    complete = [(index, row) for index, row in enumerate(rows) if row.get("complete") and row.get("psnr_masked") is not None]
    intermediate = [(index, row) for index, row in enumerate(rows) if not row.get("complete") and row.get("psnr_masked") is not None]
    lines = tex_preamble(title, subtitle)
    for metric in METRICS:
        lines.append(rf"\begin{{tikzpicture}}")
        positions = ",".join(str(index) for index in range(len(rows)))
        options = ",".join(axis_options(metric, ranges, labels, height="5.6cm", legend=False))
        options += rf",xtick={{{positions}}}"
        lines.append(rf"\begin{{axis}}[{options}]")
        if stage == "sts":
            for camera, color in CAMERA_COLORS.items():
                entries = [(index, row) for index, row in complete if row.get("camera_model") == camera]
                if not entries:
                    continue
                coords = " ".join(f"({index},{row[metric]:.8f})" for index, row in entries)
                lines.append(rf"\addplot+[fill={color},draw={color}] coordinates {{{coords}}};")
        else:
            for camera, color in (("SIMPLE_RADIAL", "srblue"), ("OPENCV", "opencvorange")):
                entries = [(index, row) for index, row in enumerate(rows) if row.get("camera_model") == camera and row.get(metric) is not None]
                coords = " ".join(f"({index},{row[metric]:.8f})" for index, row in entries)
                lines.append(rf"\addplot+[fill={color},draw={color},area legend] coordinates {{{coords}}};")
        lines.append(r"\end{axis}")
        lines.append(r"\end{tikzpicture}")
        lines.append(r"\par\vspace{2pt}")
    if stage == "sts":
        legend = (r"Dargestellt werden ausschließlich vollständige Original-GS-A-Routen. Vorhandene \texttt{sts\_masked.json}-Dateien aus später fehlgeschlagenen SuGaR-Routen bleiben als Fehlernachweis archiviert, werden hier aber nicht zusätzlich dargestellt. Die Auswertung ist objektmaskiert; die Werte stammen aus der jeweiligen Runauflösung.")
    else:
        legend = (r"Alle zwölf Balkenpaare stammen aus \texttt{sugar\_coarse\_masked.json}; die STS-Baseline wird nicht als SuGaR-Ergebnis verwendet. PSNR/SSIM: höher ist besser; LPIPS: niedriger ist besser.")
    lines.extend(tex_footer(legend))
    return "\n".join(lines)


def percentile(sorted_values: list[float], fraction: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def box_stats(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    q1 = percentile(ordered, 0.25)
    median = percentile(ordered, 0.5)
    q3 = percentile(ordered, 0.75)
    iqr = q3 - q1
    lower_limit = q1 - 1.5 * iqr
    upper_limit = q3 + 1.5 * iqr
    inliers = [value for value in ordered if lower_limit <= value <= upper_limit]
    return {
        "lower_whisker": min(inliers) if inliers else ordered[0],
        "q1": q1,
        "median": median,
        "q3": q3,
        "upper_whisker": max(inliers) if inliers else ordered[-1],
        "outliers": [value for value in ordered if value < lower_limit or value > upper_limit],
        "values": ordered,
    }


def boxplot_axis(lines: list[str], metric: str, rows: list[dict], ranges: dict[str, tuple[float, float]], axis_index: int) -> None:
    labels = [short_tick(row, include_route=rows[0].get("stage") == "sts") for row in rows]
    options = ",".join(axis_options(metric, ranges, labels, height="6.6cm", bars=False, legend=False).copy())
    positions = ",".join(str(index) for index in range(len(rows)))
    options += rf",xtick={{{positions}}},boxplot/draw direction=y"
    lines.append(r"\begin{tikzpicture}")
    lines.append(rf"\begin{{axis}}[{options}]")
    for index, row in enumerate(rows):
        values = [number(item.get(metric)) for item in row.get("per_frame", [])]
        values = [value for value in values if value is not None]
        if not values:
            continue
        stats = box_stats(values)
        color = CAMERA_COLORS.get(row.get("camera_model"), "black")
        lower = stats["lower_whisker"]
        q1 = stats["q1"]
        median = stats["median"]
        q3 = stats["q3"]
        upper = stats["upper_whisker"]
        left = index - 0.24
        right = index + 0.24
        lines.append(rf"\draw[fill={color}!35,draw={color}] (axis cs:{left:.4f},{q1:.8f}) rectangle (axis cs:{right:.4f},{q3:.8f});")
        lines.append(rf"\draw[draw={color},very thick] (axis cs:{left:.4f},{median:.8f}) -- (axis cs:{right:.4f},{median:.8f});")
        lines.append(rf"\draw[draw={color}] (axis cs:{index:.4f},{lower:.8f}) -- (axis cs:{index:.4f},{q1:.8f});")
        lines.append(rf"\draw[draw={color}] (axis cs:{index:.4f},{q3:.8f}) -- (axis cs:{index:.4f},{upper:.8f});")
        lines.append(rf"\draw[draw={color}] (axis cs:{left + 0.08:.4f},{lower:.8f}) -- (axis cs:{right - 0.08:.4f},{lower:.8f});")
        lines.append(rf"\draw[draw={color}] (axis cs:{left + 0.08:.4f},{upper:.8f}) -- (axis cs:{right - 0.08:.4f},{upper:.8f});")
        jittered = [
            f"({index + (((point_index * 17) % 11) - 5) * 0.035:.5f},{value:.8f})"
            for point_index, value in enumerate(values)
        ]
        lines.append(rf"\addplot[only marks,mark=*,mark size=0.65pt,color={color}!80!black,opacity=0.45] coordinates {{{' '.join(jittered)}}};")
    lines.append(r"\end{axis}")
    lines.append(r"\end{tikzpicture}")


def boxplots_tex(rows: list[dict], title: str, subtitle: str, ranges: dict[str, tuple[float, float]]) -> str:
    rows = sorted(rows, key=sort_key)
    lines = tex_preamble(title, subtitle)
    for metric in METRICS:
        boxplot_axis(lines, metric, rows, ranges, METRICS.index(metric))
        lines.append(r"\par\vspace{3pt}")
    legend = (r"Jeder Punkt ist eine einzelne Evaluationsansicht aus \texttt{per\_frame} und liegt bewusst auf der zentralen x-Kategorie der zugehörigen Box; die Box zeigt Quartile und robuste 1,5-IQR-Whisker. Die STS-Boxplots enthalten nur vollständige Original-GS-A-Routen; die SuGaR-Boxplots enthalten alle zwölf vollständigen Coarse-Läufe. Die x-Beschriftung kodiert Kamera, FPS und Auflösung; zusätzlich kennzeichnen Blau, Orange und Grau die Kameramodelle SR, OPENCV und PINHOLE. Unterschiedliche Auflösungen bleiben als separate Konfigurationen gekennzeichnet und werden nicht zu einer globalen Rangliste zusammengefasst.")
    lines.extend(tex_footer(legend))
    return "\n".join(lines)


def paired_delta_rows(sugar_rows: list[dict], followup_batch: Path) -> list[dict]:
    result = []
    for row in sugar_rows:
        exp = followup_batch / row["experiment"]
        sts = load_json(exp / "metrics" / "sts_masked.json")
        values = {metric: number(sts.get(metric)) for metric in METRICS}
        if any(value is None for value in values.values()):
            continue
        result.append({
            **row,
            **{f"delta_{metric}": row[metric] - values[metric] for metric in METRICS},
        })
    return sorted(result, key=sort_key)


def delta_tex(rows: list[dict], title: str, subtitle: str) -> str:
    labels = [short_tick(row, include_route=False) for row in rows]
    lines = tex_preamble(title, subtitle)
    ranges = {}
    for metric in METRICS:
        values = [row[f"delta_{metric}"] for row in rows]
        maximum = max(abs(value) for value in values) if values else 1.0
        ranges[metric] = (-math.ceil(maximum * 100) / 100, math.ceil(maximum * 100) / 100)
    for metric in METRICS:
        low, high = ranges[metric]
        positions = ",".join(str(index) for index in range(len(rows)))
        options = ",".join(axis_options(metric, ranges, labels, height="5.8cm", legend=True))
        options += rf",xtick={{{positions}}}"
        lines.append(r"\begin{tikzpicture}")
        lines.append(rf"\begin{{axis}}[{options},ymin={low},ymax={high},extra y ticks={{0}},extra y tick style={{grid=major,black}}]")
        for camera, color in (("SIMPLE_RADIAL", "srblue"), ("OPENCV", "opencvorange")):
            entries = [(index, row) for index, row in enumerate(rows) if row.get("camera_model") == camera]
            coords = " ".join(f"({index},{row[f'delta_{metric}']:.8f})" for index, row in entries)
            lines.append(rf"\addplot+[ybar,bar width=3pt,fill={color},draw={color}] coordinates {{{coords}}};")
        lines.append(r"\end{axis}")
        lines.append(r"\end{tikzpicture}\par\vspace{2pt}")
    lines.extend(tex_footer(r"Delta = SuGaR-Coarse minus STS for the same follow-up run. The x-label explicitly contains SR or OPENCV, FPS and resolution. For LPIPS, a negative delta favours SuGaR-Coarse because lower LPIPS is better. The paired comparison is only a rendering-stage comparison, not a mesh-accuracy test."))
    return "\n".join(lines)


def runtime_scatter_tex(sts_rows: list[dict], sugar_rows: list[dict], title: str, subtitle: str, ranges: dict[str, tuple[float, float]]) -> str:
    rows = [row for row in [*sts_rows, *sugar_rows] if row.get("complete") and row.get("runtime_s") is not None]
    max_runtime = max((row["runtime_s"] / 60 for row in rows), default=40.0)
    lines = tex_preamble(title, subtitle)
    lines.extend([
        r"\begin{tabular}{@{}ll@{\hspace{0.8cm}}ll@{\hspace{0.8cm}}ll@{}}",
        r"\legendcircle{stsstronggreen} & Farbe: STS (grün) & \legendcircle{sugarstrongpurple} & Farbe: SuGaR-Coarse (lila) & & \\",
        r"\legendcircle{stslightgreen} & Intensität: 2 FPS (blass) & \legendcircle{stsstronggreen} & Intensität: 5 FPS (kräftig) & & \\",
        r"\legendcircle{white} & 720p / Kreis & \legendsquare{white} & QHD / Quadrat & \legendtriangle{white} & Low / Dreieck\\",
        r"\legendbordercircle{srblue} & Rand: SR (blau) & \legendbordercircle{opencvorange} & Rand: OPENCV (orange) & \legendbordercircle{incompletegray} & Rand: PINHOLE (grau)\\",
        r"\end{tabular}\par\vspace{8pt}",
    ])
    for metric in METRICS:
        low, high = ranges[metric]
        lines.append(r"\begin{tikzpicture}")
        lines.append(rf"\begin{{axis}}[width=0.98\linewidth,height=5.7cm,xlabel={{Gesamtlaufzeit des archivierten Pipeline-Laufs (min)}},ylabel={{{METRIC_LABELS[metric]}}},xmin=15,xmax=40,xtick={{15,20,25,30,35,40}},ymin={low},ymax={high},grid=major]")
        for row in rows:
            if row.get(metric) is None:
                continue
            x = row["runtime_s"] / 60
            mark = RESOLUTION_MARKS.get(row.get("resolution"), "*")
            fill = STAGE_FPS_COLORS.get((row.get("stage"), str(row.get("fps"))), "black")
            edge = CAMERA_COLORS.get(row.get("camera_model"), "black")
            lines.append(rf"\addplot[only marks,mark={mark},mark size=2.2pt,mark options={{fill={fill},draw={edge},line width=0.6pt}}] coordinates {{({x:.6f},{row[metric]:.8f})}};")
        lines.append(r"\end{axis}\end{tikzpicture}\par\vspace{2pt}")
    lines.extend(tex_footer(r"Die x-Achse zeigt die vollständige Dauer des archivierten Pipeline-Laufs zwischen Start und Ende in \texttt{run.md}; ältere Berichte ohne Start/Ende verwenden ersatzweise die Summe ihrer aufgezeichneten Schritte. SAM3/COLMAP sind nur enthalten, sofern sie innerhalb dieses archivierten Laufs lagen. Die Darstellung ist explorativ und kein Geometrie-Qualitätsranking."))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-full", type=Path, required=True)
    parser.add_argument("--matrix-rest", type=Path, required=True)
    parser.add_argument("--sugar-followup", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sts_rows = experiment_rows(args.matrix_full, "sts_masked.json", "sts") + experiment_rows(args.matrix_rest, "sts_masked.json", "sts")
    sts_rows = sorted(sts_rows, key=sort_key)
    sugar_rows = experiment_rows(args.sugar_followup, "sugar_coarse_masked.json", "sugar_coarse")
    sugar_rows = sorted(sugar_rows, key=sort_key)
    complete_sts = [row for row in sts_rows if row.get("complete") and row.get("mesh_mode") == "original_gs" and all(row.get(metric) is not None for metric in METRICS)]
    complete_sts = keep_balanced_resolution_groups(complete_sts)
    complete_sugar = [row for row in sugar_rows if row.get("complete") and all(row.get(metric) is not None for metric in METRICS)]
    ranges = all_metric_ranges(sts_rows, sugar_rows)

    write_rows_csv(sts_rows, args.output_dir / "sts_masked_summary.csv")
    write_rows_csv(sugar_rows, args.output_dir / "sugar_coarse_masked_summary.csv")
    write_per_frame_csv(complete_sts, args.output_dir / "sts_masked_per_frame.csv")
    write_per_frame_csv(complete_sugar, args.output_dir / "sugar_coarse_masked_per_frame.csv")
    sts_frame_ranges = per_frame_ranges(complete_sts)
    sugar_frame_ranges = per_frame_ranges(complete_sugar)

    sts_overview_rows = [
        row for row in complete_sts
        if row.get("mesh_mode") == "original_gs"
    ]
    (args.output_dir / "sts_masked_overview.tex").write_text(
        overview_tex(
            sts_overview_rows,
            "STS-7000: objektmaskierte Bildmetriken",
            "Vollständige Original-GS-Route A aus sts_masked.json",
            ranges,
            "sts",
        ), encoding="utf-8")
    (args.output_dir / "sugar_coarse_masked_overview.tex").write_text(
        overview_tex(
            sugar_rows,
            "SuGaR-Coarse-9000: objektmaskierte Bildmetriken",
            "Ausschließlich sugar_coarse_masked.json aus den zwölf vollständigen Folgeläufen",
            ranges,
            "sugar_coarse",
        ), encoding="utf-8")
    (args.output_dir / "sts_masked_per_frame_boxplots.tex").write_text(
        boxplots_tex(complete_sts, "STS-7000: Verteilung der Einzelansichten", "Boxplots und Einzelansichten auf vollständigen Original-GS-A-Routen", sts_frame_ranges), encoding="utf-8")
    (args.output_dir / "sugar_coarse_masked_per_frame_boxplots.tex").write_text(
        boxplots_tex(complete_sugar, "SuGaR-Coarse-9000: Verteilung der Einzelansichten", "Boxplots und Einzelansichten aus zwölf vollständigen Coarse-Läufen", sugar_frame_ranges), encoding="utf-8")

    delta_rows = paired_delta_rows(complete_sugar, args.sugar_followup)
    write_graphics_data_bundle(sts_rows, sugar_rows, delta_rows, args.output_dir)
    write_rows_csv(delta_rows, args.output_dir / "sugar_coarse_vs_sts_delta.csv")
    (args.output_dir / "sugar_coarse_vs_sts_delta.tex").write_text(
        delta_tex(delta_rows, "Paired Delta: SuGaR-Coarse versus STS", "Gleiche Konfiguration und gleicher Eval-Split; Delta = SuGaR-Coarse minus STS"), encoding="utf-8")
    (args.output_dir / "metric_vs_runtime.tex").write_text(
        runtime_scatter_tex(complete_sts, complete_sugar, "Bildmetriken im Verhältnis zur Laufzeit", "Explorative Darstellung; Laufzeit = vollständiger archivierter Pipeline-Lauf", ranges), encoding="utf-8")

    report = [
        "# Neue metrische Grafiken (2026-08-12)",
        "",
        f"- STS summary rows: {len(sts_rows)}; complete Original-GS rows used for boxplots: {len(complete_sts)}",
        f"- SuGaR-Coarse summary rows: {len(sugar_rows)}; complete rows used for boxplots: {len(complete_sugar)}",
         "- Incomplete SuGaR-route `sts_masked.json` values remain in the source summary but are not plotted.",
        "- SuGaR-Coarse overview uses only `sugar_coarse_masked.json` and never substitutes `sts_masked.json`.",
        "- Boxplots use the `per_frame` values from the corresponding JSON files.",
        "- Boxplot points are placed on their category and receive only a small horizontal spread; y-ranges include all per-frame values.",
        "- Runtime scatter uses archived STS-to-postprocess durations and is exploratory because SAM3/COLMAP wall time was not archived per experiment.",
        "- Runtime x-axis is fixed to 15-40 minutes; light colors encode FPS and point/square/triangle encode 720p/QHD/Low.",
        "- Camera names are explicit x-axis labels; camera legends are intentionally omitted.",
        "- `middle` is used upstream for coverage and fixed-split eligibility; metric JSONs document `mask_level=default` for PSNR/SSIM/LPIPS aggregation.",
        "- Cross-resolution values are sensitivity results, not one global quality ranking; paired same-resolution comparisons are stronger.",
        "",
        "## Files",
        "",
        "- `sts_masked_overview.pdf` / `sugar_coarse_masked_overview.pdf`: aggregate per-run metric comparisons",
        "- `sts_masked_per_frame_boxplots.pdf` / `sugar_coarse_masked_per_frame_boxplots.pdf`: per-view distributions",
        "- `sugar_coarse_vs_sts_delta.pdf`: paired stage difference on identical follow-up runs",
        "- `metric_vs_runtime.pdf`: exploratory metric/runtime relation",
        "- `*_summary.csv`, `*_per_frame.csv`: provenance sources",
    ]
    (args.output_dir / "README.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
