from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


METRIC_COLUMNS = (
    "file_acc",
    "symbol_acc",
    "family_acc",
    "repair_acc",
    "total_score",
    "canonical_file_acc",
    "canonical_symbol_acc",
    "canonical_family_acc",
    "canonical_repair_acc",
    "canonical_total_score",
    "avg_calls",
)


def load_run(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def build_report(run_files: list[Path]) -> str:
    summaries = [load_run(path) for path in run_files]
    lines = [
        "| program | split | file_acc | symbol_acc | family_acc | repair_acc | raw_total_score | canonical_file_acc | canonical_symbol_acc | canonical_family_acc | canonical_repair_acc | canonical_total_score | avg_calls |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in summaries:
        canonical_defaults = {
            "canonical_file_acc": summary["file_acc"],
            "canonical_symbol_acc": summary["symbol_acc"],
            "canonical_family_acc": summary["family_acc"],
            "canonical_repair_acc": summary["repair_acc"],
            "canonical_total_score": summary["total_score"],
        }
        values = []
        for column in METRIC_COLUMNS:
            if column in summary:
                values.append(summary[column])
            else:
                values.append(canonical_defaults[column])
        cells = [
            str(summary["program"]),
            str(summary["split"]),
            *[f"{float(value):.2f}" for value in values],
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m rlm_patchplan.report")
    parser.add_argument("--runs", required=True, nargs="+", help="Run JSON files from evaluate --out")
    parser.add_argument("--out", required=True, help="Markdown report path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report([Path(item) for item in args.runs])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
