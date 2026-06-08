import json
from pathlib import Path

import pytest

from test_patchgym_mvp import run_patchgym


FAMILIES = [
    ("cli", "contract", "hard"),
    ("sqlite", "integration", "hard"),
    ("parser", "contract", "very_hard"),
    ("sqlite", "regression_trap", "very_hard"),
]


def generate_family(tmp_path: Path, template: str, bug_family: str) -> Path:
    out_dir = tmp_path / "generated_tasks"
    result = run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        template,
        "--bug-family",
        bug_family,
        "--n",
        "1",
        "--seed",
        "42",
    )
    assert result.returncode == 0, result.stderr
    return out_dir / f"{template}.{bug_family}.0042"


@pytest.mark.parametrize(("template", "bug_family", "difficulty"), FAMILIES)
def test_generate_hard_family_metadata(
    tmp_path: Path,
    template: str,
    bug_family: str,
    difficulty: str,
) -> None:
    task_dir = generate_family(tmp_path, template, bug_family)

    metadata = json.loads((task_dir / "metadata.json").read_text())
    assert metadata["task_id"] == f"{template}.{bug_family}.0042"
    assert metadata["template"] == template
    assert metadata["bug_family"] == bug_family
    assert metadata["difficulty"] == difficulty
    assert (task_dir / "repo" / "tests" / "test_public.py").is_file()
    assert (task_dir / "hidden_tests" / "test_hidden.py").is_file()
    assert (task_dir / "baseline").is_dir()


@pytest.mark.parametrize(("template", "bug_family", "difficulty"), FAMILIES)
def test_hard_family_starters_pass_public_and_fail_hidden(
    tmp_path: Path,
    template: str,
    bug_family: str,
    difficulty: str,
) -> None:
    task_dir = generate_family(tmp_path, template, bug_family)

    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 1, result.stderr
    summary = json.loads(result.stdout)
    assert summary["public_tests"]["passed"] is True
    assert summary["hidden_tests"]["passed"] is False
    assert summary["api_contract"]["passed"] is True
    assert summary["patch_budget"]["passed"] is True
    assert summary["solved"] is False


def test_cli_contract_accepts_json_schema_fix(tmp_path: Path) -> None:
    task_dir = generate_family(tmp_path, "cli", "contract")
    formatting_file = task_dir / "repo" / "src" / "taskcli" / "formatting.py"
    source = formatting_file.read_text()
    formatting_file.write_text(source.replace('"name": task["title"]', '"title": task["title"]'))

    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["solved"] is True


def test_sqlite_integration_accepts_status_wiring_fix(tmp_path: Path) -> None:
    task_dir = generate_family(tmp_path, "sqlite", "integration")
    queries_file = task_dir / "repo" / "src" / "minidb" / "queries.py"
    source = queries_file.read_text()
    queries_file.write_text(source.replace('status="active"', 'status="open"'))

    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["solved"] is True


def test_parser_contract_accepts_no_mutation_fix(tmp_path: Path) -> None:
    task_dir = generate_family(tmp_path, "parser", "contract")
    schema_file = task_dir / "repo" / "src" / "miniparse" / "schema.py"
    source = schema_file.read_text()
    schema_file.write_text(
        source.replace(
            "    fields.sort(key=lambda field: field.name)\n    return [field.name for field in fields]",
            "    ordered_fields = sorted(fields, key=lambda field: field.name)\n    return [field.name for field in ordered_fields]",
        )
    )

    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["solved"] is True


def test_sqlite_regression_trap_accepts_idempotent_migration_fix(tmp_path: Path) -> None:
    task_dir = generate_family(tmp_path, "sqlite", "regression_trap")
    migrations_file = task_dir / "repo" / "src" / "minidb" / "migrations.py"
    source = migrations_file.read_text()
    migrations_file.write_text(
        source.replace(
            '    conn.execute("DROP TABLE IF EXISTS tasks")\n'
            "    conn.execute(\n"
            "        '''\n"
            "        CREATE TABLE tasks (",
            "    conn.execute(\n"
            "        '''\n"
            "        CREATE TABLE IF NOT EXISTS tasks (",
        )
    )

    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["solved"] is True
