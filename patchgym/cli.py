from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from patchgym.agents.openai_compatible import DEFAULT_OPENAI_COMPATIBLE_MODEL
from patchgym.env import PatchGymEnv, PatchGymEnvConfig
from patchgym.generate import generate_tasks
from patchgym.runner import run_suite, run_task
from patchgym.summarize import write_markdown_report
from patchgym.verify import verify_task


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patchgym")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate tasks")
    generate_parser.add_argument("--out", required=True, help="Output directory")
    generate_parser.add_argument(
        "--templates",
        required=True,
        help="Comma-separated template names (parser, cli, sqlite)",
    )
    generate_parser.add_argument("--n", type=int, required=True, help="Tasks per template")
    generate_parser.add_argument("--seed", type=int, required=True, help="Base seed")
    generate_parser.add_argument(
        "--bug-family",
        default="boundary",
        help="Bug family to generate (boundary, contract, integration, regression_trap)",
    )

    verify_parser = subparsers.add_parser("verify", help="Verify a task repository")
    verify_parser.add_argument("--task", required=True, help="Path to task directory")
    verify_parser.add_argument(
        "--repo",
        help="Path to repository snapshot (defaults to task/repo)",
    )
    verify_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON summary to stdout",
    )

    run_parser = subparsers.add_parser("run", help="Run a single task with an agent")
    run_parser.add_argument("--task", required=True, help="Path to task directory")
    run_parser.add_argument("--agent", required=True, help="Agent name (noop, command, openai-compatible)")
    run_parser.add_argument("--out", required=True, help="Run output root directory")
    run_parser.add_argument(
        "--agent-command",
        help="Command argv string for the command agent, parsed with shlex and executed without a shell",
    )
    run_parser.add_argument(
        "--model",
        default=DEFAULT_OPENAI_COMPATIBLE_MODEL,
        help=f"Model name for --agent openai-compatible (default: {DEFAULT_OPENAI_COMPATIBLE_MODEL})",
    )
    run_parser.add_argument(
        "--api-base",
        help="Optional OpenAI-compatible API base URL. Defaults to OPENAI_BASE_URL.",
    )
    run_parser.add_argument(
        "--max-tokens",
        type=int,
        default=4096,
        help="Maximum output tokens for --agent openai-compatible",
    )
    run_parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for --agent openai-compatible",
    )

    suite_parser = subparsers.add_parser("run-suite", help="Run multiple tasks")
    suite_parser.add_argument("--tasks", required=True, help="Directory containing tasks")
    suite_parser.add_argument("--agent", required=True, help="Agent name (noop, command, openai-compatible)")
    suite_parser.add_argument("--out", required=True, help="Run output root directory")
    suite_parser.add_argument("--limit", type=int, help="Maximum number of tasks to run")
    suite_parser.add_argument(
        "--agent-command",
        help="Command argv string for the command agent, parsed with shlex and executed without a shell",
    )
    suite_parser.add_argument(
        "--model",
        default=DEFAULT_OPENAI_COMPATIBLE_MODEL,
        help=f"Model name for --agent openai-compatible (default: {DEFAULT_OPENAI_COMPATIBLE_MODEL})",
    )
    suite_parser.add_argument(
        "--api-base",
        help="Optional OpenAI-compatible API base URL. Defaults to OPENAI_BASE_URL.",
    )
    suite_parser.add_argument(
        "--max-tokens",
        type=int,
        default=4096,
        help="Maximum output tokens for --agent openai-compatible",
    )
    suite_parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for --agent openai-compatible",
    )

    summarize_parser = subparsers.add_parser("summarize", help="Summarize a run directory")
    summarize_parser.add_argument("run_root", help="Path to run output root")
    summarize_parser.add_argument("--out", required=True, help="Markdown report path")

    episode_parser = subparsers.add_parser("episode", help="Replay JSONL actions in a PatchGym env episode")
    episode_parser.add_argument("--task", required=True, help="Path to task directory")
    episode_parser.add_argument(
        "--actions",
        required=True,
        help="JSONL file with read_file/write_file/run_public_tests/submit_patch actions",
    )
    episode_parser.add_argument("--out", required=True, help="Episode output root directory")
    episode_parser.add_argument(
        "--reward-mode",
        choices=["sparse", "layered"],
        default="sparse",
        help="Terminal reward mode for submit_patch",
    )
    episode_parser.add_argument("--json", action="store_true", help="Print full episode summary as JSON")

    return parser


def _load_actions(path: str | Path) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"Action line {line_number} must be a JSON object")
            actions.append(payload)
    return actions


def run_episode_script(
    *,
    task_dir: str,
    actions_path: str,
    out_dir: str,
    reward_mode: str,
) -> dict[str, object]:
    env = PatchGymEnv(
        config=PatchGymEnvConfig(
            work_dir=out_dir,
            reward_mode=reward_mode,
            include_repo_files=False,
        )
    )
    env.reset(task_dir)
    steps: list[dict[str, object]] = []
    for action in _load_actions(actions_path):
        result = env.step(action)
        steps.append(result.to_record())
        if result.done:
            break

    final = steps[-1] if steps else None
    summary = {
        "task_id": env.metadata["task_id"],
        "steps": len(steps),
        "repo_dir": str(env.repo_dir),
        "trace_path": str(env.trace_path),
        "reward": final["reward"] if final else 0.0,
        "terminated": final["terminated"] if final else False,
        "truncated": final["truncated"] if final else False,
        "verification": final["info"].get("verification") if final else None,
        "step_records": steps,
    }
    summary_path = Path(out_dir) / env.metadata["task_id"] / "episode_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        templates = [item.strip() for item in args.templates.split(",") if item.strip()]
        generate_tasks(
            out_dir=args.out,
            templates=templates,
            n=args.n,
            seed=args.seed,
            bug_family=args.bug_family,
        )
        return 0

    if args.command == "verify":
        return verify_task(task_dir=args.task, repo_dir=args.repo, as_json=args.json)

    if args.command == "run":
        run_task(
            task_dir=args.task,
            agent=args.agent,
            out_dir=args.out,
            agent_command=args.agent_command,
            model=args.model,
            api_base=args.api_base,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        return 0

    if args.command == "run-suite":
        run_suite(
            tasks_dir=args.tasks,
            agent=args.agent,
            out_dir=args.out,
            limit=args.limit,
            agent_command=args.agent_command,
            model=args.model,
            api_base=args.api_base,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        return 0

    if args.command == "summarize":
        write_markdown_report(run_root=args.run_root, out_path=args.out)
        return 0

    if args.command == "episode":
        summary = run_episode_script(
            task_dir=args.task,
            actions_path=args.actions,
            out_dir=args.out,
            reward_mode=args.reward_mode,
        )
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(
                f"task_id={summary['task_id']} reward={summary['reward']} "
                f"terminated={summary['terminated']} truncated={summary['truncated']}"
            )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
