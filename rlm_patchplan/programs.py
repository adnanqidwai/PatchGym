from __future__ import annotations

import importlib
from typing import Any

from rlm_patchplan.metrics import BUG_FAMILY_LABELS, REPAIR_OP_LABELS
from rlm_patchplan.openai_compatible import (
    DEFAULT_OPENAI_COMPATIBLE_MODEL,
    resolve_openai_compatible_config,
)
from rlm_patchplan.schema import PatchPlanPrediction, PatchPlanTask


DSPY_SIGNATURE_STRING = (
    "issue: str, failing_test_output: str, repo_files: dict[str, str] -> "
    "bug_file: str, bug_symbol: str, bug_family: str, repair_op: str, patch_plan: str"
)


def require_dspy() -> Any:
    try:
        return importlib.import_module("dspy")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "DSPy is required for this program. Install optional dependencies with "
            "`pip install -e .[dspy]` or `pip install dspy gepa`."
        ) from exc


DEFAULT_OPENAI_MODEL = "openai/gpt-4o-mini"


def make_dspy_lm(
    model: str | None = None,
    *,
    provider: str = "openai",
    api_key: str | None = None,
    api_base: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4000,
) -> Any:
    dspy = require_dspy()
    if provider == "openai-compatible":
        config = resolve_openai_compatible_config(
            model or DEFAULT_OPENAI_COMPATIBLE_MODEL,
            api_key=api_key,
            api_base=api_base,
        )
        base_lm_cls = dspy.LM

        class OpenAICompatibleReasoningFallbackLM(base_lm_cls):
            def _process_completion(self, response: Any, merged_kwargs: dict[str, Any]) -> list[Any]:
                outputs = super()._process_completion(response, merged_kwargs)
                normalized: list[Any] = []
                for output in outputs:
                    if isinstance(output, dict) and not output.get("text") and output.get("reasoning_content"):
                        normalized.append(str(output["reasoning_content"]))
                    else:
                        normalized.append(output)
                return normalized

        return OpenAICompatibleReasoningFallbackLM(
            **config.to_dspy_lm_kwargs(max_tokens=max_tokens, temperature=temperature)
        )
    if provider != "openai":
        raise ValueError(f"Unsupported provider: {provider}")

    kwargs: dict[str, object] = {
        "model": model or DEFAULT_OPENAI_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if api_key is not None:
        kwargs["api_key"] = api_key
    if api_base is not None:
        kwargs["api_base"] = api_base
    return dspy.LM(**kwargs)


def configure_dspy(
    model: str | None = None,
    *,
    provider: str = "openai",
    api_key: str | None = None,
    api_base: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4000,
) -> None:
    dspy = require_dspy()
    dspy.configure(
        lm=make_dspy_lm(
            model,
            provider=provider,
            api_key=api_key,
            api_base=api_base,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    )


def make_patchplan_signature() -> Any:
    dspy = require_dspy()
    family_labels = " | ".join(BUG_FAMILY_LABELS)
    repair_labels = " | ".join(REPAIR_OP_LABELS)

    class PatchPlanSignature(dspy.Signature):
        """Locate the root cause of a failing test in a small Python repository.

        Return schema IDs exactly. bug_family must be one of: boundary | contract | integration | regression_trap.
        repair_op must be one of: reject_blank_input | sort_schema_fields | thread_config_path | normalize_email_lookup.
        bug_symbol must be the bare function or method name, without parentheses or line text.
        """

        issue: str = dspy.InputField()
        failing_test_output: str = dspy.InputField()
        repo_files: dict[str, str] = dspy.InputField()

        bug_file: str = dspy.OutputField(desc="Repository-relative path to the file containing the root cause.")
        bug_symbol: str = dspy.OutputField(
            desc="bare function or method name for the root cause; do not include parentheses or line text."
        )
        bug_family: str = dspy.OutputField(desc=f"Exact label ID, one of: {family_labels}.")
        repair_op: str = dspy.OutputField(desc=f"Exact label ID, one of: {repair_labels}.")
        patch_plan: str = dspy.OutputField(desc="Concise natural-language patch plan.")

    return PatchPlanSignature


class HeuristicPatchPlanner:
    """No-API baseline for smoke tests and task sanity checks."""

    def predict(self, task: PatchPlanTask) -> PatchPlanPrediction:
        return self(
            issue=task.issue,
            failing_test_output=task.failing_test_output,
            repo_files=task.repo_files,
        )

    def __call__(
        self,
        *,
        issue: str,
        failing_test_output: str,
        repo_files: dict[str, str],
    ) -> PatchPlanPrediction:
        text = "\n".join([issue, failing_test_output, *repo_files.keys(), *repo_files.values()]).lower()

        if "blank" in text or "empty date" in text:
            return PatchPlanPrediction(
                bug_file=_choose_file(repo_files, "src/miniparse/date_parser.py"),
                bug_symbol="parse_date",
                bug_family="boundary",
                repair_op="reject_blank_input",
                patch_plan="Reject stripped-empty input before calling datetime.fromisoformat.",
            )

        if "stable alphabetical" in text or "serialize_fields" in text:
            return PatchPlanPrediction(
                bug_file=_choose_file(repo_files, "src/miniparse/schema.py"),
                bug_symbol="serialize_fields",
                bug_family="contract",
                repair_op="sort_schema_fields",
                patch_plan="Return sorted field names to preserve the documented public order.",
            )

        if "--config" in text or "load_settings()" in text:
            return PatchPlanPrediction(
                bug_file=_choose_file(repo_files, "src/minicli/main.py"),
                bug_symbol="main",
                bug_family="integration",
                repair_op="thread_config_path",
                patch_plan="Pass args['config'] into load_settings so the parsed path reaches configuration loading.",
            )

        if "case-insensitive" in text or "find_user" in text:
            return PatchPlanPrediction(
                bug_file=_choose_file(repo_files, "src/minidb/users.py"),
                bug_symbol="find_user",
                bug_family="regression_trap",
                repair_op="normalize_email_lookup",
                patch_plan="Normalize email comparison in the SQL predicate without changing the returned stored email.",
            )

        return PatchPlanPrediction(
            bug_file=next(iter(repo_files), ""),
            bug_symbol="",
            bug_family="",
            repair_op="",
            patch_plan="Insufficient deterministic clues; use the DSPy RLM program for deeper inspection.",
        )


def _choose_file(repo_files: dict[str, str], preferred: str) -> str:
    if preferred in repo_files:
        return preferred
    suffix = preferred.rsplit("/", maxsplit=1)[-1]
    for path in repo_files:
        if path.endswith(suffix):
            return path
    return preferred


def make_cot_patch_planner() -> Any:
    dspy = require_dspy()
    signature = make_patchplan_signature()

    class COTPatchPlanner(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.plan = dspy.ChainOfThought(signature)

        def forward(self, issue: str, failing_test_output: str, repo_files: dict[str, str]) -> Any:
            return self.plan(
                issue=issue,
                failing_test_output=failing_test_output,
                repo_files=repo_files,
            )

    return COTPatchPlanner()


def make_rlm_patch_planner(*, max_iterations: int = 6, max_llm_calls: int = 8, verbose: bool = False) -> Any:
    dspy = require_dspy()
    signature = make_patchplan_signature()

    class RLMPatchPlanner(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            try:
                self.plan = dspy.RLM(
                    signature,
                    max_iterations=max_iterations,
                    max_llm_calls=max_llm_calls,
                    verbose=verbose,
                )
            except TypeError:
                self.plan = dspy.RLM(
                    DSPY_SIGNATURE_STRING,
                    max_iterations=max_iterations,
                    max_llm_calls=max_llm_calls,
                    verbose=verbose,
                )

        def forward(self, issue: str, failing_test_output: str, repo_files: dict[str, str]) -> Any:
            return self.plan(
                issue=issue,
                failing_test_output=failing_test_output,
                repo_files=repo_files,
            )

    return RLMPatchPlanner()


def to_dspy_examples(tasks: list[PatchPlanTask]) -> list[Any]:
    dspy = require_dspy()
    examples = []
    for task in tasks:
        record = task.to_record()
        examples.append(dspy.Example(**record).with_inputs("issue", "failing_test_output", "repo_files"))
    return examples


def build_program(
    program: str,
    *,
    model: str | None = None,
    provider: str = "openai",
    api_key: str | None = None,
    api_base: str | None = None,
    max_tokens: int = 4000,
    rlm_max_iterations: int = 6,
    rlm_max_llm_calls: int = 8,
    artifact: str | None = None,
) -> Any:
    if program == "heuristic":
        return HeuristicPatchPlanner()

    configure_dspy(model, provider=provider, api_key=api_key, api_base=api_base, max_tokens=max_tokens)

    if program == "cot":
        return make_cot_patch_planner()
    if program == "rlm":
        return make_rlm_patch_planner(max_iterations=rlm_max_iterations, max_llm_calls=rlm_max_llm_calls)
    if program == "optimized":
        if not artifact:
            raise ValueError("--artifact is required for --program optimized")
        planner = make_rlm_patch_planner(max_iterations=rlm_max_iterations, max_llm_calls=rlm_max_llm_calls)
        planner.load(artifact)
        return planner

    raise ValueError(f"Unsupported program: {program}")
