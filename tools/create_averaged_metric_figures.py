#!/usr/bin/env python3
"""Create averaged metric graphics from historical and repeat run archives."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from create_metric_diagnostic_figures import (  # noqa: E402
    METRICS,
    all_metric_ranges,
    boxplots_tex,
    delta_tex,
    experiment_rows,
    number,
    overview_tex,
    paired_delta_rows,
    runtime_scatter_tex,
    sort_key,
    write_graphics_data_bundle,
    write_per_frame_csv,
    write_rows_csv,
)

FIXED_BOXPLOT_RANGES = {
    "psnr_masked": (10.0, 40.0),
    "ssim_masked": (0.1, 1.0),
    "lpips_masked": (0.0, 0.4),
}


def key(row: dict) -> tuple[str, str, str, str]:
    return (row["camera_model"], row["fps"], row["resolution"], row["stage"])


def average_rows(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        if not row.get("complete") or any(row.get(metric) is None for metric in METRICS):
            continue
        grouped[key(row)].append(row)
    result = []
    for group_key, items in sorted(grouped.items(), key=lambda pair: pair[0]):
        first = items[0]
        row = dict(first)
        row["batch"] = "mean_historical_plus_repeat"
        row["experiment"] = f"mean/{first['camera_short']}/{first['fps']}fps/{first['resolution']}/{first['stage']}"
        row["complete"] = True
        row["source_run_count"] = len(items)
        row["source_batches"] = ";".join(sorted({item["batch"] for item in items}))
        for metric in METRICS:
            row[metric] = sum(float(item[metric]) for item in items) / len(items)
        runtimes = [item["runtime_s"] for item in items if item.get("runtime_s") is not None]
        row["runtime_s"] = sum(runtimes) / len(runtimes) if runtimes else None
        row["evaluation_frame_count"] = round(sum(float(item["evaluation_frame_count"]) for item in items if item.get("evaluation_frame_count") is not None) / len(items))
        row["per_frame"] = [
            {"frame": f"{item['batch']}:{point.get('frame', '')}", **{metric: point.get(metric) for metric in METRICS}}
            for item in items for point in item.get("per_frame", [])
        ]
        result.append(row)
    return sorted(result, key=sort_key)


def write_mean_csv(rows: list[dict], path: Path) -> None:
    fields = ["camera_model", "camera_short", "stage", "route", "fps", "resolution", "source_run_count", "source_batches", "evaluation_frame_count", "runtime_s", *METRICS]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-full", type=Path, required=True)
    parser.add_argument("--historical-rest", type=Path, required=True)
    parser.add_argument("--historical-sugar", type=Path, required=True)
    parser.add_argument("--repeat", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    historical_sts = experiment_rows(args.historical_full, "sts_masked.json", "sts") + experiment_rows(args.historical_rest, "sts_masked.json", "sts")
    repeat_sts = experiment_rows(args.repeat, "sts_masked.json", "sts")
    historical_sugar = experiment_rows(args.historical_sugar, "sugar_coarse_masked.json", "sugar_coarse")
    repeat_sugar = experiment_rows(args.repeat, "sugar_coarse_masked.json", "sugar_coarse")
    sts_rows = average_rows(historical_sts + repeat_sts)
    sugar_rows = average_rows(historical_sugar + repeat_sugar)
    complete_sts = [row for row in sts_rows if row["mesh_mode"] == "original_gs"]
    complete_sugar = list(sugar_rows)

    write_mean_csv(sts_rows, args.output_dir / "sts_mean.csv")
    write_mean_csv(sugar_rows, args.output_dir / "sugar_coarse_mean.csv")
    write_per_frame_csv(complete_sts, args.output_dir / "sts_mean_per_frame.csv")
    write_per_frame_csv(complete_sugar, args.output_dir / "sugar_coarse_mean_per_frame.csv")
    write_graphics_data_bundle(sts_rows, sugar_rows, [], args.output_dir)
    bundle = args.output_dir / "Datengrundlage"
    for name in ("sts_mean.csv", "sugar_coarse_mean.csv", "sts_mean_per_frame.csv", "sugar_coarse_mean_per_frame.csv"):
        shutil.copy2(args.output_dir / name, bundle / name)

    ranges = all_metric_ranges(sts_rows, sugar_rows)
    (args.output_dir / "sts_mean_overview.tex").write_text(
        overview_tex(complete_sts, "STS: gemittelte objektmaskierte Bildmetriken", "Mittelwerte aus historischen und Repeat-Läufen", ranges, "sts"),
        encoding="utf-8",
    )
    (args.output_dir / "sugar_coarse_mean_overview.tex").write_text(
        overview_tex(complete_sugar, "SuGaR-Coarse: gemittelte objektmaskierte Bildmetriken", "Mittelwerte aus historischer Folgematrix und Repeat-Läufen", ranges, "sugar_coarse"),
        encoding="utf-8",
    )
    (args.output_dir / "sts_mean_per_frame_boxplots.tex").write_text(boxplots_tex(complete_sts, "STS: Mittelwerte und gepoolte Einzelansichten", "Mittel über historische und Repeat-Läufe; Farben der Boxen kodieren das Kameramodell", FIXED_BOXPLOT_RANGES), encoding="utf-8")
    (args.output_dir / "sugar_coarse_mean_per_frame_boxplots.tex").write_text(boxplots_tex(complete_sugar, "SuGaR-Coarse: Mittelwerte und gepoolte Einzelansichten", "Mittel über historische und Repeat-Läufe; Farben der Boxen kodieren das Kameramodell", FIXED_BOXPLOT_RANGES), encoding="utf-8")

    delta = []
    sts_index = {key(row): row for row in sts_rows}
    for sugar in sugar_rows:
        sts = sts_index.get(key({**sugar, "stage": "sts"}))
        if not sts:
            continue
        delta.append({**sugar, **{f"delta_{metric}": sugar[metric] - sts[metric] for metric in METRICS}})
    with (args.output_dir / "sugar_coarse_vs_sts_mean_delta.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["camera_model", "camera_short", "fps", "resolution", *[f"delta_{metric}" for metric in METRICS]]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in delta)
    shutil.copy2(args.output_dir / "sugar_coarse_vs_sts_mean_delta.csv", bundle / "sugar_coarse_vs_sts_mean_delta.csv")
    (args.output_dir / "sugar_coarse_vs_sts_mean_delta.tex").write_text(delta_tex(delta, "SuGaR-Coarse minus STS: Mittelwerte", "Gepaarte Differenz der gemittelten Renderingmetriken"), encoding="utf-8")
    (args.output_dir / "metric_vs_runtime_mean.tex").write_text(runtime_scatter_tex(complete_sts, complete_sugar, "Gemittelte Bildmetriken im Verhältnis zur Laufzeit", "Mittelwerte aus historischen und Repeat-Läufen", ranges), encoding="utf-8")
    summary = {"schema": "scan2bim-metric-mean-v1", "sources": ["historical matrix_full_pipe", "historical matrix_rest", "matrix_sugar_followup_12", "matrix_repeat_20260812"], "aggregation": "arithmetic mean per camera x FPS x resolution x stage; per_frame values pooled for boxplots", "sts_rows": len(sts_rows), "sugar_rows": len(sugar_rows), "metrics": list(METRICS)}
    (args.output_dir / "mean_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote averaged graphics data: STS={len(sts_rows)}, SuGaR={len(sugar_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
