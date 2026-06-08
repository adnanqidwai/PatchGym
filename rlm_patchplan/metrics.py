from __future__ import annotations

import ast
import re
from typing import Any

from rlm_patchplan.schema import MetricResult, PatchPlanOracle, PatchPlanPrediction


BUG_FAMILY_LABELS = ("boundary", "contract", "integration", "regression_trap")
REPAIR_OP_LABELS = (
    "reject_blank_input",
    "sort_schema_fields",
    "thread_config_path",
    "normalize_email_lookup",
)
FIELD_WEIGHTS = {
    "bug_file": 0.35,
    "bug_symbol": 0.25,
    "bug_family": 0.20,
    "repair_op": 0.20,
}


def _get_value(obj: Any, name: str, default: Any = "") -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _get_oracle(example: Any) -> PatchPlanOracle:
    oracle = _get_value(example, "oracle")
    return PatchPlanOracle.from_obj(oracle)


def _normalize(value: Any) -> str:
    return str(value).strip()


def _get_repo_files(example: Any) -> dict[str, str]:
    repo_files = _get_value(example, "repo_files", {})
    if isinstance(repo_files, dict):
        return {str(path): str(contents) for path, contents in repo_files.items()}
    return {}


def _canonical_file(value: str, repo_files: dict[str, str]) -> str:
    normalized = _normalize(value)
    if normalized in repo_files:
        return normalized

    basename = normalized.rsplit("/", maxsplit=1)[-1]
    matches = [path for path in repo_files if path.rsplit("/", maxsplit=1)[-1] == basename]
    if len(matches) == 1:
        return matches[0]
    return normalized


def _candidate_symbols(repo_files: dict[str, str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for contents in repo_files.values():
        try:
            tree = ast.parse(contents)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name not in seen:
                names.append(node.name)
                seen.add(node.name)
    return names


def _canonical_symbol(value: str, patch_plan: str, repo_files: dict[str, str]) -> str:
    normalized = _normalize(value).strip("`")
    call_match = re.fullmatch(r"([A-Za-z_]\w*)\s*\([^)]*\)", normalized)
    if call_match:
        normalized = call_match.group(1)

    candidates = _candidate_symbols(repo_files)
    if normalized in candidates:
        return normalized

    direct_matches = [
        name for name in candidates if re.search(rf"\b{re.escape(name)}\b", _normalize(value))
    ]
    if len(direct_matches) == 1:
        return direct_matches[0]

    plan_matches = [
        name for name in candidates if re.search(rf"\b{re.escape(name)}\b", patch_plan)
    ]
    if len(plan_matches) == 1:
        return plan_matches[0]
    return normalized


def _first_label_match(text: str, label_keywords: list[tuple[str, tuple[str, ...]]]) -> str | None:
    lower_text = text.lower()
    for label, keywords in label_keywords:
        if label in lower_text or any(keyword in lower_text for keyword in keywords):
            return label
    return None


def _canonical_family(value: str) -> str:
    normalized = _normalize(value)
    if normalized in BUG_FAMILY_LABELS:
        return normalized

    matched = _first_label_match(
        normalized,
        [
            (
                "boundary",
                (
                    "blank",
                    "empty",
                    "whitespace",
                    "epoch",
                    "valueerror",
                    "inputvalidation",
                    "input validation",
                    "silent fallback",
                    "silent failure",
                ),
            ),
            ("contract", ("ordering", "alphabet", "insertion", "schema", "field")),
            (
                "integration",
                (
                    "--config",
                    "config",
                    "load_settings",
                    "argument propagation",
                    "argument passing",
                    "missing argument",
                    "not passed",
                    "thread",
                ),
            ),
            (
                "regression_trap",
                (
                    "regression",
                    "case-sensitivity",
                    "case sensitivity",
                    "case_insensitive",
                    "case-insensitive",
                    "email",
                    "sql",
                    "database",
                    "lower(",
                ),
            ),
        ],
    )
    return matched or normalized


def _canonical_repair(value: str, patch_plan: str) -> str:
    normalized = _normalize(value)
    if normalized in REPAIR_OP_LABELS:
        return normalized

    text = f"{normalized}\n{patch_plan}"
    matched = _first_label_match(
        text,
        [
            (
                "normalize_email_lookup",
                (
                    "lower(email)",
                    "case-insensitive",
                    "case insensitive",
                    "email case",
                    "email lookup",
                ),
            ),
            (
                "thread_config_path",
                (
                    'args["config"]',
                    "args['config']",
                    "--config",
                    "config path",
                    "parsed config",
                    "load_settings(args",
                ),
            ),
            (
                "sort_schema_fields",
                (
                    "sorted(",
                    "return sorted",
                    "sort",
                    "alphabetical",
                    "field names",
                    "dictionary keys",
                ),
            ),
            (
                "reject_blank_input",
                (
                    "valueerror",
                    "blank",
                    "empty",
                    "whitespace",
                    "silent fallback",
                    "reject invalid input",
                ),
            ),
        ],
    )
    return matched or normalized


def canonicalize_prediction(example: Any, pred: Any) -> PatchPlanPrediction:
    prediction = PatchPlanPrediction.from_obj(pred)
    repo_files = _get_repo_files(example)
    return PatchPlanPrediction(
        bug_file=_canonical_file(prediction.bug_file, repo_files),
        bug_symbol=_canonical_symbol(prediction.bug_symbol, prediction.patch_plan, repo_files),
        bug_family=_canonical_family(prediction.bug_family),
        repair_op=_canonical_repair(prediction.repair_op, prediction.patch_plan),
        patch_plan=prediction.patch_plan,
    )


def score_patchplan(example: Any, pred: Any, *, canonicalize: bool = False) -> MetricResult:
    oracle = _get_oracle(example)
    prediction = canonicalize_prediction(example, pred) if canonicalize else PatchPlanPrediction.from_obj(pred)
    components: dict[str, bool] = {}
    feedback_parts: list[str] = []
    score = 0.0

    for field, weight in FIELD_WEIGHTS.items():
        predicted = _normalize(getattr(prediction, field))
        expected = _normalize(getattr(oracle, field))
        is_correct = predicted == expected
        components[field] = is_correct
        if is_correct:
            score += weight
            feedback_parts.append(f"{field} correct.")
        else:
            feedback_parts.append(f"{field} wrong: predicted {predicted}, expected {expected}.")

    issue = _normalize(_get_value(example, "issue"))
    failing_test_output = _normalize(_get_value(example, "failing_test_output"))
    if issue:
        feedback_parts.append(f"Issue: {issue}")
    if failing_test_output:
        feedback_parts.append(f"Failing test output: {failing_test_output[:1000]}")
    if prediction.patch_plan:
        feedback_parts.append(f"Patch plan: {prediction.patch_plan}")

    return MetricResult(score=score, feedback="\n".join(feedback_parts), components=components)


def patchplan_metric(
    example: Any,
    pred: Any,
    trace: Any | None = None,
    pred_name: str | None = None,
    pred_trace: Any | None = None,
) -> Any:
    del trace, pred_name, pred_trace
    result = score_patchplan(example, pred)

    try:
        import dspy  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return result

    return dspy.Prediction(score=result.score, feedback=result.feedback)
