from pathlib import Path
import re
import tomllib

from test_patchgym_mvp import run_patchgym


ROOT = Path(__file__).resolve().parents[1]


def test_dspy_extra_lets_dspy_resolve_its_own_gepa_pin() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())

    dspy_extra = metadata["project"]["optional-dependencies"]["dspy"]

    assert "dspy>=3.2.0" in dspy_extra
    assert not any(requirement.startswith("gepa>=") for requirement in dspy_extra)


def test_pytest_is_dev_dependency_not_runtime() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())

    runtime_dependencies = metadata["project"].get("dependencies", [])
    dev_dependencies = metadata["project"]["optional-dependencies"]["dev"]

    assert not any(requirement.startswith("pytest") for requirement in runtime_dependencies)
    assert any(requirement.startswith("pytest") for requirement in dev_dependencies)


def test_command_agent_help_describes_argv_not_shell() -> None:
    result = run_patchgym("run", "--help")

    assert result.returncode == 0, result.stderr
    assert "Command argv string" in result.stdout
    assert "Shell command" not in result.stdout


def test_ci_workflow_is_present() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"

    assert workflow.is_file()
    text = workflow.read_text()
    assert "python -m pytest -q" in text


def test_design_doc_is_present() -> None:
    design_doc = ROOT / "docs" / "design.md"

    assert design_doc.is_file()
    text = design_doc.read_text()
    assert "Verifier Stack" in text
    assert "RLM-PatchPlan" in text


def test_readme_avoids_meta_release_sections() -> None:
    readme = (ROOT / "README.md").read_text()

    banned = (
        "Repository Hygiene",
        "Current Limitations",
        "Related Project",
        "Why This Exists",
        "resume",
        "sibling project",
    )
    assert not any(phrase in readme for phrase in banned)


def test_public_files_do_not_mention_secret_literals() -> None:
    banned = (
        re.compile(r"(?<![a-z0-9])sk-[a-z0-9_-]{8,}", re.IGNORECASE),
        re.compile(r"bearer\s+ey[a-z0-9_-]{8,}", re.IGNORECASE),
    )
    checked_suffixes = {".py", ".md", ".toml", ".sh", ".yml", ".yaml"}
    ignored_parts = {
        ".venv",
        ".pytest_cache",
        "__pycache__",
        "artifacts",
        "data",
        "generated_tasks",
        "reports",
        "runs",
    }
    offenders: list[str] = []

    for path in ROOT.rglob("*"):
        if ".git" in path.parts or any(part in ignored_parts for part in path.parts):
            continue
        if path.is_file() and path.suffix in checked_suffixes:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for pattern in banned:
                if pattern.search(text):
                    offenders.append(f"{path.relative_to(ROOT)} contains {pattern.pattern}")

    assert offenders == []
