from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rlm_patchplan.metrics import FIELD_WEIGHTS, score_patchplan
from rlm_patchplan.programs import build_program
from rlm_patchplan.schema import PatchPlanPrediction, PatchPlanTask


def load_tasks(path: str | Path) -> list[PatchPlanTask]:
    tasks = []
    with Path(path).open() as handle:
        for line in handle:
            if line.strip():
                tasks.append(PatchPlanTask.from_record(json.loads(line)))
    return tasks


def _predict(program: Any, task: PatchPlanTask) -> PatchPlanPrediction:
    if hasattr(program, "predict"):
        return PatchPlanPrediction.from_obj(program.predict(task))
    return PatchPlanPrediction.from_obj(
        program(
            issue=task.issue,
            failing_test_output=task.failing_test_output,
            repo_files=task.repo_files,
        )
    )


def _call_count(prediction: Any) -> int:
    trajectory = getattr(prediction, "trajectory", None)
    if isinstance(trajectory, list):
        return len(trajectory)
    return 1


def evaluate_tasks(tasks: list[PatchPlanTask], program: Any, *, program_name: str, split: str) -> dict[str, Any]:
    selected = [task for task in tasks if task.split == split]
    if not selected:
        raise ValueError(f"No examples found for split {split!r}")

    component_counts = {field: 0 for field in FIELD_WEIGHTS}
    canonical_component_counts = {field: 0 for field in FIELD_WEIGHTS}
    scores: list[float] = []
    canonical_scores: list[float] = []
    calls: list[int] = []
    examples: list[dict[str, Any]] = []

    for task in selected:
        raw_pred = program.predict(task) if hasattr(program, "predict") else program(
            issue=task.issue,
            failing_test_output=task.failing_test_output,
            repo_files=task.repo_files,
        )
        pred = PatchPlanPrediction.from_obj(raw_pred)
        scored = score_patchplan(task, pred)
        canonical_scored = score_patchplan(task, pred, canonicalize=True)

        for field, correct in scored.components.items():
            component_counts[field] += int(correct)
        for field, correct in canonical_scored.components.items():
            canonical_component_counts[field] += int(correct)
        scores.append(scored.score)
        canonical_scores.append(canonical_scored.score)
        calls.append(_call_count(raw_pred))
        examples.append(
            {
                "task_id": task.task_id,
                "prediction": pred.to_record(),
                "score": scored.score,
                "components": scored.components,
                "feedback": scored.feedback,
                "canonical_score": canonical_scored.score,
                "canonical_components": canonical_scored.components,
                "canonical_feedback": canonical_scored.feedback,
            }
        )

    count = len(selected)
    return {
        "program": program_name,
        "split": split,
        "example_count": count,
        "file_acc": component_counts["bug_file"] / count,
        "symbol_acc": component_counts["bug_symbol"] / count,
        "family_acc": component_counts["bug_family"] / count,
        "repair_acc": component_counts["repair_op"] / count,
        "total_score": sum(scores) / count,
        "canonical_file_acc": canonical_component_counts["bug_file"] / count,
        "canonical_symbol_acc": canonical_component_counts["bug_symbol"] / count,
        "canonical_family_acc": canonical_component_counts["bug_family"] / count,
        "canonical_repair_acc": canonical_component_counts["repair_op"] / count,
        "canonical_total_score": sum(canonical_scores) / count,
        "avg_calls": sum(calls) / count,
        "examples": examples,
    }


def _format_table(summary: dict[str, Any]) -> str:
    header = (
        "program              file_acc  symbol_acc  family_acc  repair_acc  "
        "raw_total  canonical_total  avg_calls"
    )
    row = (
        f"{summary['program']:<20}"
        f"{summary['file_acc']:<10.2f}"
        f"{summary['symbol_acc']:<12.2f}"
        f"{summary['family_acc']:<12.2f}"
        f"{summary['repair_acc']:<12.2f}"
        f"{summary['total_score']:<11.2f}"
        f"{summary['canonical_total_score']:<17.2f}"
        f"{summary['avg_calls']:.1f}"
    )
    return f"{header}\n{row}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m rlm_patchplan.evaluate")
    parser.add_argument("--program", choices=["heuristic", "cot", "rlm", "optimized"], required=True)
    parser.add_argument("--data", required=True, help="Task JSONL path")
    parser.add_argument("--split", default="test", choices=["train", "dev", "test"])
    parser.add_argument(
        "--provider",
        default="openai",
        choices=["openai", "openai-compatible"],
        help="LLM provider for DSPy programs",
    )
    parser.add_argument("--model", help="DSPy model for cot/rlm/optimized; provider default is used when omitted")
    parser.add_argument("--api-base", help="Optional OpenAI-compatible API base URL override")
    parser.add_argument("--max-tokens", type=int, default=4000, help="Maximum tokens per DSPy LM call")
    parser.add_argument("--rlm-max-iterations", type=int, default=6, help="Maximum RLM REPL iterations")
    parser.add_argument("--rlm-max-llm-calls", type=int, default=8, help="Maximum RLM sub-LLM calls")
    parser.add_argument("--artifact", help="Optimized DSPy program artifact for --program optimized")
    parser.add_argument("--out", help="Optional path for full run JSON")
    parser.add_argument("--json", action="store_true", help="Print summary as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tasks = load_tasks(args.data)
    program = build_program(
        args.program,
        model=args.model,
        provider=args.provider,
        api_base=args.api_base,
        max_tokens=args.max_tokens,
        rlm_max_iterations=args.rlm_max_iterations,
        rlm_max_llm_calls=args.rlm_max_llm_calls,
        artifact=args.artifact,
    )
    summary = evaluate_tasks(tasks, program, program_name=args.program, split=args.split)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2) + "\n")

    printable = {key: value for key, value in summary.items() if key != "examples"}
    if args.json:
        print(json.dumps(printable, indent=2))
    else:
        print(_format_table(printable))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
