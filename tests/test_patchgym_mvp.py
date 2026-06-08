import json
import shutil
import subprocess
import sys
from pathlib import Path

from patchgym.generate import generate_tasks
from patchgym.verify import build_verification_summary


ROOT = Path(__file__).resolve().parents[1]


def run_patchgym(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "patchgym", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_generate_creates_seeded_parser_boundary_task(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"

    result = run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "parser",
        "--n",
        "1",
        "--seed",
        "42",
    )

    assert result.returncode == 0, result.stderr
    task_dir = out_dir / "parser.boundary.0042"
    assert task_dir.is_dir()
    assert (task_dir / "repo" / "pyproject.toml").is_file()
    assert (task_dir / "repo" / "src" / "miniparse" / "date_parser.py").is_file()
    assert (task_dir / "repo" / "tests" / "test_public.py").is_file()
    assert (task_dir / "hidden_tests" / "test_hidden.py").is_file()
    assert (task_dir / "issue.md").read_text().startswith("# Fix date parsing")

    metadata = json.loads((task_dir / "metadata.json").read_text())
    assert metadata == {
        "task_id": "parser.boundary.0042",
        "template": "parser",
        "bug_family": "boundary",
        "seed": 42,
        "language": "python",
        "max_steps": 40,
        "patch_budget": {"max_files_touched": 3, "max_lines_changed": 80},
    }

    oracle = json.loads((task_dir / "oracle.json").read_text())
    assert oracle["public_api"][0]["module"] == "miniparse.date_parser"
    assert oracle["public_api"][0]["name"] == "parse_date"
    assert oracle["forbidden_patterns"] == ["test_public", "hidden_tests"]


def test_generate_creates_harder_parser_regression_trap_task(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"

    result = run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "parser",
        "--bug-family",
        "regression_trap",
        "--n",
        "1",
        "--seed",
        "42",
    )

    assert result.returncode == 0, result.stderr
    task_dir = out_dir / "parser.regression_trap.0042"
    assert task_dir.is_dir()
    assert (task_dir / "repo" / "src" / "miniparse" / "record_parser.py").is_file()
    assert (task_dir / "repo" / "tests" / "test_public.py").is_file()
    assert (task_dir / "hidden_tests" / "test_hidden.py").is_file()
    assert (task_dir / "issue.md").read_text().startswith("# Fix quoted delimiter parsing")

    metadata = json.loads((task_dir / "metadata.json").read_text())
    assert metadata["task_id"] == "parser.regression_trap.0042"
    assert metadata["bug_family"] == "regression_trap"
    assert metadata["patch_budget"] == {"max_files_touched": 2, "max_lines_changed": 120}

    oracle = json.loads((task_dir / "oracle.json").read_text())
    assert oracle["public_api"][0]["module"] == "miniparse.record_parser"
    assert oracle["public_api"][0]["name"] == "parse_record"


def test_harder_regression_trap_starter_fails_public_and_hidden_tests(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"
    assert run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "parser",
        "--bug-family",
        "regression_trap",
        "--n",
        "1",
        "--seed",
        "42",
    ).returncode == 0

    task_dir = out_dir / "parser.regression_trap.0042"
    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 1, result.stderr
    summary = json.loads(result.stdout)
    assert summary["public_tests"]["passed"] is False
    assert summary["hidden_tests"]["passed"] is False
    assert summary["api_contract"]["passed"] is True
    assert summary["patch_budget"]["passed"] is True
    assert summary["solved"] is False


def test_harder_regression_trap_accepts_csv_based_fix(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"
    assert run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "parser",
        "--bug-family",
        "regression_trap",
        "--n",
        "1",
        "--seed",
        "42",
    ).returncode == 0

    task_dir = out_dir / "parser.regression_trap.0042"
    parser_file = task_dir / "repo" / "src" / "miniparse" / "record_parser.py"
    parser_file.write_text(
        """\
from __future__ import annotations

import csv
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    name: str
    required: bool = True


def parse_record(line: str, fields: list[Field], delimiter: str = ',') -> dict[str, str]:
    if line is None:
        raise ValueError("record line is required")

    rows = list(csv.reader([line], delimiter=delimiter, skipinitialspace=True))
    parts = rows[0] if rows else []
    if len(parts) != len(fields):
        raise ValueError(f"expected {len(fields)} fields, got {len(parts)}")

    result: dict[str, str] = {}
    for field, raw_value in zip(fields, parts):
        value = raw_value.strip()
        if field.required and value == "":
            raise ValueError(f"field {field.name} is required")
        result[field.name] = value
    return result
"""
    )

    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["public_tests"]["passed"] is True
    assert summary["hidden_tests"]["passed"] is True
    assert summary["api_contract"]["passed"] is True
    assert summary["solved"] is True


def test_verify_reports_hidden_failure_for_seeded_bug(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"
    assert run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "parser",
        "--n",
        "1",
        "--seed",
        "42",
    ).returncode == 0

    task_dir = out_dir / "parser.boundary.0042"
    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 1, result.stderr
    summary = json.loads(result.stdout)
    assert summary["task_id"] == "parser.boundary.0042"
    assert summary["public_tests"]["passed"] is True
    assert summary["hidden_tests"]["passed"] is False
    assert summary["api_contract"]["passed"] is True
    assert summary["patch_budget"]["passed"] is True
    assert summary["solved"] is False


def test_verify_accepts_minimal_manual_fix(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"
    assert run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "parser",
        "--n",
        "1",
        "--seed",
        "42",
    ).returncode == 0

    task_dir = out_dir / "parser.boundary.0042"
    parser_file = task_dir / "repo" / "src" / "miniparse" / "date_parser.py"
    source = parser_file.read_text()
    parser_file.write_text(
        source.replace(
            "if value is None:",
            "if value is None or value.strip() == \"\":",
        )
    )

    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["public_tests"]["passed"] is True
    assert summary["hidden_tests"]["passed"] is True
    assert summary["api_contract"]["passed"] is True
    assert summary["solved"] is True


def test_verify_repo_override_runs_hidden_tests_against_override(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"
    assert run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "parser",
        "--n",
        "1",
        "--seed",
        "42",
    ).returncode == 0

    task_dir = out_dir / "parser.boundary.0042"
    final_repo = tmp_path / "final_repo"
    shutil.copytree(task_dir / "repo", final_repo)
    parser_file = final_repo / "src" / "miniparse" / "date_parser.py"
    source = parser_file.read_text()
    parser_file.write_text(
        source.replace(
            "if value is None:",
            "if value is None or value.strip() == \"\":",
        )
    )

    result = run_patchgym(
        "verify",
        "--task",
        str(task_dir),
        "--repo",
        str(final_repo),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["hidden_tests"]["passed"] is True
    assert summary["solved"] is True


def test_verify_repo_override_accepts_relative_repo_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    generate_tasks(out_dir="generated_tasks", templates=["parser"], n=1, seed=42)
    task_dir = Path("generated_tasks") / "parser.boundary.0042"
    final_repo = Path("final_repo")
    shutil.copytree(task_dir / "repo", final_repo)
    parser_file = final_repo / "src" / "miniparse" / "date_parser.py"
    source = parser_file.read_text()
    parser_file.write_text(
        source.replace(
            "if value is None:",
            "if value is None or value.strip() == \"\":",
        )
    )

    summary = build_verification_summary(task_dir, final_repo)

    assert summary["public_tests"]["passed"] is True
    assert summary["hidden_tests"]["passed"] is True
    assert summary["solved"] is True


def test_verify_flags_public_api_signature_changes(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"
    assert run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "parser",
        "--n",
        "1",
        "--seed",
        "42",
    ).returncode == 0

    task_dir = out_dir / "parser.boundary.0042"
    parser_file = task_dir / "repo" / "src" / "miniparse" / "date_parser.py"
    source = parser_file.read_text()
    parser_file.write_text(
        source.replace(
            "def parse_date(value: str) -> ParsedDate:",
            "def parse_date(value: str, default_timezone: str = \"UTC\") -> ParsedDate:",
        )
    )

    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 1, result.stderr
    summary = json.loads(result.stdout)
    assert summary["api_contract"]["passed"] is False
    assert summary["solved"] is False
