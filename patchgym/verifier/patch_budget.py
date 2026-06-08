from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any


def _count_line_changes(baseline_lines: list[str], repo_lines: list[str]) -> int:
    matcher = difflib.SequenceMatcher(None, baseline_lines, repo_lines)
    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed += max(i2 - i1, j2 - j1)
    return changed


def _iter_files(root: Path) -> list[Path]:
    ignored_dirs = {"__pycache__", ".pytest_cache"}
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not ignored_dirs.intersection(path.parts)
        and path.suffix != ".pyc"
    )


def _relative_lines(path: Path, root: Path) -> list[str]:
    text = path.read_text()
    return text.splitlines(keepends=True)


def check_patch_budget(
    repo_dir: Path,
    baseline_dir: Path,
    limits: dict[str, int],
) -> dict[str, Any]:
    repo_files = {file.relative_to(repo_dir) for file in _iter_files(repo_dir)}
    baseline_files = {file.relative_to(baseline_dir) for file in _iter_files(baseline_dir)}
    all_files = sorted(repo_files | baseline_files)

    files_touched = 0
    lines_changed = 0

    for relative in all_files:
        repo_file = repo_dir / relative
        baseline_file = baseline_dir / relative
        if not repo_file.is_file() or not baseline_file.is_file():
            files_touched += 1
            if repo_file.is_file():
                lines_changed += len(repo_file.read_text().splitlines())
            if baseline_file.is_file():
                lines_changed += len(baseline_file.read_text().splitlines())
            continue

        repo_lines = _relative_lines(repo_file, repo_dir)
        baseline_lines = _relative_lines(baseline_file, baseline_dir)
        if repo_lines == baseline_lines:
            continue

        files_touched += 1
        lines_changed += _count_line_changes(baseline_lines, repo_lines)

    max_files = limits.get("max_files_touched", 3)
    max_lines = limits.get("max_lines_changed", 80)
    passed = files_touched <= max_files and lines_changed <= max_lines

    return {
        "passed": passed,
        "files_touched": files_touched,
        "lines_changed": lines_changed,
        "max_files_touched": max_files,
        "max_lines_changed": max_lines,
    }
