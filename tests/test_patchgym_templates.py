import json
from pathlib import Path

from test_patchgym_mvp import run_patchgym


def test_generate_creates_cli_and_sqlite_boundary_tasks(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"

    result = run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "cli,sqlite",
        "--n",
        "1",
        "--seed",
        "42",
    )

    assert result.returncode == 0, result.stderr

    cli_task = out_dir / "cli.boundary.0042"
    assert (cli_task / "repo" / "src" / "taskcli" / "main.py").is_file()
    assert (cli_task / "repo" / "src" / "taskcli" / "storage.py").is_file()
    assert (cli_task / "repo" / "tests" / "test_public.py").is_file()
    assert (cli_task / "hidden_tests" / "test_hidden.py").is_file()
    cli_metadata = json.loads((cli_task / "metadata.json").read_text())
    assert cli_metadata["template"] == "cli"
    assert cli_metadata["bug_family"] == "boundary"
    cli_oracle = json.loads((cli_task / "oracle.json").read_text())
    assert cli_oracle["public_api"][0]["module"] == "taskcli.main"
    assert cli_oracle["public_api"][0]["name"] == "resolve_limit"

    sqlite_task = out_dir / "sqlite.boundary.0042"
    assert (sqlite_task / "repo" / "src" / "minidb" / "queries.py").is_file()
    assert (sqlite_task / "repo" / "src" / "minidb" / "models.py").is_file()
    assert (sqlite_task / "repo" / "tests" / "test_public.py").is_file()
    assert (sqlite_task / "hidden_tests" / "test_hidden.py").is_file()
    sqlite_metadata = json.loads((sqlite_task / "metadata.json").read_text())
    assert sqlite_metadata["template"] == "sqlite"
    assert sqlite_metadata["bug_family"] == "boundary"
    sqlite_oracle = json.loads((sqlite_task / "oracle.json").read_text())
    assert sqlite_oracle["public_api"][0]["module"] == "minidb.queries"
    assert sqlite_oracle["public_api"][0]["name"] == "list_tasks"


def test_cli_boundary_starter_passes_public_and_fails_hidden(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"
    assert run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "cli",
        "--n",
        "1",
        "--seed",
        "42",
    ).returncode == 0

    result = run_patchgym("verify", "--task", str(out_dir / "cli.boundary.0042"), "--json")

    assert result.returncode == 1, result.stderr
    summary = json.loads(result.stdout)
    assert summary["public_tests"]["passed"] is True
    assert summary["hidden_tests"]["passed"] is False
    assert summary["api_contract"]["passed"] is True
    assert summary["patch_budget"]["passed"] is True
    assert summary["solved"] is False


def test_cli_boundary_accepts_flag_precedence_fix(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"
    assert run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "cli",
        "--n",
        "1",
        "--seed",
        "42",
    ).returncode == 0

    task_dir = out_dir / "cli.boundary.0042"
    main_file = task_dir / "repo" / "src" / "taskcli" / "main.py"
    source = main_file.read_text()
    main_file.write_text(
        source.replace(
            "if config_limit is not None:\n        return config_limit\n    if cli_limit is not None:\n        return cli_limit",
            "if cli_limit is not None:\n        return cli_limit\n    if config_limit is not None:\n        return config_limit",
        )
    )

    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["hidden_tests"]["passed"] is True
    assert summary["solved"] is True


def test_sqlite_boundary_starter_passes_public_and_fails_hidden(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"
    assert run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "sqlite",
        "--n",
        "1",
        "--seed",
        "42",
    ).returncode == 0

    result = run_patchgym("verify", "--task", str(out_dir / "sqlite.boundary.0042"), "--json")

    assert result.returncode == 1, result.stderr
    summary = json.loads(result.stdout)
    assert summary["public_tests"]["passed"] is True
    assert summary["hidden_tests"]["passed"] is False
    assert summary["api_contract"]["passed"] is True
    assert summary["patch_budget"]["passed"] is True
    assert summary["solved"] is False


def test_sqlite_boundary_accepts_pagination_fix(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated_tasks"
    assert run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "sqlite",
        "--n",
        "1",
        "--seed",
        "42",
    ).returncode == 0

    task_dir = out_dir / "sqlite.boundary.0042"
    queries_file = task_dir / "repo" / "src" / "minidb" / "queries.py"
    source = queries_file.read_text()
    queries_file.write_text(source.replace("offset = page * limit", "offset = (page - 1) * limit"))

    result = run_patchgym("verify", "--task", str(task_dir), "--json")

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["hidden_tests"]["passed"] is True
    assert summary["solved"] is True
