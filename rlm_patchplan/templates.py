from __future__ import annotations

from collections.abc import Callable

from rlm_patchplan.schema import PatchPlanOracle, PatchPlanTask


TaskBuilder = Callable[[int, str], PatchPlanTask]


def _parser_boundary_task(seed: int, split: str) -> PatchPlanTask:
    task_id = f"parser.boundary.{seed:04d}"
    hidden_case = f"blank_{seed:04d}"
    sample_date = f"2024-03-{(seed % 20) + 1:02d}T12:00:00+00:00"
    return PatchPlanTask(
        task_id=task_id,
        split=split,
        issue=f"{hidden_case}: "
        + (
            "The miniparse date parser accepts empty or whitespace-only date strings. "
            "Blank date input should raise ValueError instead of silently becoming the epoch."
        ),
        failing_test_output=f"""\
tests/test_hidden.py::test_{hidden_case}_is_rejected FAILED
E   AssertionError: expected ValueError for empty date string

Traceback (most recent call last):
  File "tests/test_hidden.py", line 10, in test_empty_string_is_rejected
    parse_date("")
  File "src/miniparse/date_parser.py", line 15, in parse_date
    parsed = datetime(1970, 1, 1, tzinfo=timezone.utc)
""",
        repo_files={
            "src/miniparse/date_parser.py": """\
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

    return ParsedDate(date=parsed, timezone=parsed.tzname() or "UTC")
""",
            "src/miniparse/schema.py": """\
from dataclasses import dataclass


@dataclass(frozen=True)
class DateField:
    name: str
    required: bool = True
""",
            "tests/test_public.py": f"""\
from miniparse.date_parser import parse_date


def test_parse_valid_iso_date():
    assert parse_date("{sample_date}").timezone == "UTC"
""",
        },
        oracle=PatchPlanOracle(
            bug_file="src/miniparse/date_parser.py",
            bug_symbol="parse_date",
            bug_family="boundary",
            repair_op="reject_blank_input",
        ),
    )


def _parser_contract_task(seed: int, split: str) -> PatchPlanTask:
    task_id = f"parser.contract.{seed:04d}"
    late_field = f"field_{seed:04d}_b"
    early_field = f"field_{seed:04d}_a"
    return PatchPlanTask(
        task_id=task_id,
        split=split,
        issue=f"{task_id}: "
        + (
            "The public schema serializer returns fields in insertion order. "
            "The documented contract requires stable alphabetical ordering."
        ),
        failing_test_output=f"""\
tests/test_contract.py::test_fields_are_stably_ordered FAILED
E   AssertionError: assert ['{late_field}', '{early_field}'] == ['{early_field}', '{late_field}']

Traceback (most recent call last):
  File "tests/test_contract.py", line 7, in test_fields_are_stably_ordered
    assert serialize_fields({{"{late_field}": "late", "{early_field}": "early"}}) == ["{early_field}", "{late_field}"]
  File "src/miniparse/schema.py", line 9, in serialize_fields
    return list(fields)
""",
        repo_files={
            "src/miniparse/schema.py": """\
def serialize_fields(fields: dict[str, object]) -> list[str]:
    \"\"\"Return the public schema field names in stable order.\"\"\"
    return list(fields)
""",
            "src/miniparse/date_parser.py": """\
def parse_date(value: str) -> str:
    return value.strip()
""",
            "tests/test_public.py": """\
from miniparse.schema import serialize_fields


def test_single_field():
    assert serialize_fields({"date": "2024-01-02"}) == ["date"]
""",
        },
        oracle=PatchPlanOracle(
            bug_file="src/miniparse/schema.py",
            bug_symbol="serialize_fields",
            bug_family="contract",
            repair_op="sort_schema_fields",
        ),
    )


def _cli_integration_task(seed: int, split: str) -> PatchPlanTask:
    task_id = f"cli.integration.{seed:04d}"
    config_name = f"project_{seed:04d}.toml"
    profile_name = f"project_{seed:04d}"
    return PatchPlanTask(
        task_id=task_id,
        split=split,
        issue=f"{task_id}: "
        + (
            "The minicli command accepts --config but still loads default settings. "
            "The config path is parsed correctly and then dropped before settings are loaded."
        ),
        failing_test_output=f"""\
tests/test_cli.py::test_uses_config_file FAILED
E   AssertionError: assert 'default' == '{profile_name}'

Traceback (most recent call last):
  File "tests/test_cli.py", line 18, in test_uses_config_file
    assert main(["--config", "{config_name}"]) == "{profile_name}"
  File "src/minicli/main.py", line 21, in main
    settings = load_settings()
""",
        repo_files={
            "src/minicli/main.py": """\
from minicli.config import load_settings


def parse_args(argv: list[str]) -> dict[str, str | None]:
    if "--config" in argv:
        index = argv.index("--config")
        return {"config": argv[index + 1]}
    return {"config": None}


def main(argv: list[str]) -> str:
    args = parse_args(argv)
    settings = load_settings()
    return settings["profile"]
""",
            "src/minicli/config.py": f"""\
def load_settings(path: str | None = None) -> dict[str, str]:
    if path == "{config_name}":
        return {{"profile": "{profile_name}"}}
    return {{"profile": "default"}}
""",
            "tests/test_public.py": """\
from minicli.main import main


def test_default_profile():
    assert main([]) == "default"
""",
        },
        oracle=PatchPlanOracle(
            bug_file="src/minicli/main.py",
            bug_symbol="main",
            bug_family="integration",
            repair_op="thread_config_path",
        ),
    )


def _sqlite_regression_task(seed: int, split: str) -> PatchPlanTask:
    task_id = f"sqlite.regression_trap.{seed:04d}"
    email = f"ada{seed:04d}@example.com"
    upper_email = email.upper()
    return PatchPlanTask(
        task_id=task_id,
        split=split,
        issue=f"{task_id}: "
        + (
            "The mini SQLite user lookup passes visible exact-case tests but hidden tests "
            "show a regression for emails with different casing."
        ),
        failing_test_output=(  # nosec B608
            "tests/test_hidden.py::test_find_user_is_case_insensitive FAILED\n"  # nosec B608
            f"E   AssertionError: assert None == {{'email': '{email}'}}\n\n"
            "Traceback (most recent call last):\n"
            '  File "tests/test_hidden.py", line 15, in test_find_user_is_case_insensitive\n'
            f'    assert find_user(conn, "{upper_email}") == {{"email": "{email}"}}\n'
            '  File "src/minidb/users.py", line 12, in find_user\n'
            '    row = conn.execute("select email from users where email = ?", (email,)).fetchone()\n'
        ),
        repo_files={
            "src/minidb/users.py": """\
import sqlite3


def find_user(conn: sqlite3.Connection, email: str) -> dict[str, str] | None:
    row = conn.execute("select email from users where email = ?", (email,)).fetchone()
    if row is None:
        return None
    return {"email": row[0]}
""",
            "src/minidb/schema.py": """\
CREATE_USERS_SQL = "create table users(email text primary key)"
""",
            "tests/test_public.py": f"""\
from minidb.users import find_user


def test_find_exact_email(conn):
    assert find_user(conn, "{email}") == {{"email": "{email}"}}
""",
        },
        oracle=PatchPlanOracle(
            bug_file="src/minidb/users.py",
            bug_symbol="find_user",
            bug_family="regression_trap",
            repair_op="normalize_email_lookup",
        ),
    )


TASK_BUILDERS: tuple[TaskBuilder, ...] = (
    _parser_boundary_task,
    _parser_contract_task,
    _cli_integration_task,
    _sqlite_regression_task,
)
