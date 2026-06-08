import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import ANY

import pytest

from rlm_patchplan.evaluate import build_parser as build_evaluate_parser
from rlm_patchplan.generate import generate_tasks, generate_tasks_jsonl
from rlm_patchplan.metrics import canonicalize_prediction, patchplan_metric, score_patchplan
from rlm_patchplan.optimize_gepa import build_parser as build_optimize_parser
from rlm_patchplan.openai_compatible import (
    DEFAULT_OPENAI_COMPATIBLE_MODEL,
    resolve_openai_compatible_config,
)
from rlm_patchplan.programs import configure_dspy, make_dspy_lm, make_patchplan_signature
from rlm_patchplan.report import build_report
from rlm_patchplan.schema import PatchPlanPrediction


ROOT = Path(__file__).resolve().parents[1]


def test_generate_tasks_jsonl_creates_deterministic_oracles(tmp_path: Path) -> None:
    out_file = tmp_path / "tasks.jsonl"

    generate_tasks_jsonl(out_file, n=8, seed=7)

    records = [json.loads(line) for line in out_file.read_text().splitlines()]
    assert len(records) == 8
    assert {record["split"] for record in records} == {"train", "dev", "test"}
    assert len({record["task_id"] for record in records}) == len(records)

    first = records[0]
    assert first["task_id"] == "parser.boundary.0007"
    assert first["split"] == "train"
    assert "src/miniparse/date_parser.py" in first["repo_files"]
    assert "tests/test_public.py" in first["repo_files"]
    assert first["oracle"] == {
        "bug_file": "src/miniparse/date_parser.py",
        "bug_symbol": "parse_date",
        "bug_family": "boundary",
        "repair_op": "reject_blank_input",
    }


def test_generate_tasks_uses_documented_mvp_split_for_eighty_examples() -> None:
    tasks = generate_tasks(n=80, seed=7)

    assert sum(task.split == "train" for task in tasks) == 40
    assert sum(task.split == "dev" for task in tasks) == 20
    assert sum(task.split == "test" for task in tasks) == 20


def test_generate_tasks_keeps_documented_train_dev_caps_for_larger_sets() -> None:
    tasks = generate_tasks(n=100, seed=7)

    assert sum(task.split == "train" for task in tasks) == 40
    assert sum(task.split == "dev" for task in tasks) == 20
    assert sum(task.split == "test" for task in tasks) == 40


def test_generate_tasks_varies_content_across_seeded_examples() -> None:
    tasks = generate_tasks(n=16, seed=7)

    fingerprints = {
        json.dumps(
            {
                "issue": task.issue,
                "failing_test_output": task.failing_test_output,
                "repo_files": task.repo_files,
                "oracle": task.oracle.__dict__,
            },
            sort_keys=True,
        )
        for task in tasks
    }
    assert len(fingerprints) == len(tasks)


def test_generate_tasks_requires_enough_examples_for_all_splits() -> None:
    with pytest.raises(ValueError, match="at least 4"):
        generate_tasks(n=3, seed=7)


def test_resolve_openai_compatible_config_builds_dspy_kwargs() -> None:
    config = resolve_openai_compatible_config(
        "openai-compatible/test-model",
        api_key="test-key",
        api_base="https://api.openai.com/v1",
    )

    assert config.model_name == "openai-compatible/test-model"
    assert config.api_base == "https://api.openai.com/v1"
    assert config.to_dspy_lm_kwargs(max_tokens=123, temperature=0.2) == {
        "model": "openai-compatible/test-model",
        "api_key": "test-key",
        "api_base": "https://api.openai.com/v1",
        "max_tokens": 123,
        "temperature": 0.2,
        "timeout": 180.0,
    }


def test_configure_dspy_can_use_openai_compatible_provider_without_printing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeLM:
        def __init__(self, **kwargs: object) -> None:
            calls["lm_kwargs"] = kwargs

    fake_dspy = types.SimpleNamespace(
        LM=FakeLM,
        configure=lambda **kwargs: calls.setdefault("configure_kwargs", kwargs),
    )
    monkeypatch.setitem(sys.modules, "dspy", fake_dspy)

    configure_dspy(
        "openai-compatible/test-model",
        provider="openai-compatible",
        api_key="secret-value",
        api_base="https://api.openai.com/v1",
        max_tokens=321,
    )

    assert calls["configure_kwargs"] == {"lm": ANY}
    assert calls["lm_kwargs"] == {
        "model": "openai-compatible/test-model",
        "api_key": "secret-value",
        "api_base": "https://api.openai.com/v1",
        "temperature": 0.0,
        "max_tokens": 321,
        "timeout": 180.0,
    }


def test_openai_compatible_lm_falls_back_to_reasoning_content(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLM:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def _process_completion(self, response: object, merged_kwargs: dict[str, object]) -> list[object]:
            return [{"text": None, "reasoning_content": '{"answer": "REASONING_OK"}'}]

    fake_dspy = types.SimpleNamespace(LM=FakeLM)
    monkeypatch.setitem(sys.modules, "dspy", fake_dspy)

    lm = make_dspy_lm("openai-compatible/test-model", provider="openai-compatible", api_key="secret-value")

    response = types.SimpleNamespace()
    assert lm._process_completion(response, {}) == ['{"answer": "REASONING_OK"}']


def test_evaluate_cli_accepts_openai_compatible_provider_flags() -> None:
    parser = build_evaluate_parser()

    args = parser.parse_args(
        [
            "--program",
            "rlm",
            "--provider",
            "openai-compatible",
            "--model",
            "openai-compatible/test-model",
            "--max-tokens",
            "1024",
            "--rlm-max-iterations",
            "2",
            "--rlm-max-llm-calls",
            "3",
            "--data",
            "data/tasks.jsonl",
            "--split",
            "test",
        ]
    )

    assert args.provider == "openai-compatible"
    assert args.model == "openai-compatible/test-model"
    assert args.max_tokens == 1024
    assert args.rlm_max_iterations == 2
    assert args.rlm_max_llm_calls == 3


def test_optimize_cli_accepts_openai_compatible_provider_for_student_and_reflection_models() -> None:
    parser = build_optimize_parser()

    args = parser.parse_args(
        [
            "--data",
            "data/tasks.jsonl",
            "--provider",
            "openai-compatible",
            "--model",
            DEFAULT_OPENAI_COMPATIBLE_MODEL,
            "--reflection-provider",
            "openai-compatible",
            "--reflection-model",
            "openai-compatible/reflection-model",
            "--rlm-max-iterations",
            "2",
            "--rlm-max-llm-calls",
            "3",
        ]
    )

    assert args.provider == "openai-compatible"
    assert args.model == DEFAULT_OPENAI_COMPATIBLE_MODEL
    assert args.reflection_provider == "openai-compatible"
    assert args.reflection_model == "openai-compatible/reflection-model"
    assert args.rlm_max_iterations == 2
    assert args.rlm_max_llm_calls == 3


def test_patchplan_metric_scores_components_and_returns_feedback() -> None:
    example = {
        "issue": "Date parser accepts blank input.",
        "failing_test_output": "E Failed: expected ValueError",
        "oracle": {
            "bug_file": "src/miniparse/date_parser.py",
            "bug_symbol": "parse_date",
            "bug_family": "boundary",
            "repair_op": "reject_blank_input",
        },
    }
    pred = PatchPlanPrediction(
        bug_file="src/miniparse/date_parser.py",
        bug_symbol="parse_timezone",
        bug_family="boundary",
        repair_op="bypass_validation",
        patch_plan="Change timezone parsing.",
    )

    scored = score_patchplan(example, pred)

    assert scored.score == pytest.approx(0.55)
    assert scored.components == {
        "bug_file": True,
        "bug_symbol": False,
        "bug_family": True,
        "repair_op": False,
    }
    assert "bug_symbol wrong: predicted parse_timezone, expected parse_date." in scored.feedback
    assert "repair_op wrong: predicted bypass_validation, expected reject_blank_input." in scored.feedback

    metric_result = patchplan_metric(example, pred)
    assert metric_result.score == pytest.approx(0.55)
    assert "Issue: Date parser accepts blank input." in metric_result.feedback


def test_canonicalized_score_preserves_raw_metric_but_maps_descriptive_labels() -> None:
    example = {
        "issue": "cli.integration.0012: The command accepts --config but still loads defaults.",
        "failing_test_output": "settings = load_settings()",
        "repo_files": {
            "src/minicli/main.py": (
                "def parse_args(argv):\n"
                "    return {'config': argv[-1]}\n\n"
                "def load_settings(path=None):\n"
                "    return {'profile': 'default'}\n\n"
                "def main(argv):\n"
                "    args = parse_args(argv)\n"
                "    settings = load_settings()\n"
                "    return settings['profile']\n"
            )
        },
        "oracle": {
            "bug_file": "src/minicli/main.py",
            "bug_symbol": "main",
            "bug_family": "integration",
            "repair_op": "thread_config_path",
        },
    }
    pred = PatchPlanPrediction(
        bug_file="src/minicli/main.py",
        bug_symbol="main()",
        bug_family="Incorrect Argument Propagation",
        repair_op='Pass args["config"] to load_settings() in main.',
        patch_plan="Thread the parsed config path through the main function.",
    )

    raw = score_patchplan(example, pred)
    canonical = score_patchplan(example, pred, canonicalize=True)

    assert raw.score == pytest.approx(0.35)
    assert canonical.score == pytest.approx(1.0)
    assert canonical.components == {
        "bug_file": True,
        "bug_symbol": True,
        "bug_family": True,
        "repair_op": True,
    }
    assert canonicalize_prediction(example, pred) == PatchPlanPrediction(
        bug_file="src/minicli/main.py",
        bug_symbol="main",
        bug_family="integration",
        repair_op="thread_config_path",
        patch_plan="Thread the parsed config path through the main function.",
    )


def test_patchplan_signature_describes_allowed_label_space(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeField:
        def __init__(self, *, desc: str = "") -> None:
            self.description = desc

    fake_dspy = types.SimpleNamespace(
        Signature=object,
        InputField=lambda **kwargs: FakeField(**kwargs),
        OutputField=lambda **kwargs: FakeField(**kwargs),
    )
    monkeypatch.setitem(sys.modules, "dspy", fake_dspy)

    signature = make_patchplan_signature()

    assert "boundary | contract | integration | regression_trap" in signature.bug_family.description
    assert (
        "reject_blank_input | sort_schema_fields | thread_config_path | normalize_email_lookup"
        in signature.repair_op.description
    )
    assert "bare function or method name" in signature.bug_symbol.description


def test_heuristic_evaluate_cli_outputs_metrics(tmp_path: Path) -> None:
    data_file = tmp_path / "tasks.jsonl"
    generate_tasks_jsonl(data_file, n=8, seed=7)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "rlm_patchplan.evaluate",
            "--program",
            "heuristic",
            "--data",
            str(data_file),
            "--split",
            "test",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["program"] == "heuristic"
    assert summary["split"] == "test"
    assert summary["example_count"] == 2
    assert summary["file_acc"] == pytest.approx(1.0)
    assert summary["symbol_acc"] == pytest.approx(1.0)
    assert summary["family_acc"] == pytest.approx(1.0)
    assert summary["repair_acc"] == pytest.approx(1.0)
    assert summary["total_score"] == pytest.approx(1.0)
    assert summary["canonical_file_acc"] == pytest.approx(1.0)
    assert summary["canonical_symbol_acc"] == pytest.approx(1.0)
    assert summary["canonical_family_acc"] == pytest.approx(1.0)
    assert summary["canonical_repair_acc"] == pytest.approx(1.0)
    assert summary["canonical_total_score"] == pytest.approx(1.0)


def test_report_includes_raw_and_canonical_metric_columns(tmp_path: Path) -> None:
    run_file = tmp_path / "run.json"
    run_file.write_text(
        json.dumps(
            {
                "program": "rlm",
                "split": "test",
                "file_acc": 1.0,
                "symbol_acc": 0.7,
                "family_acc": 0.0,
                "repair_acc": 0.0,
                "total_score": 0.525,
                "canonical_file_acc": 1.0,
                "canonical_symbol_acc": 0.9,
                "canonical_family_acc": 1.0,
                "canonical_repair_acc": 1.0,
                "canonical_total_score": 0.975,
                "avg_calls": 2.0,
                "examples": [],
            }
        )
    )

    report = build_report([run_file])

    assert "raw_total_score" in report
    assert "canonical_total_score" in report
    assert "| rlm | test | 1.00 | 0.70 | 0.00 | 0.00 | 0.53 | 1.00 | 0.90 | 1.00 | 1.00 | 0.97 | 2.00 |" in report
