import json
import sys
from pathlib import Path

from test_patchgym_mvp import run_patchgym


def generate_parser_tasks(out_dir: Path, *, count: int = 1) -> Path:
    result = run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "parser",
        "--n",
        str(count),
        "--seed",
        "42",
    )
    assert result.returncode == 0, result.stderr
    return out_dir


def test_run_noop_agent_writes_trace_and_unsolved_summary(tmp_path: Path) -> None:
    tasks_dir = generate_parser_tasks(tmp_path / "generated_tasks")
    task_dir = tasks_dir / "parser.boundary.0042"
    run_dir = tmp_path / "runs" / "noop"

    result = run_patchgym(
        "run",
        "--task",
        str(task_dir),
        "--agent",
        "noop",
        "--out",
        str(run_dir),
    )

    assert result.returncode == 0, result.stderr
    task_run = run_dir / "parser.boundary.0042"
    assert (task_run / "final_repo" / "src" / "miniparse" / "date_parser.py").is_file()
    summary = json.loads((task_run / "summary.json").read_text())
    assert summary["agent"] == "noop"
    assert summary["verification"]["public_tests"]["passed"] is True
    assert summary["verification"]["hidden_tests"]["passed"] is False
    assert summary["verification"]["solved"] is False

    events = [
        json.loads(line)
        for line in (task_run / "trace.jsonl").read_text().splitlines()
    ]
    assert [event["event"] for event in events] == [
        "run_started",
        "issue_loaded",
        "agent_noop",
        "verification_finished",
    ]


def test_run_command_agent_can_solve_task_through_repo_env(tmp_path: Path) -> None:
    tasks_dir = generate_parser_tasks(tmp_path / "generated_tasks")
    task_dir = tasks_dir / "parser.boundary.0042"
    run_dir = tmp_path / "runs" / "command"
    fixer = tmp_path / "fixer.py"
    fixer.write_text(
        """\
import os
from pathlib import Path

parser_file = Path(os.environ["PATCHGYM_REPO_DIR"]) / "src" / "miniparse" / "date_parser.py"
source = parser_file.read_text()
parser_file.write_text(
    source.replace(
        "if value is None:",
        "if value is None or value.strip() == \\"\\":",
    )
)
"""
    )

    result = run_patchgym(
        "run",
        "--task",
        str(task_dir),
        "--agent",
        "command",
        "--agent-command",
        f"{sys.executable} {fixer}",
        "--out",
        str(run_dir),
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads((run_dir / "parser.boundary.0042" / "summary.json").read_text())
    assert summary["agent"] == "command"
    assert summary["verification"]["solved"] is True
    assert summary["agent_result"]["returncode"] == 0


def test_run_suite_and_summarize_write_markdown_report(tmp_path: Path) -> None:
    tasks_dir = generate_parser_tasks(tmp_path / "generated_tasks", count=2)
    run_dir = tmp_path / "runs" / "noop-suite"
    report_path = tmp_path / "report.md"

    suite_result = run_patchgym(
        "run-suite",
        "--tasks",
        str(tasks_dir),
        "--agent",
        "noop",
        "--limit",
        "2",
        "--out",
        str(run_dir),
    )
    assert suite_result.returncode == 0, suite_result.stderr

    report_result = run_patchgym("summarize", str(run_dir), "--out", str(report_path))

    assert report_result.returncode == 0, report_result.stderr
    report = report_path.read_text()
    assert "agent | tasks | solve_rate | visible_pass_hidden_fail" in report
    assert "noop | 2 | 0.00 | 2" in report
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["agent"] == "noop"
    assert summary["tasks"] == 2
    assert summary["solve_rate"] == 0.0
    assert summary["visible_pass_hidden_fail"] == 2
