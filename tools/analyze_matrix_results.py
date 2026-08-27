#!/usr/bin/env python3
"""Create reproducible, dependency-free reports and SVG figures for a matrix batch."""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
from pathlib import Path
from statistics import mean


COLORS = {
    "success": "#2e7d32",
    "failed": "#c62828",
    "missing": "#757575",
    "not_run": "#bdbdbd",
}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_metrics(exp: Path) -> dict:
    candidates = [exp / "metrics" / "sts_masked.json"]
    for path in candidates:
        data = load_json(path)
        if data:
            return data
    return {}


def read_coverage(exp: Path) -> dict:
    for path in (
        exp / "masks" / "ideal" / "mask_coverage_report.json",
        exp / "masks" / "raw" / "mask_coverage_report.json",
    ):
        data = load_json(path)
        if data:
            return data
    return {}


def read_pipeline_runtime(exp: Path) -> int | None:
    """Return summed STS-to-postprocess step time from the archived run report."""
    candidates = [exp / "pipeline_run" / "run.md"]
    candidates.extend(sorted((exp / "pipeline_run").glob("*/run.md")))
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        durations = re.findall(r"^\|[^|]+\|[^|]+\|[^|]+\|\s*(\d+)\s*\|", text, re.MULTILINE)
        if durations:
            return sum(int(value) for value in durations)
    return None


def failure_reason(exp: Path) -> str:
    log = exp / "run.log"
    if not log.is_file():
        return "no run log"
    text = log.read_text(encoding="utf-8", errors="replace")
    if "ModuleNotFoundError: No module named 'sugar_scene'" in text:
        return "SuGaR render helper import failed: sugar_scene unavailable"
    patterns = [
        r"(?:ModuleNotFoundError|ImportError):[^\n]+",
        r"(?:ValueError|RuntimeError|AssertionError|PermissionError):[^\n]+",
        r"(?:Error|ERROR):[^\n]+",
    ]
    matches = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text))
    return matches[-1].strip() if matches else "command failed (see run.log)"


def collect(batch: Path) -> list[dict]:
    rows = []
    for manifest_path in sorted(batch.glob("*/ */ */manifest.json".replace(" ", ""))):
        exp = manifest_path.parent
        manifest = load_json(manifest_path)
        params = load_json(exp / "parameters.json")
        metrics = read_metrics(exp)
        coverage = read_coverage(exp)
        runtime_s = read_pipeline_runtime(exp)
        fps = manifest.get("fps", params.get("fps", exp.parents[2].name.replace("fps", "")))
        row = {
            "fps": str(fps),
            "resolution": str(manifest.get("resolution_id", params.get("resolution_id", exp.parents[1].name))),
            "variant": str(manifest.get("variant", exp.name)),
            "camera_model": str(manifest.get("camera_model", params.get("camera_model", ""))),
            "mesh_mode": str(manifest.get("mesh_mode", params.get("mesh_mode", ""))),
            "status": str(manifest.get("status", "missing")),
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
            "failure_reason": "" if manifest.get("status") == "success" else failure_reason(exp),
            "experiment": str(exp.relative_to(batch)),
        }
        rows.append(row)
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    fields = list(rows[0]) if rows else ["experiment"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def esc(value: object) -> str:
    return html.escape(str(value))


def svg_status(rows: list[dict], path: Path) -> None:
    variants = sorted({r["variant"] for r in rows})
    resolutions = ["720p", "qhd", "low"]
    fps_values = sorted({r["fps"] for r in rows}, key=lambda x: float(x))
    cell_w, cell_h = 190, 58
    left, top = 150, 58
    width = left + len(resolutions) * cell_w + 20
    height = top + len(variants) * len(fps_values) * cell_h + 35
    lookup = {(r["fps"], r["variant"], r["resolution"]): r for r in rows}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<style>text{font-family:Arial,sans-serif;font-size:12px}.title{font-size:16px;font-weight:bold}.small{font-size:10px}</style>', '<rect width="100%" height="100%" fill="white"/>', f'<text x="10" y="24" class="title">Matrix status: {esc(path.stem)}</text>']
    for j, resolution in enumerate(resolutions):
        x = left + j * cell_w
        parts.append(f'<text x="{x + cell_w/2}" y="48" text-anchor="middle">{resolution}</text>')
    y = top
    for fps in fps_values:
        for variant in variants:
            label = f"{fps} FPS / {variant}"
            parts.append(f'<text x="{left-8}" y="{y + 34}" text-anchor="end" class="small">{esc(label)}</text>')
            for j, resolution in enumerate(resolutions):
                x = left + j * cell_w
                row = lookup.get((fps, variant, resolution))
                status = row["status"] if row else "not_run"
                color = COLORS.get(status, COLORS["missing"])
                text = "SUCCESS" if status == "success" else ("FAILED" if status == "failed" else "NOT RUN")
                parts += [f'<rect x="{x+2}" y="{y+5}" width="{cell_w-4}" height="{cell_h-10}" rx="6" fill="{color}"/>', f'<text x="{x+cell_w/2}" y="{y+29}" text-anchor="middle" fill="white" font-weight="bold">{text}</text>']
                if row and row["failure_reason"]:
                    parts.append(f'<text x="{x+cell_w/2}" y="{y+44}" text-anchor="middle" fill="white" class="small">{esc(row["failure_reason"][:25])}</text>')
            y += cell_h
    parts.append('</svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_metric(rows: list[dict], path: Path) -> None:
    success = [r for r in rows if r["status"] == "success" and r["psnr_masked"] != ""]
    width, height = 1200, 560
    left, right, top, bottom = 90, 30, 70, 90
    plot_w, plot_h = width-left-right, height-top-bottom
    max_value = max([float(r["psnr_masked"]) for r in success] or [1])
    max_value *= 1.08
    bar_w = max(8, plot_w / max(1, len(success)) - 8)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">', '<style>text{font-family:Arial,sans-serif;font-size:11px}.title{font-size:16px;font-weight:bold}.axis{stroke:#444}.grid{stroke:#ddd}</style>', '<rect width="100%" height="100%" fill="white"/>', '<text x="20" y="28" class="title">Object-masked PSNR of successful runs</text>']
    for tick in range(0, 5):
        value = max_value * tick / 4
        y = top + plot_h - plot_h * value / max_value
        parts += [f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="grid"/>', f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end">{value:.1f}</text>']
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" class="axis"/>')
    for i, row in enumerate(sorted(success, key=lambda r: (float(r["fps"]), r["variant"], r["resolution"]))):
        value = float(row["psnr_masked"])
        x = left + i * (plot_w / len(success)) + 4
        h = plot_h * value / max_value
        y = top + plot_h - h
        color = {"PINHOLE":"#1565c0", "OPENCV":"#ef6c00", "SIMPLE_RADIAL":"#2e7d32"}.get(row["camera_model"], "#616161")
        parts += [f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}"/>', f'<text transform="translate({x+bar_w/2:.1f},{top+plot_h+14}) rotate(55)" text-anchor="start">{esc(row["fps"]+"/"+row["resolution"]+"/"+row["variant"])}</text>', f'<text x="{x+bar_w/2:.1f}" y="{y-4:.1f}" text-anchor="middle">{value:.2f}</text>']
    parts.append(f'<text x="20" y="{height-20}">Color: green=SIMPLE_RADIAL, blue=PINHOLE, orange=OPENCV. Metric scope: object-masked-only.</text></svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_coverage(rows: list[dict], path: Path) -> None:
    measured = [r for r in rows if r["empty_fraction"] != ""]
    width, height = 1200, 500
    left, right, top, bottom = 90, 30, 70, 90
    plot_w, plot_h = width - left - right, height - top - bottom
    bar_w = max(8, plot_w / max(1, len(measured)) - 8)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<style>text{font-family:Arial,sans-serif;font-size:11px}.title{font-size:16px;font-weight:bold}.axis{stroke:#444}.grid{stroke:#ddd}</style>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="20" y="28" class="title">Empty-mask fraction by run</text>',
    ]
    for tick in range(0, 4):
        value = 0.30 * tick / 3
        y = top + plot_h - plot_h * value / 0.30
        parts += [
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="grid"/>',
            f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end">{value:.0%}</text>',
        ]
    threshold_y = top
    parts.append(f'<line x1="{left}" y1="{threshold_y}" x2="{width-right}" y2="{threshold_y}" stroke="#c62828" stroke-dasharray="5,4"/>')
    parts.append(f'<text x="{width-right-4}" y="{threshold_y-5}" text-anchor="end" fill="#c62828">30% abort threshold</text>')
    for i, row in enumerate(sorted(measured, key=lambda r: (float(r["fps"]), r["variant"], r["resolution"]))):
        value = min(0.30, float(row["empty_fraction"]))
        x = left + i * (plot_w / len(measured)) + 4
        h = plot_h * value / 0.30
        y = top + plot_h - h
        color = COLORS.get(row["status"], COLORS["missing"])
        label = f'{row["fps"]}/{row["resolution"]}/{row["variant"]}'
        parts += [
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(1,h):.1f}" fill="{color}"/>',
            f'<text transform="translate({x+bar_w/2:.1f},{top+plot_h+14}) rotate(55)" text-anchor="start">{esc(label)}</text>',
            f'<text x="{x+bar_w/2:.1f}" y="{max(top+12,y-4):.1f}" text-anchor="middle">{value:.1%}</text>',
        ]
    parts.append(f'<text x="20" y="{height-20}">Red bars indicate failed runs; green/blue/orange-gray bars indicate the archived run status. Threshold is the pre-run mask guard.</text></svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def write_report(rows: list[dict], batch: Path, path: Path) -> None:
    successful = [r for r in rows if r["status"] == "success"]
    failed = [r for r in rows if r["status"] != "success"]
    lines = [f"# Matrix analysis: {batch.name}", "", f"- Experiments found: **{len(rows)}**", f"- Successful: **{len(successful)}**", f"- Failed/not complete: **{len(failed)}**", "- Metric scope: **object-masked-only**", "", "## Interpretation", "", "The primary comparison factors are camera model, FPS, and resolution. Mesh route is a separate factor: `sugar_coarse` failures must not be interpreted as camera-model failures. `simple_radial_a` was intentionally excluded from this follow-up batch because it was already tested in the previous batch.", "", "## Successful runs", "", "| FPS | Resolution | Variant | Camera | PSNR masked | SSIM masked | LPIPS masked | Empty-mask fraction |", "|---:|---|---|---|---:|---:|---:|---:|"]
    for r in sorted(successful, key=lambda x: (float(x["fps"]), x["variant"], x["resolution"])):
        def f(k): return "" if r[k] == "" else f"{float(r[k]):.4f}"
        lines.append(f"| {r['fps']} | {r['resolution']} | {r['variant']} | {r['camera_model']} | {f('psnr_masked')} | {f('ssim_masked')} | {f('lpips_masked')} | {f('empty_fraction')} |")
    lines += ["", "## Failed runs", "", "| FPS | Resolution | Variant | Reason |", "|---:|---|---|---|"]
    for r in sorted(failed, key=lambda x: (float(x["fps"]), x["variant"], x["resolution"])):
        lines.append(f"| {r['fps']} | {r['resolution']} | {r['variant']} | {r['failure_reason']} |")
    lines += ["", "## Files used", "", "- `manifest.json`: completion status and route", "- `parameters.json`: FPS, resolution, camera model, STS and mesh settings", "- `metrics/sts_masked.json`: object-only PSNR/SSIM/LPIPS", "- `masks/{raw,ideal}/*coverage_report.json`: mask coverage", "- `run.log`: failure reasons and stage completion", "- `live/centerline/` and `live/gis/`: postprocess outputs", "", "## Bachelor thesis recommendation", "", "Use status as a separate figure/table, compare successful runs by camera model × FPS × resolution, and report `sugar_coarse` failures in a separate robustness/failure analysis. Do not rank a failed route using missing image metrics."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    batch = args.batch.resolve()
    output = (args.output_dir or batch / "analysis").resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = collect(batch)
    if not rows:
        raise SystemExit(f"No experiment manifests found under {batch}")
    write_csv(rows, output / "matrix_results.csv")
    write_report(rows, batch, output / "matrix_analysis.md")
    svg_status(rows, output / "matrix_status.svg")
    svg_metric(rows, output / "matrix_psnr_masked.svg")
    svg_coverage(rows, output / "matrix_mask_coverage.svg")
    print(f"Wrote analysis for {len(rows)} experiments to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
