#!/usr/bin/env python3
"""Create thesis-ready grouped metric tables from archived matrix batches.

The generated tables use two grouped columns (2 FPS and 5 FPS) and one row per
route/resolution. The original tables use object-masked STS metrics. The
additional SuGaR tables use the successful ``sugar_coarse_masked.json`` stage
from the dedicated follow-up matrix and never substitute an STS baseline for a
SuGaR result.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from analyze_matrix_results import (  # noqa: E402
    collect,
    failure_reason,
    load_json,
    read_coverage,
    read_pipeline_runtime,
)


FPS_ORDER = ["2", "5"]
RESOLUTION_ORDER = ["720p", "qhd", "low"]
VARIANT_ORDER = ["simple_radial_a", "simple_radial_sugar", "pinhole_a", "opencv_a"]
VARIANT_LABELS = {
    "simple_radial_a": r"SIMPLE\textsubscript{RADIAL} / A$^{*}$",
    "simple_radial_sugar": r"SIMPLE\textsubscript{RADIAL} / SuGaR",
    "pinhole_a": r"PINHOLE / A",
    "opencv_a": r"OPENCV / A",
}
RESOLUTION_LABELS = {"720p": "720p", "qhd": "QHD", "low": "Low"}
SUGAR_VARIANT_ORDER = ["simple_radial_sugar_coarse", "opencv_sugar_coarse"]
SUGAR_VARIANT_LABELS = {
    "simple_radial_sugar_coarse": r"SIMPLE\textsubscript{RADIAL} / SuGaR-Coarse",
    "opencv_sugar_coarse": r"OPENCV / SuGaR-Coarse",
}
COMBINED_VARIANT_ORDER = [
    "simple_radial_a",
    "pinhole_a",
    "opencv_a",
    "simple_radial_sugar_coarse",
    "opencv_sugar_coarse",
]
COMBINED_VARIANT_LABELS = {
    "simple_radial_a": r"SIMPLE\textsubscript{RADIAL} / A (STS-7000)",
    "pinhole_a": r"PINHOLE / A (STS-7000)",
    "opencv_a": r"OPENCV / A (STS-7000)",
    **SUGAR_VARIANT_LABELS,
}


def latex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in text)


def number(row: dict, key: str) -> float | None:
    value = row.get(key, "")
    if value in ("", None):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def load_rows(current: Path, previous: Path) -> list[dict]:
    rows = []
    for batch, source in ((previous, "previous batch"), (current, "matrix_rest")):
        for row in collect(batch):
            row = dict(row)
            row["source"] = source
            row["batch"] = batch.name
            row["model_stage"] = "sts"
            rows.append(row)
    return rows


def load_sugar_rows(batch: Path) -> list[dict]:
    """Load only successful SuGaR-Coarse metrics from a follow-up batch."""
    rows = []
    for manifest_path in sorted(batch.glob("*/*/*/manifest.json")):
        experiment = manifest_path.parent
        manifest = load_json(manifest_path)
        params = load_json(experiment / "parameters.json")
        metrics_path = experiment / "metrics" / "sugar_coarse_masked.json"
        metrics = load_json(metrics_path)
        variant = str(manifest.get("variant", params.get("variant", experiment.name)))
        variant_id = f"{variant}_coarse"
        status = "success"
        if manifest.get("status") != "success" or not all(
            number(metrics, key) is not None
            for key in ("psnr_masked", "ssim_masked", "lpips_masked")
        ):
            status = "failed"
        coverage = read_coverage(experiment)
        runtime_s = read_pipeline_runtime(experiment)
        row = {
            "fps": str(manifest.get("fps", params.get("fps", experiment.parents[2].name.replace("fps", "")))),
            "resolution": str(manifest.get("resolution_id", params.get("resolution_id", experiment.parents[1].name))),
            "variant": variant_id,
            "camera_model": str(manifest.get("camera_model", params.get("camera_model", ""))),
            "mesh_mode": "sugar_coarse",
            "status": status,
            "message": str(manifest.get("message", "")),
            "evaluation_frames": metrics.get("evaluation_frame_count", ""),
            "psnr_masked": metrics.get("psnr_masked", ""),
            "ssim_masked": metrics.get("ssim_masked", ""),
            "lpips_masked": metrics.get("lpips_masked", ""),
            "empty_fraction": coverage.get("empty_fraction", ""),
            "empty_frames": coverage.get("empty_frames", ""),
            "total_frames": coverage.get("total_frames", ""),
            "runtime_s": runtime_s if runtime_s is not None else "",
            "runtime_source": "pipeline_run step sum" if runtime_s is not None else "",
            "failure_reason": "" if status == "success" else failure_reason(experiment),
            "experiment": str(experiment.relative_to(batch)),
            "source": "SuGaR follow-up",
            "batch": batch.name,
            "model_stage": "sugar_coarse",
            "metric_path": str(metrics_path),
        }
        rows.append(row)
    return rows


def index_rows(rows: list[dict]) -> dict[tuple[str, str, str], dict]:
    indexed: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (str(row["fps"]), str(row["variant"]), str(row["resolution"]))
        indexed[key] = row
    return indexed


def quality_indices(rows: list[dict]) -> None:
    candidates = [
        row for row in rows
        if row.get("status") == "success"
        and number(row, "psnr_masked") is not None
        and number(row, "ssim_masked") is not None
        and number(row, "lpips_masked") is not None
        and number(row, "runtime_s") is not None
    ]
    ranges = {}
    for key in ("psnr_masked", "ssim_masked", "lpips_masked"):
        values = [number(row, key) for row in candidates]
        values = [value for value in values if value is not None]
        ranges[key] = (min(values), max(values))
    for row in rows:
        row["quality_index"] = ""
        row["quality_per_minute"] = ""
        if row not in candidates:
            continue
        normalized = []
        for key, lower_is_better in (("psnr_masked", False), ("ssim_masked", False), ("lpips_masked", True)):
            value = number(row, key)
            low, high = ranges[key]
            if high == low:
                score = 0.5
            else:
                score = (value - low) / (high - low)
                if lower_is_better:
                    score = 1.0 - score
            normalized.append(score)
        quality = 100.0 * sum(normalized) / len(normalized)
        runtime_min = number(row, "runtime_s") / 60.0
        row["quality_index"] = quality
        row["quality_per_minute"] = quality / runtime_min if runtime_min > 0 else ""


def best_values(indexed: dict[tuple[str, str, str], dict], metric: str, fps: str) -> float | None:
    values = []
    for (row_fps, _variant, _resolution), row in indexed.items():
        if row_fps != fps or row.get("status") != "success":
            continue
        value = number(row, metric)
        if value is not None:
            values.append(value)
    if not values:
        return None
    return min(values) if metric == "lpips_masked" else max(values)


def average_metric_value(
    indexed: dict[tuple[str, str, str], dict],
    variant: str,
    resolution: str,
    metric: str,
) -> float | None:
    values = []
    for fps in FPS_ORDER:
        row = indexed.get((fps, variant, resolution))
        value = number(row, metric) if row and row.get("status") == "success" else None
        if value is None:
            return None
        values.append(value)
    return sum(values) / len(values)


def best_average_value(
    indexed: dict[tuple[str, str, str], dict],
    metric: str,
    variant_order: list[str] = VARIANT_ORDER,
) -> float | None:
    values = [
        value
        for variant in variant_order
        for resolution in RESOLUTION_ORDER
        if (value := average_metric_value(indexed, variant, resolution, metric)) is not None
    ]
    if not values:
        return None
    return min(values) if metric == "lpips_masked" else max(values)


def metric_color(value: float | None, metric: str, successful: bool, best: bool, all_values: list[float]) -> str:
    if value is None:
        return "missinggray" if successful else "failred"
    if not successful:
        return "incompleteorange"
    if best:
        return "bestgreen"
    if not all_values:
        return "neutral"
    low, high = min(all_values), max(all_values)
    score = 0.5 if high == low else (value - low) / (high - low)
    if metric == "lpips_masked":
        score = 1.0 - score
    if score >= 0.66:
        return "goodgreen"
    if score >= 0.33:
        return "midyellow"
    return "lowred"


def format_metric_cell(row: dict | None, metric: str, indexed: dict[tuple[str, str, str], dict], all_values: list[float]) -> str:
    if row is None:
        return r"\cellcolor{missinggray}\textcolor{darkgray}{--}"
    value = number(row, metric)
    successful = row.get("status") == "success"
    best = value is not None and successful and value == best_values(indexed, metric, str(row["fps"]))
    color = metric_color(value, metric, successful, best, all_values)
    if value is None:
        return rf"\cellcolor{{{color}}}\textcolor{{darkgray}}{{--}}$^{{\ddagger}}$"
    precision = ".4f" if metric == "lpips_masked" else ".3f"
    text = format(value, precision)
    if best:
        text = rf"\textbf{{{text}}}"
    if not successful:
        text += r"$^{\dagger}$"
    return rf"\cellcolor{{{color}}}{text}"


def status_cell(row: dict | None) -> str:
    if row is None:
        return r"\cellcolor{missinggray}\textcolor{darkgray}{not run}"
    if row.get("status") == "success":
        return r"\cellcolor{bestgreen}\textbf{OK}"
    return r"\cellcolor{failred}\textbf{FAIL}"


def best_efficiency_value(
    indexed: dict[tuple[str, str, str], dict], fps: str
) -> float | None:
    values = [
        number(row, "quality_per_minute")
        for (row_fps, _variant, _resolution), row in indexed.items()
        if row_fps == fps and row.get("status") == "success"
    ]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def best_efficiency_average(
    indexed: dict[tuple[str, str, str], dict],
    variant_order: list[str] = VARIANT_ORDER,
) -> float | None:
    values = []
    for variant in variant_order:
        for resolution in RESOLUTION_ORDER:
            pair = [indexed.get((fps, variant, resolution)) for fps in FPS_ORDER]
            if any(row is None or row.get("status") != "success" for row in pair):
                continue
            efficiencies = [number(row, "quality_per_minute") for row in pair]
            if all(value is not None for value in efficiencies):
                values.append(sum(efficiencies) / 2)
    return max(values) if values else None


def runtime_cell(
    row: dict | None,
    indexed: dict[tuple[str, str, str], dict],
    fps: str,
) -> str:
    if row is None:
        return r"\cellcolor{missinggray}\textcolor{darkgray}{--}"
    runtime = number(row, "runtime_s")
    if runtime is None:
        return r"\cellcolor{missinggray}\textcolor{darkgray}{--}"
    minutes = runtime / 60.0
    if row.get("status") != "success":
        return rf"\cellcolor{{incompleteorange}}\textcolor{{darkgray}}{{\makecell{{FAIL\\[-1pt]\scriptsize {minutes:.1f} min}}}}"
    efficiency = number(row, "quality_per_minute")
    if efficiency is None:
        return rf"\cellcolor{{missinggray}}\textcolor{{darkgray}}{{\makecell{{--\\[-1pt]\scriptsize {minutes:.1f} min}}}}"
    color = "bestgreen" if efficiency == best_efficiency_value(indexed, fps) else "neutral"
    text = rf"\textbf{{{efficiency:.2f}}}" if color == "bestgreen" else f"{efficiency:.2f}"
    return rf"\cellcolor{{{color}}}\makecell{{{text}\\[-1pt]\scriptsize {minutes:.1f} min}}"


def table_rows(
    indexed: dict[tuple[str, str, str], dict],
    cell_renderer,
    average_renderer=None,
    variant_order: list[str] = VARIANT_ORDER,
    variant_labels: dict[str, str] = VARIANT_LABELS,
) -> list[str]:
    lines = []
    for variant in variant_order:
        for resolution in RESOLUTION_ORDER:
            label = f"{variant_labels[variant]} / {RESOLUTION_LABELS[resolution]}"
            cells = []
            for fps in FPS_ORDER:
                cells.append(cell_renderer(indexed.get((fps, variant, resolution)), fps))
            if average_renderer is not None:
                cells.append(average_renderer(variant, resolution))
            lines.append(f"{label} & {' & '.join(cells)} " + r"\\")
    return lines


def tex_header(title: str, subtitle: str, include_average: bool = False) -> list[str]:
    column_spec = (
        r">{\raggedright\arraybackslash}p{5.9cm}YYY"
        if include_average
        else r">{\raggedright\arraybackslash}p{7.1cm}YY"
    )
    header = (
        r"\textbf{Konfiguration / Auflösung} & "
        r"\multicolumn{1}{c}{\textbf{2 FPS}} & "
        r"\multicolumn{1}{c}{\textbf{5 FPS}}"
    )
    if include_average:
        header += r" & \multicolumn{1}{c}{\textbf{Average}}"
    header += r"\\"
    return [
        r"\documentclass[a4paper,landscape]{article}",
        r"\usepackage[margin=1.15cm]{geometry}",
        r"\usepackage[table]{xcolor}",
        r"\usepackage{booktabs,tabularx,array,makecell}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        r"\definecolor{bestgreen}{HTML}{C6EFCE}",
        r"\definecolor{goodgreen}{HTML}{E2F0D9}",
        r"\definecolor{midyellow}{HTML}{FFF2CC}",
        r"\definecolor{lowred}{HTML}{F4CCCC}",
        r"\definecolor{failred}{HTML}{F4CCCC}",
        r"\definecolor{incompleteorange}{HTML}{FCE4D6}",
        r"\definecolor{missinggray}{HTML}{E7E6E6}",
        r"\definecolor{neutral}{HTML}{F2F2F2}",
        r"\definecolor{darkgray}{HTML}{666666}",
        r"\newcolumntype{Y}{>{\centering\arraybackslash}X}",
        r"\renewcommand{\arraystretch}{1.32}",
        r"\begin{document}",
        r"\pagestyle{empty}",
        r"\begin{center}",
        rf"{{\Large\bfseries {title}}}\\[3pt]",
        rf"{{\small {subtitle}}}\\[10pt]",
        rf"\begin{{tabularx}}{{0.98\linewidth}}{{{column_spec}}}",
        r"\toprule",
        header,
        r"\midrule",
    ]


def tex_footer(legend: str) -> list[str]:
    return [
        r"\bottomrule",
        r"\end{tabularx}",
        r"\vspace{7pt}",
        rf"\begin{{minipage}}{{0.98\linewidth}}\scriptsize {legend}\end{{minipage}}",
        r"\end{center}",
        r"\end{document}",
    ]


def metric_tex(
    metric: str,
    title: str,
    indexed: dict,
    rows: list[dict],
    variant_order: list[str] = VARIANT_ORDER,
    variant_labels: dict[str, str] = VARIANT_LABELS,
    subtitle: str | None = None,
) -> str:
    all_values = [number(row, metric) for row in rows if row.get("status") == "success"]
    all_values = [value for value in all_values if value is not None]

    def render(row: dict | None, _fps: str) -> str:
        return format_metric_cell(row, metric, indexed, all_values)

    average_values = [
        value
        for variant in variant_order
        for resolution in RESOLUTION_ORDER
        if (value := average_metric_value(indexed, variant, resolution, metric)) is not None
    ]

    def render_average(variant: str, resolution: str) -> str:
        value = average_metric_value(indexed, variant, resolution, metric)
        if value is None:
            return r"\cellcolor{incompleteorange}\textcolor{darkgray}{--}$^{\ddagger}$"
        best = value == best_average_value(indexed, metric, variant_order)
        color = metric_color(value, metric, True, best, average_values)
        text = f"{value:.4f}" if metric == "lpips_masked" else f"{value:.3f}"
        if best:
            text = rf"\textbf{{{text}}}"
        return rf"\cellcolor{{{color}}}{text}"

    subtitle = subtitle or "STS-7000; ausschließlich objektmaskierte Auswertung; fett/grün = bestes verfügbares Ergebnis je FPS"
    legend = (r"$^{*}$ bereits im vorherigen Batch getestet und nicht erneut gerechnet. "
              r"$^{\dagger}$ Metrik der ausgewählten Route/Stufe ist vorhanden, aber der Lauf ist insgesamt fehlgeschlagen. "
              r"$^{\ddagger}$ keine Metrik wegen fehlender/leerer Eval-Maske. "
              r"Grün = besser, Gelb = mittlerer Bereich, Rot = schlechter bzw. fehlgeschlagen. "
              r"PSNR/SSIM: höher ist besser; LPIPS: niedriger ist besser.")
    legend += r" Average = arithmetisches Mittel aus 2 und 5 FPS; nur berechnet, wenn beide Läufe vollständig erfolgreich sind."
    return "\n".join(
        tex_header(title, subtitle, include_average=True)
        + table_rows(indexed, render, render_average, variant_order, variant_labels)
        + tex_footer(legend)
    )


def status_tex(
    indexed: dict,
    variant_order: list[str] = VARIANT_ORDER,
    variant_labels: dict[str, str] = VARIANT_LABELS,
    subtitle: str | None = None,
) -> str:
    def render(row: dict | None, _fps: str) -> str:
        return status_cell(row)
    subtitle = subtitle or "Archivstatus einschließlich der sechs historischen SIMPLE-RADIAL-A-Versuche"
    legend = (r"OK = Matrixlauf einschließlich Postprocess abgeschlossen. FAIL = Lauf nicht vollständig abgeschlossen. "
              r"$^{*}$ bezeichnet die sechs historischen A-Läufe aus dem vorherigen Batch.")
    return "\n".join(
        tex_header("Matrixstatus", subtitle)
        + table_rows(indexed, render, variant_order=variant_order, variant_labels=variant_labels)
        + tex_footer(legend)
    )


def efficiency_tex(
    indexed: dict,
    variant_order: list[str] = VARIANT_ORDER,
    variant_labels: dict[str, str] = VARIANT_LABELS,
    subtitle: str | None = None,
) -> str:
    def render(row: dict | None, _fps: str) -> str:
        return runtime_cell(row, indexed, _fps)

    def render_average(variant: str, resolution: str) -> str:
        pair = [indexed.get((fps, variant, resolution)) for fps in FPS_ORDER]
        if any(row is None or row.get("status") != "success" for row in pair):
            return r"\cellcolor{incompleteorange}\textcolor{darkgray}{--}$^{\ddagger}$"
        values = [number(row, "quality_per_minute") for row in pair]
        runtimes = [number(row, "runtime_s") for row in pair]
        if any(value is None for value in values + runtimes):
            return r"\cellcolor{missinggray}\textcolor{darkgray}{--}"
        efficiency = sum(values) / 2
        color = "bestgreen" if efficiency == best_efficiency_average(indexed, variant_order) else "neutral"
        text = rf"\textbf{{{efficiency:.2f}}}" if color == "bestgreen" else f"{efficiency:.2f}"
        return rf"\cellcolor{{{color}}}\makecell{{{text}\\[-1pt]\scriptsize {sum(runtimes) / 2 / 60:.1f} min}}"

    subtitle = subtitle or "Relativer Qualitätsindex pro Pipeline-Minute; Laufzeit = Summe der STS-bis-Postprocess-Schritte"
    legend = (r"Zuerst werden PSNR, SSIM und LPIPS über alle erfolgreichen Läufe auf 0--1 normalisiert "
              r"(LPIPS invertiert), anschließend gemittelt und mit 100 multipliziert: "
              r"$Q=100\cdot(PSNR_n+SSIM_n+LPIPS_n)/3$. Der Quotient ist $Q/t_{min}$; höher ist besser. "
              r"Die Kennzahl ist ein explorativer Effizienzvergleich und ersetzt keine geometrische Genauigkeitsmetrik. "
              r"In der Zelle steht oben $Q/t_{min}$ und unten die Laufzeit. Fehlgeschlagene Läufe werden nicht gerankt.")
    legend += r" Average = arithmetisches Mittel der 2- und 5-FPS-Quotienten bei vollständigen Läufen."
    return "\n".join(
        tex_header("Zeit-Qualitäts-Verhältnis", subtitle, include_average=True)
        + table_rows(indexed, render, render_average, variant_order, variant_labels)
        + tex_footer(legend)
    )


def overview_tex(
    indexed: dict,
    rows: list[dict],
    variant_order: list[str] = VARIANT_ORDER,
    variant_labels: dict[str, str] = VARIANT_LABELS,
    title: str = "Übergeordnete Matrix: PSNR, SSIM und LPIPS",
    subtitle: str = "Objektmaskierte STS-7000-Metriken; Zeilen = Laufbezeichnung; Average = Mittelwert aus 2 und 5 FPS",
) -> str:
    metrics = ["psnr_masked", "ssim_masked", "lpips_masked"]
    metric_labels = {
        "psnr_masked": r"PSNR$\uparrow$",
        "ssim_masked": r"SSIM$\uparrow$",
        "lpips_masked": r"LPIPS$\downarrow$",
    }
    all_values = {
        metric: [
            value
            for value in (number(row, metric) for row in rows if row.get("status") == "success")
            if value is not None
        ]
        for metric in metrics
    }
    average_values = {
        metric: [
            value
            for variant in variant_order
            for resolution in RESOLUTION_ORDER
            if (value := average_metric_value(indexed, variant, resolution, metric)) is not None
        ]
        for metric in metrics
    }

    def average_cell(metric: str, variant: str, resolution: str) -> str:
        value = average_metric_value(indexed, variant, resolution, metric)
        if value is None:
            return r"\cellcolor{incompleteorange}\textcolor{darkgray}{--}$^{\ddagger}$"
        best = value == best_average_value(indexed, metric, variant_order)
        color = metric_color(value, metric, True, best, average_values[metric])
        text = f"{value:.4f}" if metric == "lpips_masked" else f"{value:.3f}"
        if best:
            text = rf"\textbf{{{text}}}"
        return rf"\cellcolor{{{color}}}{text}"

    lines = [
        r"\documentclass[a4paper,landscape]{article}",
        r"\usepackage[margin=0.8cm]{geometry}",
        r"\usepackage[table]{xcolor}",
        r"\usepackage{booktabs,tabularx,array,makecell}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        r"\definecolor{bestgreen}{HTML}{C6EFCE}",
        r"\definecolor{goodgreen}{HTML}{E2F0D9}",
        r"\definecolor{midyellow}{HTML}{FFF2CC}",
        r"\definecolor{lowred}{HTML}{F4CCCC}",
        r"\definecolor{failred}{HTML}{F4CCCC}",
        r"\definecolor{incompleteorange}{HTML}{FCE4D6}",
        r"\definecolor{missinggray}{HTML}{E7E6E6}",
        r"\definecolor{darkgray}{HTML}{666666}",
        r"\newcolumntype{Y}{>{\centering\arraybackslash}X}",
        r"\renewcommand{\arraystretch}{1.28}",
        r"\begin{document}",
        r"\pagestyle{empty}",
        r"\begin{center}",
        rf"{{\Large\bfseries {title}}}\\[3pt]",
        rf"{{\small {subtitle}}}\\[8pt]",
        r"\begin{tabularx}{0.99\linewidth}{>{\raggedright\arraybackslash}p{5.0cm}YYYYYYYYY}",
        r"\toprule",
        r"\textbf{Laufbezeichnung} & \multicolumn{3}{c}{\textbf{2 FPS}} & \multicolumn{3}{c}{\textbf{5 FPS}} & \multicolumn{3}{c}{\textbf{Average}}\\",
        " & " + " & ".join(metric_labels[metric] for _group in range(3) for metric in metrics) + r"\\",
        r"\midrule",
    ]
    for variant in variant_order:
        for resolution in RESOLUTION_ORDER:
            label = f"{variant_labels[variant]} / {RESOLUTION_LABELS[resolution]}"
            cells = []
            for fps in FPS_ORDER:
                row = indexed.get((fps, variant, resolution))
                for metric in metrics:
                    cells.append(format_metric_cell(row, metric, indexed, all_values[metric]))
            for metric in metrics:
                cells.append(average_cell(metric, variant, resolution))
            lines.append(f"{label} & {' & '.join(cells)} " + r"\\")
    legend = (
        r"$^{*}$ bereits im vorherigen Batch getestet und nicht erneut gerechnet. "
        r"$^{\dagger}$ Metrik der ausgewählten Route/Stufe vorhanden, aber der Lauf insgesamt fehlgeschlagen. "
        r"$^{\ddagger}$ kein Average wegen eines fehlenden/fehlgeschlagenen FPS-Laufs. "
        r"Grün/fett = bestes verfügbares Ergebnis innerhalb der jeweiligen Spaltengruppe; Gelb = mittlerer Bereich; Rot = schlechter bzw. fehlgeschlagen. "
        r"PSNR/SSIM: höher ist besser; LPIPS: niedriger ist besser."
    )
    lines += [
        r"\bottomrule",
        r"\end{tabularx}",
        r"\vspace{5pt}",
        rf"\begin{{minipage}}{{0.99\linewidth}}\scriptsize {legend}\end{{minipage}}",
        r"\end{center}",
        r"\end{document}",
    ]
    return "\n".join(lines)


def write_csv(rows: list[dict], output: Path) -> None:
    fields = [
        "batch", "source", "experiment", "fps", "resolution", "variant", "camera_model", "mesh_mode",
        "model_stage",
        "status", "runtime_s", "runtime_source", "evaluation_frames", "empty_fraction", "psnr_masked",
        "ssim_masked", "lpips_masked", "quality_index", "quality_per_minute", "failure_reason",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_method_report(rows: list[dict], output: Path) -> None:
    successful = [row for row in rows if row.get("status") == "success"]
    failed = [row for row in rows if row.get("status") != "success"]
    sts_rows = [row for row in rows if row.get("model_stage") == "sts"]
    sugar_rows = [row for row in rows if row.get("model_stage") == "sugar_coarse"]
    lines = [
        "# Matrix figures for the bachelor thesis",
        "",
        f"- Combined stage observations: **{len(rows)}**",
        f"- Complete stage observations: **{len(successful)}**",
        f"- Incomplete stage observations: **{len(failed)}**",
        f"- STS rows: **{len(sts_rows)}**; SuGaR-Coarse rows: **{len(sugar_rows)}**",
        "- Source batches: historical `matrix_full_pipe`, `matrix_rest`, and the completed `matrix_sugar_followup_12`",
        "- Image metrics: **object-masked-only**; model stage is recorded separately",
        "",
        "## Files used",
        "",
        "- `manifest.json`: completion status, FPS, variant and camera model",
        "- `parameters.json`: resolution, STS, SIFT and mesh parameters",
        "- `metrics/sts_masked.json`: PSNR, SSIM and LPIPS",
        "- `metrics/sugar_coarse_masked.json`: successful SuGaR-Coarse PSNR, SSIM and LPIPS",
        "- `masks/ideal/mask_coverage_report.json`: empty-mask fraction",
        "- `pipeline_run/run.md`: archived step durations for the time quotient",
        "- `run.log`: detailed failure reason and last reached stage",
        "- `matrix_overview_table.pdf`: grouped overview with PSNR, SSIM and LPIPS under 2 FPS, 5 FPS and Average",
        "- `matrix_combined_overview_table.pdf`: successful historical A/STS rows together with the completed SuGaR-Coarse rows",
        "- `matrix_sugar_overview_table.pdf`: grouped SuGaR-Coarse overview under 2 FPS, 5 FPS and Average",
        "- `matrix_sugar_status_table.pdf`, `matrix_sugar_psnr_table.pdf`, `matrix_sugar_ssim_table.pdf`, `matrix_sugar_lpips_table.pdf`, `matrix_sugar_time_quality_table.pdf`: stage-specific SuGaR-Coarse figures",
        "",
        "## Time/quality quotient",
        "",
        "The runtime is the sum of the archived STS workspace, STS training, object filtering, SuGaR meshing and centerline/postprocess steps. SAM3, COLMAP, rendering and metric-container time are not included because the matrix did not archive their per-experiment wall-clock intervals separately. The displayed relative quality index is the mean of min-max normalized PSNR and SSIM plus inverted LPIPS across complete runs. Failed routes are not ranked, even if an STS baseline metric exists.",
        "",
        "## Interpretation rule",
        "",
        "The previous SIMPLE_RADIAL-A rows are included for completeness and marked with `*`. SuGaR rows with `†` contain an STS baseline metric but their SuGaR route is incomplete; they must not be interpreted as successful SuGaR results. Green cells identify the best available result within an FPS column, not a proof of statistical significance.",
        "",
        "The `Average` column in the metric tables is the arithmetic mean of the 2-FPS and 5-FPS values for the same route and resolution. It is shown only when both FPS runs are complete and successful. A gray/orange dash marks an incomplete pair; this avoids presenting a one-sided average as a balanced FPS comparison.",
        "",
        "The `sts_masked.json` file in a failed historical `simple_radial_sugar` experiment is the STS baseline metric produced before the SuGaR-specific rendering step. It is not a successful SuGaR metric. The completed `matrix_sugar_followup_12` is evaluated from `sugar_coarse_masked.json`; its `sugar_refined_masked.json` files are explicitly skipped because no refined PLY was exported.",
        "",
        "Resolution caveat: lower-resolution runs are evaluated in their own downsampled image domain. Downsampling can smooth edge misalignment, high-frequency noise and mask-boundary errors, so higher PSNR/SSIM or lower LPIPS at low resolution does not prove better geometry. The time/quality quotient is therefore an exploratory screening result, not the primary scientific ranking. Runtime covers the archived STS-to-postprocess steps, not the complete SAM3/COLMAP/render/metric wall time.",
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, default=Path("data/10_runs/matrix_rest"))
    parser.add_argument("--previous", type=Path, default=Path("data/10_runs/matrix_full_pipe"))
    parser.add_argument("--sugar-followup", type=Path, default=Path("data/10_runs/matrix_sugar_followup_12"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/grafiken"))
    args = parser.parse_args()
    sts_rows = load_rows(args.current.resolve(), args.previous.resolve())
    sugar_rows = load_sugar_rows(args.sugar_followup.resolve())
    quality_indices(sts_rows)
    quality_indices(sugar_rows)
    rows = sts_rows + sugar_rows
    indexed = index_rows(sts_rows)
    sugar_indexed = index_rows(sugar_rows)
    combined_rows = [
        row for row in sts_rows
        if row.get("status") == "success"
        and row.get("variant") in {"simple_radial_a", "pinhole_a", "opencv_a"}
    ] + sugar_rows
    combined_indexed = index_rows(combined_rows)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(rows, output / "matrix_thesis_data.csv")
    write_method_report(rows, output / "matrix_thesis_method.md")
    files = {
        "matrix_overview_table.tex": overview_tex(indexed, sts_rows),
        "matrix_combined_overview_table.tex": overview_tex(
            combined_indexed,
            combined_rows,
            COMBINED_VARIANT_ORDER,
            COMBINED_VARIANT_LABELS,
            title="Kombinierte Overview: erfolgreiche STS-/A-Routen und SuGaR-Coarse",
            subtitle="Objektmaskierte PSNR-, SSIM- und LPIPS-Metriken; historische Fehlrouten ausgeschlossen; Average = Mittelwert aus 2 und 5 FPS",
        ),
        "matrix_status_table.tex": status_tex(indexed),
        "matrix_psnr_table.tex": metric_tex("psnr_masked", "Objektmaskiertes PSNR", indexed, sts_rows),
        "matrix_ssim_table.tex": metric_tex("ssim_masked", "Objektmaskiertes SSIM", indexed, sts_rows),
        "matrix_lpips_table.tex": metric_tex("lpips_masked", "Objektmaskiertes LPIPS", indexed, sts_rows),
        "matrix_time_quality_table.tex": efficiency_tex(indexed),
        "matrix_sugar_overview_table.tex": overview_tex(
            sugar_indexed,
            sugar_rows,
            SUGAR_VARIANT_ORDER,
            SUGAR_VARIANT_LABELS,
            title="SuGaR-Coarse-Folgematrix: PSNR, SSIM und LPIPS",
            subtitle="Erfolgreiche \\texttt{sugar\\_coarse}-Stufe; ausschließlich objektmaskierte Auswertung; Average = Mittelwert aus 2 und 5 FPS",
        ),
        "matrix_sugar_status_table.tex": status_tex(
            sugar_indexed,
            SUGAR_VARIANT_ORDER,
            SUGAR_VARIANT_LABELS,
            subtitle="Status der zwölf Läufe aus \\texttt{matrix\\_sugar\\_followup\\_12}",
        ),
        "matrix_sugar_psnr_table.tex": metric_tex(
            "psnr_masked",
            "SuGaR-Coarse: objektmaskiertes PSNR",
            sugar_indexed,
            sugar_rows,
            SUGAR_VARIANT_ORDER,
            SUGAR_VARIANT_LABELS,
            subtitle="SuGaR-Coarse-Folgematrix; ausschließlich objektmaskierte Auswertung",
        ),
        "matrix_sugar_ssim_table.tex": metric_tex(
            "ssim_masked",
            "SuGaR-Coarse: objektmaskiertes SSIM",
            sugar_indexed,
            sugar_rows,
            SUGAR_VARIANT_ORDER,
            SUGAR_VARIANT_LABELS,
            subtitle="SuGaR-Coarse-Folgematrix; ausschließlich objektmaskierte Auswertung",
        ),
        "matrix_sugar_lpips_table.tex": metric_tex(
            "lpips_masked",
            "SuGaR-Coarse: objektmaskiertes LPIPS",
            sugar_indexed,
            sugar_rows,
            SUGAR_VARIANT_ORDER,
            SUGAR_VARIANT_LABELS,
            subtitle="SuGaR-Coarse-Folgematrix; ausschließlich objektmaskierte Auswertung",
        ),
        "matrix_sugar_time_quality_table.tex": efficiency_tex(
            sugar_indexed,
            SUGAR_VARIANT_ORDER,
            SUGAR_VARIANT_LABELS,
            subtitle="SuGaR-Coarse: relativer Qualitätsindex pro Pipeline-Minute; vollständige End-to-End-Laufzeit",
        ),
    }
    for name, content in files.items():
        (output / name).write_text(content + "\n", encoding="utf-8")
    print(f"Prepared {len(rows)} combined experiment rows in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
