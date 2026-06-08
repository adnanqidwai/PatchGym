from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

from patchgym.agents.openai_compatible import (
    DEFAULT_OPENAI_COMPATIBLE_MODEL,
    OpenAICompatibleClient,
    run_openai_compatible_agent,
)
from patchgym.verify import build_verification_summary


def _append_trace(trace_path: Path, event: str, **extra: Any) -> None:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": event, **extra}) + "\n")


def _prepare_final_repo(task_dir: Path, task_run_dir: Path) -> Path:
    final_repo = task_run_dir / "final_repo"
    if final_repo.exists():
        shutil.rmtree(final_repo)
    shutil.copytree(task_dir / "repo", final_repo)
    return final_repo


def run_task(
    task_dir: str | Path,
    agent: str,
    out_dir: str | Path,
    *,
    agent_command: str | None = None,
    model: str = DEFAULT_OPENAI_COMPATIBLE_MODEL,
    openai_client: OpenAICompatibleClient | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    max_tokens: int | None = 4096,
    temperature: float = 0.0,
) -> dict[str, Any]:
    task_path = Path(task_dir)
    run_root = Path(out_dir)
    metadata = json.loads((task_path / "metadata.json").read_text())
    task_id = metadata["task_id"]
    task_run_dir = run_root / task_id
    task_run_dir.mkdir(parents=True, exist_ok=True)

    trace_path = task_run_dir / "trace.jsonl"
    if trace_path.exists():
        trace_path.unlink()

    _append_trace(trace_path, "run_started", task_id=task_id, agent=agent)
    issue_path = task_path / "issue.md"
    _append_trace(
        trace_path,
        "issue_loaded",
        issue_path=str(issue_path),
        issue_bytes=issue_path.stat().st_size,
    )

    final_repo = _prepare_final_repo(task_path, task_run_dir)
    agent_result: dict[str, Any]

    if agent == "noop":
        _append_trace(trace_path, "agent_noop")
        agent_result = {"status": "noop"}
    elif agent == "command":
        if not agent_command:
            raise ValueError("command agent requires --agent-command")
        env = os.environ.copy()
        env["PATCHGYM_TASK_DIR"] = str(task_path.resolve())
        env["PATCHGYM_REPO_DIR"] = str(final_repo.resolve())
        env["PATCHGYM_TRACE_PATH"] = str(trace_path.resolve())
        # The command agent intentionally executes caller-supplied local tools in a copied task repo.
        completed = subprocess.run(  # nosec B603
            shlex.split(agent_command),
            cwd=str(final_repo),
            env=env,
            capture_output=True,
            text=True,
        )
        agent_result = {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        _append_trace(trace_path, "agent_command_finished", returncode=completed.returncode)
    elif agent in {"openai", "openai-compatible"}:
        _append_trace(trace_path, "agent_openai_started", model=model)
        try:
            agent_result = run_openai_compatible_agent(
                task_path,
                final_repo,
                model_name=model,
                client=openai_client,
                api_key=api_key,
                base_url=api_base,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            agent_result = {
                "status": "error",
                "model": model,
                "error": str(exc),
                "edits_applied": [],
                "rejected_edits": [],
            }
            _append_trace(trace_path, "agent_openai_failed", error=str(exc))
        else:
            _append_trace(
                trace_path,
                "agent_openai_response_received",
                response_chars=agent_result["response_chars"],
                input_tokens=agent_result["input_tokens"],
                output_tokens=agent_result["output_tokens"],
            )
            for path in agent_result["edits_applied"]:
                _append_trace(trace_path, "agent_openai_edit_applied", path=path)
            for rejected in agent_result["rejected_edits"]:
                _append_trace(
                    trace_path,
                    "agent_openai_edit_rejected",
                    path=rejected["path"],
                    reason=rejected["reason"],
                )
    else:
        raise ValueError(f"Unsupported agent: {agent}")

    verification = build_verification_summary(task_path, final_repo)
    _append_trace(
        trace_path,
        "verification_finished",
        solved=verification["solved"],
    )

    summary = {
        "agent": agent,
        "task_id": task_id,
        "agent_result": agent_result,
        "verification": verification,
    }
    (task_run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def run_suite(
    tasks_dir: str | Path,
    agent: str,
    out_dir: str | Path,
    *,
    limit: int | None = None,
    agent_command: str | None = None,
    model: str = DEFAULT_OPENAI_COMPATIBLE_MODEL,
    api_key: str | None = None,
    api_base: str | None = None,
    max_tokens: int | None = 4096,
    temperature: float = 0.0,
) -> dict[str, Any]:
    tasks_root = Path(tasks_dir)
    task_dirs = sorted(
        path
        for path in tasks_root.iterdir()
        if path.is_dir() and (path / "metadata.json").is_file()
    )
    if limit is not None:
        task_dirs = task_dirs[:limit]

    summaries: list[dict[str, Any]] = []
    for task_dir in task_dirs:
        summaries.append(
            run_task(
                task_dir,
                agent,
                out_dir,
                agent_command=agent_command,
                model=model,
                api_key=api_key,
                api_base=api_base,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        )

    solved_count = sum(1 for item in summaries if item["verification"]["solved"])
    visible_pass_hidden_fail = sum(
        1
        for item in summaries
        if item["verification"]["public_tests"]["passed"]
        and not item["verification"]["hidden_tests"]["passed"]
    )
    total = len(summaries)
    aggregate = {
        "agent": agent,
        "tasks": total,
        "solve_rate": (solved_count / total) if total else 0.0,
        "visible_pass_hidden_fail": visible_pass_hidden_fail,
    }
    (Path(out_dir) / "summary.json").write_text(
        json.dumps(aggregate, indent=2) + "\n",
        encoding="utf-8",
    )
    return aggregate
