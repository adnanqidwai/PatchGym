from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from patchgym.verifier.api_contract import check_api_contract
from patchgym.verifier.patch_budget import check_patch_budget
from patchgym.verifier.tests_runner import run_pytest


def build_verification_summary(
    task_dir: str | Path,
    repo_dir: str | Path | None = None,
) -> dict[str, Any]:
    task_path = Path(task_dir).resolve()
    repo_path = Path(repo_dir).resolve() if repo_dir else (task_path / "repo").resolve()
    baseline_path = task_path / "baseline"

    metadata = json.loads((task_path / "metadata.json").read_text())
    oracle = json.loads((task_path / "oracle.json").read_text())

    public_result = run_pytest(repo_path / "tests" / "test_public.py", cwd=repo_path)
    hidden_result = run_pytest(
        task_path / "hidden_tests",
        cwd=task_path,
        env={"PATCHGYM_REPO_UNDER_TEST": str(repo_path.resolve())},
    )
    api_contract = check_api_contract(repo_path, oracle)
    patch_budget = check_patch_budget(
        repo_path,
        baseline_path,
        metadata.get("patch_budget", {}),
    )

    solved = (
        public_result["passed"]
        and hidden_result["passed"]
        and api_contract["passed"]
        and patch_budget["passed"]
    )

    return {
        "task_id": metadata["task_id"],
        "public_tests": {"passed": public_result["passed"]},
        "hidden_tests": {"passed": hidden_result["passed"]},
        "api_contract": {"passed": api_contract["passed"]},
        "patch_budget": {"passed": patch_budget["passed"]},
        "solved": solved,
    }


def verify_task(task_dir: str | Path, repo_dir: str | Path | None = None, as_json: bool = False) -> int:
    summary = build_verification_summary(task_dir, repo_dir)

    if as_json:
        sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    else:
        sys.stdout.write(f"task_id={summary['task_id']} solved={summary['solved']}\n")

    return 0 if summary["solved"] else 1
