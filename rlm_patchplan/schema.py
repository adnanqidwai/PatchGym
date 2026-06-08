from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PatchPlanOracle:
    bug_file: str
    bug_symbol: str
    bug_family: str
    repair_op: str

    @classmethod
    def from_obj(cls, value: Any) -> "PatchPlanOracle":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(
                bug_file=str(value["bug_file"]),
                bug_symbol=str(value["bug_symbol"]),
                bug_family=str(value["bug_family"]),
                repair_op=str(value["repair_op"]),
            )
        return cls(
            bug_file=str(getattr(value, "bug_file")),
            bug_symbol=str(getattr(value, "bug_symbol")),
            bug_family=str(getattr(value, "bug_family")),
            repair_op=str(getattr(value, "repair_op")),
        )


@dataclass(frozen=True)
class PatchPlanTask:
    task_id: str
    split: str
    issue: str
    failing_test_output: str
    repo_files: dict[str, str]
    oracle: PatchPlanOracle

    def to_record(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "split": self.split,
            "issue": self.issue,
            "failing_test_output": self.failing_test_output,
            "repo_files": dict(self.repo_files),
            "oracle": asdict(self.oracle),
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "PatchPlanTask":
        return cls(
            task_id=str(record["task_id"]),
            split=str(record["split"]),
            issue=str(record["issue"]),
            failing_test_output=str(record["failing_test_output"]),
            repo_files={str(key): str(value) for key, value in record["repo_files"].items()},
            oracle=PatchPlanOracle.from_obj(record["oracle"]),
        )


@dataclass(frozen=True)
class PatchPlanPrediction:
    bug_file: str
    bug_symbol: str
    bug_family: str
    repair_op: str
    patch_plan: str

    @classmethod
    def from_obj(cls, value: Any) -> "PatchPlanPrediction":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(
                bug_file=str(value.get("bug_file", "")),
                bug_symbol=str(value.get("bug_symbol", "")),
                bug_family=str(value.get("bug_family", "")),
                repair_op=str(value.get("repair_op", "")),
                patch_plan=str(value.get("patch_plan", "")),
            )
        return cls(
            bug_file=str(getattr(value, "bug_file", "")),
            bug_symbol=str(getattr(value, "bug_symbol", "")),
            bug_family=str(getattr(value, "bug_family", "")),
            repair_op=str(getattr(value, "repair_op", "")),
            patch_plan=str(getattr(value, "patch_plan", "")),
        )

    def to_record(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MetricResult:
    score: float
    feedback: str
    components: dict[str, bool]
