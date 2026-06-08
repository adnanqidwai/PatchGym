from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_task_summaries(run_root: Path) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for child in sorted(run_root.iterdir()):
        if not child.is_dir():
            continue
        summary_path = child / "summary.json"
        if summary_path.is_file():
            summaries.append(json.loads(summary_path.read_text(encoding="utf-8")))
    return summaries


def build_aggregate_summary(run_root: Path) -> dict[str, Any]:
    aggregate_path = run_root / "summary.json"
    if aggregate_path.is_file():
        return json.loads(aggregate_path.read_text(encoding="utf-8"))

    summaries = _load_task_summaries(run_root)
    if not summaries:
        return {
            "agent": "unknown",
            "tasks": 0,
            "solve_rate": 0.0,
            "visible_pass_hidden_fail": 0,  # nosec B105
        }

    agent = summaries[0]["agent"]
    solved_count = sum(1 for item in summaries if item["verification"]["solved"])
    visible_pass_hidden_fail = sum(
        1
        for item in summaries
        if item["verification"]["public_tests"]["passed"]
        and not item["verification"]["hidden_tests"]["passed"]
    )
    total = len(summaries)
    return {
        "agent": agent,
        "tasks": total,
        "solve_rate": (solved_count / total) if total else 0.0,
        "visible_pass_hidden_fail": visible_pass_hidden_fail,
    }


def write_markdown_report(run_root: str | Path, out_path: str | Path) -> None:
    run_path = Path(run_root)
    aggregate = build_aggregate_summary(run_path)
    report_path = Path(out_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "| agent | tasks | solve_rate | visible_pass_hidden_fail |",
        "| --- | --- | --- | --- |",
        (
            f"| {aggregate['agent']} | {aggregate['tasks']} | "
            f"{aggregate['solve_rate']:.2f} | {aggregate['visible_pass_hidden_fail']} |"
        ),
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
