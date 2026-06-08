from __future__ import annotations

import json
import shutil
from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def generate_parser_boundary_task(task_dir: Path, seed: int) -> None:
    task_id = f"parser.boundary.{seed:04d}"
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
name = "miniparse"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
where = ["src"]
""",
    )

    _write(
        repo_dir / "src" / "miniparse" / "__init__.py",
        """\
from miniparse.date_parser import ParsedDate, parse_date

__all__ = ["ParsedDate", "parse_date"]
""",
    )

    _write(
        repo_dir / "src" / "miniparse" / "schema.py",
        """\
from dataclasses import dataclass


@dataclass(frozen=True)
class DateField:
    name: str
    required: bool = True
""",
    )

    _write(
        repo_dir / "src" / "miniparse" / "date_parser.py",
        """\
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ParsedDate:
    date: datetime
    timezone: str


def parse_date(value: str) -> ParsedDate:
    if value is None:
        raise ValueError("date value is required")

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    if text:
        parsed = datetime.fromisoformat(text)
    else:
        parsed = datetime(1970, 1, 1, tzinfo=timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    tz_name = parsed.tzname() or "UTC"
    return ParsedDate(date=parsed, timezone=tz_name)
""",
    )

    _write(
        repo_dir / "tests" / "test_public.py",
        """\
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from miniparse.date_parser import parse_date


def test_parse_valid_iso_date() -> None:
    result = parse_date("2024-03-15T12:00:00+00:00")
    assert result.date == datetime(2024, 3, 15, 12, 0, tzinfo=timezone.utc)
    assert result.timezone == "UTC"


def test_parse_z_suffix() -> None:
    result = parse_date("2024-01-02T08:30:00Z")
    assert result.date.hour == 8
    assert result.timezone == "UTC"
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

from miniparse.date_parser import parse_date


def test_empty_string_is_rejected() -> None:
    try:
        parse_date("")
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty date string")


def test_whitespace_only_is_rejected() -> None:
    try:
        parse_date("   ")
    except ValueError:
        return
    raise AssertionError("expected ValueError for whitespace-only date string")
""",
    )

    _write(
        task_dir / "issue.md",
        """\
# Fix date parsing for empty inputs

The `miniparse` parser library accepts blank date strings when it should reject them.

## Expected behavior

- Valid ISO-8601 strings should parse to a `ParsedDate` with `date` and `timezone`.
- Empty or whitespace-only strings should raise `ValueError`.

## How to verify

Run the public tests in the generated repository:

```bash
pytest tests/test_public.py
```

Hidden tests are unavailable during agent runs.
""",
    )

    metadata = {
        "task_id": task_id,
        "template": "parser",
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
                "module": "miniparse.date_parser",
                "name": "parse_date",
                "signature": "(value: str) -> ParsedDate",
            }
        ],
        "forbidden_patterns": ["test_public", "hidden_tests"],
        "expected_output_schema": {
            "type": "object",
            "required": ["date", "timezone"],
        },
    }
    _write(task_dir / "oracle.json", json.dumps(oracle, indent=2) + "\n")

    baseline_dir = task_dir / "baseline"
    shutil.copytree(repo_dir, baseline_dir)


def generate_parser_contract_task(task_dir: Path, seed: int) -> None:
    task_id = f"parser.contract.{seed:04d}"
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
name = "miniparse"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
where = ["src"]
""",
    )

    _write(
        repo_dir / "src" / "miniparse" / "__init__.py",
        """\
from miniparse.schema import DateField, ordered_field_names

__all__ = ["DateField", "ordered_field_names"]
""",
    )

    _write(
        repo_dir / "src" / "miniparse" / "schema.py",
        """\
from dataclasses import dataclass


@dataclass(frozen=True)
class DateField:
    name: str
    required: bool = True


def ordered_field_names(fields: list[DateField]) -> list[str]:
    fields.sort(key=lambda field: field.name)
    return [field.name for field in fields]
""",
    )

    _write(
        repo_dir / "src" / "miniparse" / "date_parser.py",
        """\
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ParsedDate:
    date: datetime
    timezone: str


def parse_date(value: str) -> ParsedDate:
    if value is None:
        raise ValueError("date value is required")

    text = value.strip()
    if not text:
        raise ValueError("date value is required")

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    tz_name = parsed.tzname() or "UTC"
    return ParsedDate(date=parsed, timezone=tz_name)
""",
    )

    _write(
        repo_dir / "tests" / "test_public.py",
        """\
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from miniparse.date_parser import parse_date
from miniparse.schema import DateField


def test_parse_valid_iso_date() -> None:
    result = parse_date("2024-03-15T12:00:00+00:00")
    assert result.date == datetime(2024, 3, 15, 12, 0, tzinfo=timezone.utc)
    assert result.timezone == "UTC"


def test_date_field_dataclass_is_accessible() -> None:
    field = DateField("due_at", required=False)
    assert field.name == "due_at"
    assert field.required is False
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

from miniparse.schema import DateField, ordered_field_names


def test_ordered_field_names_does_not_mutate_input() -> None:
    fields = [
        DateField("status"),
        DateField("due_at"),
        DateField("title"),
    ]
    original_order = [field.name for field in fields]

    assert ordered_field_names(fields) == ["due_at", "status", "title"]
    assert [field.name for field in fields] == original_order


def test_ordered_field_names_handles_single_field() -> None:
    fields = [DateField("only")]
    assert ordered_field_names(fields) == ["only"]
    assert [field.name for field in fields] == ["only"]
""",
    )

    _write(
        task_dir / "issue.md",
        """\
# Fix schema field ordering contract

The `miniparse` schema helper returns sorted field names for stable exports, but it
mutates the caller-provided field list in place.

## Expected behavior

- `ordered_field_names` should return names sorted alphabetically.
- The input `fields` list must keep its original order after the call.
- Existing date parsing behavior should remain unchanged.

## How to verify

Run the public tests in the generated repository:

```bash
pytest tests/test_public.py
```

Hidden tests cover non-mutating field ordering semantics.
""",
    )

    metadata = {
        "task_id": task_id,
        "template": "parser",
        "bug_family": "contract",
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
                "module": "miniparse.schema",
                "name": "ordered_field_names",
                "signature": "(fields: list[DateField]) -> list[str]",
            }
        ],
        "forbidden_patterns": ["test_public", "hidden_tests"],
        "expected_output_schema": {
            "type": "array",
            "items": {"type": "string"},
        },
    }
    _write(task_dir / "oracle.json", json.dumps(oracle, indent=2) + "\n")

    baseline_dir = task_dir / "baseline"
    shutil.copytree(repo_dir, baseline_dir)


def generate_parser_regression_trap_task(task_dir: Path, seed: int) -> None:
    task_id = f"parser.regression_trap.{seed:04d}"
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
name = "miniparse"
version = "0.1.0"
requires-python = ">=3.10"

[tool.setuptools.packages.find]
where = ["src"]
""",
    )

    _write(
        repo_dir / "src" / "miniparse" / "__init__.py",
        """\
from miniparse.record_parser import Field, parse_record

__all__ = ["Field", "parse_record"]
""",
    )

    _write(
        repo_dir / "src" / "miniparse" / "record_parser.py",
        """\
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    name: str
    required: bool = True


def parse_record(line: str, fields: list[Field], delimiter: str = ',') -> dict[str, str]:
    if line is None:
        raise ValueError("record line is required")

    parts = [part.strip() for part in line.split(delimiter)]
    if len(parts) != len(fields):
        raise ValueError(f"expected {len(fields)} fields, got {len(parts)}")

    result: dict[str, str] = {}
    for field, value in zip(fields, parts):
        if field.required and value == "":
            raise ValueError(f"field {field.name} is required")
        result[field.name] = value
    return result
""",
    )

    _write(
        repo_dir / "tests" / "test_public.py",
        """\
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from miniparse.record_parser import Field, parse_record


def test_parse_plain_record() -> None:
    fields = [Field("name"), Field("role")]
    assert parse_record("Ada,engineer", fields) == {
        "name": "Ada",
        "role": "engineer",
    }


def test_parse_quoted_comma_in_field() -> None:
    fields = [Field("name"), Field("role")]
    assert parse_record('"Ada, Lovelace",engineer', fields) == {
        "name": "Ada, Lovelace",
        "role": "engineer",
    }


def test_required_field_validation_still_runs() -> None:
    fields = [Field("name"), Field("role")]
    try:
        parse_record("Ada,", fields)
    except ValueError:
        return
    raise AssertionError("expected missing required field to fail")
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

from miniparse.record_parser import Field, parse_record


def test_multiple_quoted_commas_are_not_split() -> None:
    fields = [Field("title"), Field("owner"), Field("status")]
    assert parse_record('"alpha, beta, gamma",Dana,open', fields) == {
        "title": "alpha, beta, gamma",
        "owner": "Dana",
        "status": "open",
    }


def test_escaped_quotes_inside_quoted_field() -> None:
    fields = [Field("quote"), Field("speaker")]
    assert parse_record('\"\"\"Hello, Ada\"\"\",Grace', fields) == {
        "quote": '"Hello, Ada"',
        "speaker": "Grace",
    }


def test_optional_empty_field_is_preserved() -> None:
    fields = [Field("name"), Field("nickname", required=False), Field("role")]
    assert parse_record("Ada,,engineer", fields) == {
        "name": "Ada",
        "nickname": "",
        "role": "engineer",
    }


def test_custom_delimiter_with_quoted_delimiter() -> None:
    fields = [Field("path"), Field("owner")]
    assert parse_record('"src|miniparse"|Ada', fields, delimiter="|") == {
        "path": "src|miniparse",
        "owner": "Ada",
    }
""",
    )

    _write(
        task_dir / "issue.md",
        """\
# Fix quoted delimiter parsing

The `miniparse` record parser treats every delimiter character as a field split,
even when that delimiter appears inside a quoted field.

## Expected behavior

- Plain delimited records should keep working.
- Quoted fields may contain delimiters without increasing the field count.
- Required-field validation must still reject empty required fields.
- Optional empty fields should still be preserved as empty strings.

## How to verify

Run the public tests in the generated repository:

```bash
pytest tests/test_public.py
```

Hidden tests contain additional quoted-field variants and custom delimiters.
""",
    )

    metadata = {
        "task_id": task_id,
        "template": "parser",
        "bug_family": "regression_trap",
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
                "module": "miniparse.record_parser",
                "name": "parse_record",
                "signature": "(line: str, fields: list[Field], delimiter: str = ',') -> dict[str, str]",
            }
        ],
        "forbidden_patterns": ["test_public", "hidden_tests"],
        "expected_output_schema": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    }
    _write(task_dir / "oracle.json", json.dumps(oracle, indent=2) + "\n")

    baseline_dir = task_dir / "baseline"
    shutil.copytree(repo_dir, baseline_dir)
