from __future__ import annotations

import json
import shutil
from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def generate_cli_boundary_task(task_dir: Path, seed: int) -> None:
    task_id = f"cli.boundary.{seed:04d}"
    if task_dir.exists():
        shutil.rmtree(task_dir)
    task_dir.mkdir(parents=True)

    repo_dir = task_dir / "repo"
    repo_dir.mkdir()

    _write(
        repo_dir / "pyproject.toml",
        """\
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "taskcli"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
where = ["src"]
""",
    )

    _write(
        repo_dir / "src" / "taskcli" / "__init__.py",
        """\
from taskcli.main import resolve_limit

__all__ = ["resolve_limit"]
""",
    )

    _write(
        repo_dir / "src" / "taskcli" / "main.py",
        """\
from __future__ import annotations


def resolve_limit(
    cli_limit: int | None,
    config_limit: int | None,
    default_limit: int = 20,
) -> int:
    if config_limit is not None:
        return config_limit
    if cli_limit is not None:
        return cli_limit
    return default_limit
""",
    )

    _write(
        repo_dir / "src" / "taskcli" / "storage.py",
        """\
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaskStore:
    tasks: list[dict[str, str]] = field(default_factory=list)

    def add(self, title: str, status: str = "open") -> dict[str, str]:
        task = {"title": title, "status": status}
        self.tasks.append(task)
        return task

    def list_open(self, limit: int) -> list[dict[str, str]]:
        open_tasks = [task for task in self.tasks if task["status"] == "open"]
        return open_tasks[:limit]
""",
    )

    _write(
        repo_dir / "src" / "taskcli" / "formatting.py",
        """\
from __future__ import annotations


def format_task_line(task: dict[str, str]) -> str:
    return f"[{task['status']}] {task['title']}"
""",
    )

    _write(
        repo_dir / "tests" / "test_public.py",
        """\
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from taskcli.main import resolve_limit


def test_resolve_limit_uses_default() -> None:
    assert resolve_limit(None, None) == 20


def test_resolve_limit_uses_config_when_cli_missing() -> None:
    assert resolve_limit(None, 50) == 50


def test_resolve_limit_uses_cli_when_config_missing() -> None:
    assert resolve_limit(100, None) == 100
""",
    )

    _write(
        task_dir / "hidden_tests" / "test_hidden.py",
        """\
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("PATCHGYM_REPO_UNDER_TEST", Path(__file__).resolve().parents[1] / "repo"))
sys.path.insert(0, str(ROOT / "src"))

from taskcli.main import resolve_limit


def test_cli_limit_overrides_config() -> None:
    assert resolve_limit(100, 50) == 100


def test_cli_limit_overrides_config_with_custom_default() -> None:
    assert resolve_limit(15, 30, default_limit=5) == 15
""",
    )

    _write(
        task_dir / "issue.md",
        """\
# Fix CLI flag precedence for task listing limits

The `taskcli` tool resolves listing limits from CLI flags, config files, and defaults,
but config values currently override explicit CLI flags.

## Expected behavior

- When a CLI limit is provided, it should take precedence over config and defaults.
- When only config is provided, config should be used.
- When neither is provided, the default limit should apply.

## How to verify

Run the public tests in the generated repository:

```bash
pytest tests/test_public.py
```

Hidden tests cover CLI-versus-config precedence cases.
""",
    )

    metadata = {
        "task_id": task_id,
        "template": "cli",
        "bug_family": "boundary",
        "seed": seed,
        "language": "python",
        "max_steps": 40,
        "patch_budget": {
            "max_files_touched": 3,
            "max_lines_changed": 80,
        },
    }
    _write(task_dir / "metadata.json", json.dumps(metadata, indent=2) + "\n")

    oracle = {
        "public_api": [
            {
                "module": "taskcli.main",
                "name": "resolve_limit",
                "signature": "(cli_limit: int | None, config_limit: int | None, default_limit: int = 20) -> int",
            }
        ],
        "forbidden_patterns": ["test_public", "hidden_tests"],
        "expected_output_schema": {
            "type": "integer",
        },
    }
    _write(task_dir / "oracle.json", json.dumps(oracle, indent=2) + "\n")

    baseline_dir = task_dir / "baseline"
    shutil.copytree(repo_dir, baseline_dir)


def generate_cli_contract_task(task_dir: Path, seed: int) -> None:
    task_id = f"cli.contract.{seed:04d}"
    if task_dir.exists():
        shutil.rmtree(task_dir)
    task_dir.mkdir(parents=True)

    repo_dir = task_dir / "repo"
    repo_dir.mkdir()

    _write(
        repo_dir / "pyproject.toml",
        """\
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "taskcli"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
where = ["src"]
""",
    )

    _write(
        repo_dir / "src" / "taskcli" / "__init__.py",
        """\
from taskcli.formatting import format_task_json, format_task_line

__all__ = ["format_task_json", "format_task_line"]
""",
    )

    _write(
        repo_dir / "src" / "taskcli" / "main.py",
        """\
from __future__ import annotations


def resolve_limit(
    cli_limit: int | None,
    config_limit: int | None,
    default_limit: int = 20,
) -> int:
    if cli_limit is not None:
        return cli_limit
    if config_limit is not None:
        return config_limit
    return default_limit
""",
    )

    _write(
        repo_dir / "src" / "taskcli" / "storage.py",
        """\
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaskStore:
    tasks: list[dict[str, str]] = field(default_factory=list)

    def add(self, title: str, status: str = "open") -> dict[str, str]:
        task = {"title": title, "status": status}
        self.tasks.append(task)
        return task
""",
    )

    _write(
        repo_dir / "src" / "taskcli" / "formatting.py",
        """\
from __future__ import annotations


def format_task_line(task: dict[str, str]) -> str:
    return f"[{task['status']}] {task['title']}"


def format_task_json(task: dict[str, str]) -> dict[str, str]:
    return {
        "name": task["title"],
        "status": task["status"],
    }
""",
    )

    _write(
        repo_dir / "tests" / "test_public.py",
        """\
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from taskcli.formatting import format_task_line
from taskcli.main import resolve_limit


def test_format_task_line_renders_status_and_title() -> None:
    task = {"title": "Ship docs", "status": "open"}
    assert format_task_line(task) == "[open] Ship docs"


def test_resolve_limit_uses_default() -> None:
    assert resolve_limit(None, None) == 20


def test_resolve_limit_prefers_cli_over_config() -> None:
    assert resolve_limit(100, 50) == 100
""",
    )

    _write(
        task_dir / "hidden_tests" / "test_hidden.py",
        """\
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("PATCHGYM_REPO_UNDER_TEST", Path(__file__).resolve().parents[1] / "repo"))
sys.path.insert(0, str(ROOT / "src"))

from taskcli.formatting import format_task_json


def test_json_output_uses_title_key() -> None:
    payload = format_task_json({"title": "Ship docs", "status": "open"})
    assert "title" in payload
    assert payload["title"] == "Ship docs"
    assert "name" not in payload


def test_json_output_is_serializable_with_title_key() -> None:
    payload = format_task_json({"title": "Review patch", "status": "done"})
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["title"] == "Review patch"
""",
    )

    _write(
        task_dir / "issue.md",
        """\
# Fix JSON task export contract

The `taskcli` formatter exposes tasks as JSON for downstream integrations, but the
serialized payload uses the wrong field name for the task title.

## Expected behavior

- Text rendering via `format_task_line` should remain unchanged.
- JSON output must expose the task title under the `title` key.
- The JSON payload must remain serializable with the documented schema.

## How to verify

Run the public tests in the generated repository:

```bash
pytest tests/test_public.py
```

Hidden tests validate the JSON export contract.
""",
    )

    metadata = {
        "task_id": task_id,
        "template": "cli",
        "bug_family": "contract",
        "difficulty": "hard",
        "seed": seed,
        "language": "python",
        "max_steps": 40,
        "patch_budget": {
            "max_files_touched": 3,
            "max_lines_changed": 80,
        },
    }
    _write(task_dir / "metadata.json", json.dumps(metadata, indent=2) + "\n")

    oracle = {
        "public_api": [
            {
                "module": "taskcli.formatting",
                "name": "format_task_json",
                "signature": "(task: dict[str, str]) -> dict[str, str]",
            }
        ],
        "forbidden_patterns": ["test_public", "hidden_tests"],
        "expected_output_schema": {
            "type": "object",
            "required": ["title", "status"],
        },
    }
    _write(task_dir / "oracle.json", json.dumps(oracle, indent=2) + "\n")

    baseline_dir = task_dir / "baseline"
    shutil.copytree(repo_dir, baseline_dir)
