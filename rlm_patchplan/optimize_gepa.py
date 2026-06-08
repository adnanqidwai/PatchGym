from __future__ import annotations

import argparse
import json
from pathlib import Path

from rlm_patchplan.evaluate import load_tasks
from rlm_patchplan.metrics import patchplan_metric
from rlm_patchplan.programs import configure_dspy, make_dspy_lm, make_rlm_patch_planner, require_dspy, to_dspy_examples


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m rlm_patchplan.optimize_gepa")
    parser.add_argument("--data", required=True, help="Task JSONL path")
    parser.add_argument("--artifact", default="artifacts/optimized_patchplanner.json")
    parser.add_argument("--log-dir", default="runs/gepa_patchplan")
    parser.add_argument(
        "--provider",
        default="openai",
        choices=["openai", "openai-compatible"],
        help="Student model provider",
    )
    parser.add_argument("--model", help="Student model; provider default is used when omitted")
    parser.add_argument("--api-base", help="Optional student OpenAI-compatible API base URL override")
    parser.add_argument(
        "--reflection-provider",
        choices=["openai", "openai-compatible"],
        help="Reflection model provider; defaults to --provider",
    )
    parser.add_argument("--reflection-model", help="Reflection model; provider default is used when omitted")
    parser.add_argument("--reflection-api-base", help="Optional reflection OpenAI-compatible API base URL override")
    parser.add_argument("--train", type=int, default=40, help="Maximum train examples to use")
    parser.add_argument("--dev", type=int, default=20, help="Maximum dev examples to use")
    parser.add_argument("--rlm-max-iterations", type=int, default=6, help="Maximum RLM REPL iterations")
    parser.add_argument("--rlm-max-llm-calls", type=int, default=8, help="Maximum RLM sub-LLM calls")
    parser.add_argument("--auto", choices=["light", "medium", "heavy"], default="light")
    parser.add_argument("--max-metric-calls", type=int, help="Override GEPA auto budget")
    parser.add_argument("--seed", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dspy = require_dspy()
    configure_dspy(args.model, provider=args.provider, api_base=args.api_base)

    tasks = load_tasks(args.data)
    train_tasks = [task for task in tasks if task.split == "train"][: args.train]
    dev_tasks = [task for task in tasks if task.split == "dev"][: args.dev]
    if not train_tasks:
        raise ValueError("No train examples found")
    if not dev_tasks:
        raise ValueError("No dev examples found")

    student = make_rlm_patch_planner(
        max_iterations=args.rlm_max_iterations,
        max_llm_calls=args.rlm_max_llm_calls,
    )
    reflection_provider = args.reflection_provider or args.provider
    optimizer_kwargs = {
        "metric": patchplan_metric,
        "reflection_lm": make_dspy_lm(
            args.reflection_model,
            provider=reflection_provider,
            api_base=args.reflection_api_base,
            temperature=1.0,
            max_tokens=32000,
        ),
        "track_stats": True,
        "log_dir": args.log_dir,
        "seed": args.seed,
    }
    if args.max_metric_calls is not None:
        optimizer_kwargs["max_metric_calls"] = args.max_metric_calls
    else:
        optimizer_kwargs["auto"] = args.auto

    optimizer = dspy.GEPA(**optimizer_kwargs)
    optimized = optimizer.compile(
        student,
        trainset=to_dspy_examples(train_tasks),
        valset=to_dspy_examples(dev_tasks),
    )

    artifact_path = Path(args.artifact)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    optimized.save(str(artifact_path))

    metadata = {
        "artifact": str(artifact_path),
        "log_dir": args.log_dir,
        "train_examples": len(train_tasks),
        "dev_examples": len(dev_tasks),
        "provider": args.provider,
        "model": args.model,
        "reflection_provider": reflection_provider,
        "reflection_model": args.reflection_model,
        "rlm_max_iterations": args.rlm_max_iterations,
        "rlm_max_llm_calls": args.rlm_max_llm_calls,
    }
    metadata_path = artifact_path.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
