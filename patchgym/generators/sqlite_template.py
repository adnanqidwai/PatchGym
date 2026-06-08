from __future__ import annotations

import json
import shutil
from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def generate_sqlite_boundary_task(task_dir: Path, seed: int) -> None:
    task_id = f"sqlite.boundary.{seed:04d}"
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
name = "minidb"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
where = ["src"]
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "__init__.py",
        """\
from minidb.queries import list_tasks

__all__ = ["list_tasks"]
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "models.py",
        """\
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    status: str
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "migrations.py",
        """\
from __future__ import annotations

import sqlite3


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open'
        )
        '''
    )
    conn.commit()


def insert_task(conn: sqlite3.Connection, title: str, status: str = "open") -> int:
    cursor = conn.execute(
        "INSERT INTO tasks (title, status) VALUES (?, ?)",
        (title, status),
    )
    conn.commit()
    return int(cursor.lastrowid)
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "queries.py",
        """\
from __future__ import annotations

import sqlite3


def list_tasks(
    conn: sqlite3.Connection,
    status: str | None = None,
    page: int = 1,
    limit: int = 10,
) -> list[dict[str, object]]:
    offset = page * limit
    query = "SELECT id, title, status FROM tasks"
    params: list[object] = []

    if status is not None:
        query += " WHERE status = ?"
        params.append(status)

    query += " ORDER BY id LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [
        {"id": row[0], "title": row[1], "status": row[2]}
        for row in rows
    ]
""",
    )

    _write(
        repo_dir / "tests" / "test_public.py",
        """\
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minidb.migrations import init_db
from minidb.queries import list_tasks


def test_list_tasks_on_empty_database() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    assert list_tasks(conn) == []


def test_list_tasks_returns_rows_after_schema_init() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute("INSERT INTO tasks (title, status) VALUES ('alpha', 'open')")
    conn.commit()
    rows = list_tasks(conn, status="open")
    assert isinstance(rows, list)
""",
    )

    _write(
        task_dir / "hidden_tests" / "test_hidden.py",
        """\
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(os.environ.get("PATCHGYM_REPO_UNDER_TEST", Path(__file__).resolve().parents[1] / "repo"))
sys.path.insert(0, str(ROOT / "src"))

from minidb.migrations import init_db, insert_task
from minidb.queries import list_tasks


def _seed_tasks(conn: sqlite3.Connection, count: int) -> None:
    for index in range(count):
        insert_task(conn, title=f"task-{index + 1:02d}", status="open")


def test_first_page_starts_at_offset_zero() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_tasks(conn, 15)

    rows = list_tasks(conn, page=1, limit=10)
    assert len(rows) == 10
    assert rows[0]["title"] == "task-01"
    assert rows[-1]["title"] == "task-10"


def test_second_page_continues_sequence() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _seed_tasks(conn, 15)

    rows = list_tasks(conn, page=2, limit=10)
    assert len(rows) == 5
    assert rows[0]["title"] == "task-11"
    assert rows[-1]["title"] == "task-15"
""",
    )

    _write(
        task_dir / "issue.md",
        """\
# Fix task pagination offsets

The `minidb` query helper paginates task listings, but page offsets are computed
from the page number incorrectly.

## Expected behavior

- Page 1 should return the first `limit` rows.
- Page 2 should continue with the next `limit` rows.
- Status filtering should still apply before pagination.

## How to verify

Run the public tests in the generated repository:

```bash
pytest tests/test_public.py
```

Hidden tests cover multi-page pagination boundaries.
""",
    )

    metadata = {
        "task_id": task_id,
        "template": "sqlite",
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
                "module": "minidb.queries",
                "name": "list_tasks",
                "signature": "(conn: sqlite3.Connection, status: str | None = None, page: int = 1, limit: int = 10) -> list[dict[str, object]]",
            }
        ],
        "forbidden_patterns": ["test_public", "hidden_tests"],
        "expected_output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "title", "status"],
            },
        },
    }
    _write(task_dir / "oracle.json", json.dumps(oracle, indent=2) + "\n")

    baseline_dir = task_dir / "baseline"
    shutil.copytree(repo_dir, baseline_dir)


def generate_sqlite_integration_task(task_dir: Path, seed: int) -> None:
    task_id = f"sqlite.integration.{seed:04d}"
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
name = "minidb"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
where = ["src"]
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "__init__.py",
        """\
from minidb.queries import list_open_tasks_for_integration, list_tasks

__all__ = ["list_open_tasks_for_integration", "list_tasks"]
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "models.py",
        """\
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    status: str
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "migrations.py",
        """\
from __future__ import annotations

import sqlite3


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open'
        )
        '''
    )
    conn.commit()


def insert_task(conn: sqlite3.Connection, title: str, status: str = "open") -> int:
    cursor = conn.execute(
        "INSERT INTO tasks (title, status) VALUES (?, ?)",
        (title, status),
    )
    conn.commit()
    return int(cursor.lastrowid)
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "queries.py",
        """\
from __future__ import annotations

import sqlite3


def list_tasks(
    conn: sqlite3.Connection,
    status: str | None = None,
    page: int = 1,
    limit: int = 10,
) -> list[dict[str, object]]:
    offset = (page - 1) * limit
    query = "SELECT id, title, status FROM tasks"
    params: list[object] = []

    if status is not None:
        query += " WHERE status = ?"
        params.append(status)

    query += " ORDER BY id LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [
        {"id": row[0], "title": row[1], "status": row[2]}
        for row in rows
    ]


def list_open_tasks_for_integration(conn: sqlite3.Connection) -> list[dict[str, object]]:
    return list_tasks(conn, status="active")
""",
    )

    _write(
        repo_dir / "tests" / "test_public.py",
        """\
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minidb.migrations import init_db, insert_task
from minidb.queries import list_tasks


def test_list_tasks_on_empty_database() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    assert list_tasks(conn) == []


def test_list_tasks_returns_open_rows() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    insert_task(conn, title="alpha", status="open")
    rows = list_tasks(conn, status="open")
    assert len(rows) == 1
    assert rows[0]["title"] == "alpha"
""",
    )

    _write(
        task_dir / "hidden_tests" / "test_hidden.py",
        """\
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(os.environ.get("PATCHGYM_REPO_UNDER_TEST", Path(__file__).resolve().parents[1] / "repo"))
sys.path.insert(0, str(ROOT / "src"))

from minidb.migrations import init_db, insert_task
from minidb.queries import list_open_tasks_for_integration


def test_integration_helper_returns_open_tasks() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    insert_task(conn, title="alpha", status="open")
    insert_task(conn, title="beta", status="done")

    rows = list_open_tasks_for_integration(conn)
    assert len(rows) == 1
    assert rows[0]["title"] == "alpha"
    assert rows[0]["status"] == "open"


def test_integration_helper_ignores_done_tasks() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    insert_task(conn, title="alpha", status="open")
    insert_task(conn, title="beta", status="open")
    insert_task(conn, title="gamma", status="done")

    rows = list_open_tasks_for_integration(conn)
    assert len(rows) == 2
    assert {row["title"] for row in rows} == {"alpha", "beta"}
""",
    )

    _write(
        task_dir / "issue.md",
        """\
# Fix integration query status wiring

The `minidb` integration helper should return open tasks for downstream sync jobs,
but it filters on the wrong status value.

## Expected behavior

- `list_tasks` pagination and filtering should keep working.
- `list_open_tasks_for_integration` must return only tasks with status `open`.

## How to verify

Run the public tests in the generated repository:

```bash
pytest tests/test_public.py
```

Hidden tests cover the integration helper wiring.
""",
    )

    metadata = {
        "task_id": task_id,
        "template": "sqlite",
        "bug_family": "integration",
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
                "module": "minidb.queries",
                "name": "list_open_tasks_for_integration",
                "signature": "(conn: sqlite3.Connection) -> list[dict[str, object]]",
            }
        ],
        "forbidden_patterns": ["test_public", "hidden_tests"],
        "expected_output_schema": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "title", "status"],
            },
        },
    }
    _write(task_dir / "oracle.json", json.dumps(oracle, indent=2) + "\n")

    baseline_dir = task_dir / "baseline"
    shutil.copytree(repo_dir, baseline_dir)


def generate_sqlite_regression_trap_task(task_dir: Path, seed: int) -> None:
    task_id = f"sqlite.regression_trap.{seed:04d}"
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
name = "minidb"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
where = ["src"]
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "__init__.py",
        """\
from minidb.migrations import init_db
from minidb.queries import list_tasks

__all__ = ["init_db", "list_tasks"]
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "models.py",
        """\
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    status: str
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "migrations.py",
        """\
from __future__ import annotations

import sqlite3


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS tasks")
    conn.execute(
        '''
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open'
        )
        '''
    )
    conn.commit()


def insert_task(conn: sqlite3.Connection, title: str, status: str = "open") -> int:
    cursor = conn.execute(
        "INSERT INTO tasks (title, status) VALUES (?, ?)",
        (title, status),
    )
    conn.commit()
    return int(cursor.lastrowid)
""",
    )

    _write(
        repo_dir / "src" / "minidb" / "queries.py",
        """\
from __future__ import annotations

import sqlite3


def list_tasks(
    conn: sqlite3.Connection,
    status: str | None = None,
    page: int = 1,
    limit: int = 10,
) -> list[dict[str, object]]:
    offset = (page - 1) * limit
    query = "SELECT id, title, status FROM tasks"
    params: list[object] = []

    if status is not None:
        query += " WHERE status = ?"
        params.append(status)

    query += " ORDER BY id LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [
        {"id": row[0], "title": row[1], "status": row[2]}
        for row in rows
    ]
""",
    )

    _write(
        repo_dir / "tests" / "test_public.py",
        """\
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minidb.migrations import init_db, insert_task
from minidb.queries import list_tasks


def test_list_tasks_on_empty_database() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    assert list_tasks(conn) == []


def test_list_tasks_returns_rows_after_schema_init() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    insert_task(conn, title="alpha", status="open")
    rows = list_tasks(conn, status="open")
    assert len(rows) == 1
    assert rows[0]["title"] == "alpha"
""",
    )

    _write(
        task_dir / "hidden_tests" / "test_hidden.py",
        """\
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(os.environ.get("PATCHGYM_REPO_UNDER_TEST", Path(__file__).resolve().parents[1] / "repo"))
sys.path.insert(0, str(ROOT / "src"))

from minidb.migrations import init_db, insert_task
from minidb.queries import list_tasks


def test_init_db_is_idempotent_and_preserves_rows() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    insert_task(conn, title="alpha", status="open")
    insert_task(conn, title="beta", status="done")

    init_db(conn)

    rows = list_tasks(conn)
    assert len(rows) == 2
    assert {row["title"] for row in rows} == {"alpha", "beta"}


def test_repeated_init_db_does_not_reset_autoincrement_sequence_unnecessarily() -> None:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    first_id = insert_task(conn, title="alpha", status="open")

    init_db(conn)
    second_id = insert_task(conn, title="gamma", status="open")

    assert second_id == first_id + 1
""",
    )

    _write(
        task_dir / "issue.md",
        """\
# Fix destructive database initialization

The `minidb` migration helper recreates the tasks table on every initialization call,
which wipes existing rows during routine startup.

## Expected behavior

- The first `init_db` call should create the schema when needed.
- Repeated `init_db` calls must be idempotent and preserve existing rows.
- Task inserts and listings should continue to work after re-initialization.

## How to verify

Run the public tests in the generated repository:

```bash
pytest tests/test_public.py
```

Hidden tests cover repeated initialization and data retention.
""",
    )

    metadata = {
        "task_id": task_id,
        "template": "sqlite",
        "bug_family": "regression_trap",
        "difficulty": "very_hard",
        "seed": seed,
        "language": "python",
        "max_steps": 60,
        "patch_budget": {
            "max_files_touched": 2,
            "max_lines_changed": 120,
        },
    }
    _write(task_dir / "metadata.json", json.dumps(metadata, indent=2) + "\n")

    oracle = {
        "public_api": [
            {
                "module": "minidb.migrations",
                "name": "init_db",
                "signature": "(conn: sqlite3.Connection) -> None",
            }
        ],
        "forbidden_patterns": ["test_public", "hidden_tests"],
        "expected_output_schema": {
            "type": "null",
        },
    }
    _write(task_dir / "oracle.json", json.dumps(oracle, indent=2) + "\n")

    baseline_dir = task_dir / "baseline"
    shutil.copytree(repo_dir, baseline_dir)
