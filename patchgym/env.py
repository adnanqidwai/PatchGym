from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from patchgym.verifier.tests_runner import run_pytest
from patchgym.verify import build_verification_summary


READABLE_SUFFIXES = {".py", ".toml", ".md", ".txt", ".json"}
ACTION_TYPES = {"read_file", "write_file", "run_public_tests", "submit_patch", "submit"}


@dataclass(frozen=True)
class PatchGymEnvConfig:
    """Configuration for a local PatchGym coding-agent episode."""

    work_dir: str | Path | None = None
    max_steps: int | None = None
    reward_mode: str = "sparse"
    include_repo_files: bool = True
    include_test_output: bool = True
    expose_hidden_feedback: bool = False


@dataclass(frozen=True)
class PatchGymAction:
    type: str
    path: str | None = None
    content: str | None = None


@dataclass(frozen=True)
class PatchGymStepResult:
    observation: dict[str, Any]
    reward: float
    terminated: bool
    truncated: bool
    info: dict[str, Any]

    @property
    def done(self) -> bool:
        return self.terminated or self.truncated

    def to_record(self) -> dict[str, Any]:
        return {
            "observation": self.observation,
            "reward": self.reward,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "done": self.done,
            "info": self.info,
        }


def _append_trace(trace_path: Path, event: str, **extra: Any) -> None:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": event, **extra}) + "\n")


def _is_safe_relative_path(relative_path: str, *, for_write: bool) -> tuple[bool, str | None]:
    normalized = Path(relative_path)
    if normalized.is_absolute() or ".." in normalized.parts:
        return False, "path escapes repository"
    if for_write and normalized.parts and normalized.parts[0] == "tests":
        return False, "test edits are not allowed"
    if for_write and normalized.name in {"metadata.json", "oracle.json"}:
        return False, "generated metadata edits are not allowed"
    return True, None


def _repo_files(repo_dir: Path) -> dict[str, str]:
    ignored_dirs = {"__pycache__", ".pytest_cache", ".git"}
    files: dict[str, str] = {}
    for path in sorted(repo_dir.rglob("*")):
        if not path.is_file():
            continue
        if ignored_dirs.intersection(path.parts):
            continue
        if path.suffix not in READABLE_SUFFIXES:
            continue
        files[path.relative_to(repo_dir).as_posix()] = path.read_text(encoding="utf-8")
    return files


def score_verification_summary(summary: dict[str, Any], *, reward_mode: str = "sparse") -> float:
    if reward_mode == "sparse":
        return 1.0 if summary["solved"] else 0.0
    if reward_mode == "layered":
        weights = {
            "public_tests": 0.15,
            "hidden_tests": 0.45,
            "api_contract": 0.20,
            "patch_budget": 0.20,
        }
        return sum(weight for layer, weight in weights.items() if summary[layer]["passed"])
    raise ValueError(f"Unsupported reward mode: {reward_mode}")


def extract_json_edits(text: str) -> list[dict[str, str]]:
    stripped = text.strip()
    payload_text: str | None = None
    if stripped.startswith("{"):
        payload_text = stripped
    else:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if fenced:
            payload_text = fenced.group(1)
        else:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start != -1 and end != -1 and end > start:
                payload_text = stripped[start : end + 1]

    if payload_text is None:
        raise ValueError("completion did not contain a JSON object")

    payload = json.loads(payload_text)
    edits = payload.get("edits", [])
    if not isinstance(edits, list):
        raise ValueError("completion JSON field `edits` must be a list")

    normalized: list[dict[str, str]] = []
    for edit in edits:
        if not isinstance(edit, dict):
            raise ValueError("each edit must be an object")
        path = edit.get("path")
        content = edit.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            raise ValueError("each edit requires string `path` and `content` fields")
        normalized.append({"path": path, "content": content})
    return normalized


class PatchGymEnv:
    """Dependency-free RL-style episode API around a generated PatchGym task."""

    def __init__(self, task_dir: str | Path | None = None, *, config: PatchGymEnvConfig | None = None) -> None:
        self.config = config or PatchGymEnvConfig()
        self.task_dir: Path | None = None
        self.repo_dir: Path | None = None
        self.episode_dir: Path | None = None
        self.trace_path: Path | None = None
        self.metadata: dict[str, Any] = {}
        self.step_count = 0
        self.max_steps = 0
        self.terminated = False
        self.truncated = False
        self._owned_work_dir: Path | None = None
        self._last_public_tests: dict[str, Any] | None = None
        self._last_read: dict[str, str] | None = None
        self._last_verification: dict[str, Any] | None = None
        if task_dir is not None:
            self.reset(task_dir)

    def reset(self, task_dir: str | Path | None = None) -> dict[str, Any]:
        if task_dir is not None:
            self.task_dir = Path(task_dir).resolve()
        if self.task_dir is None:
            raise ValueError("reset requires a task_dir on first use")

        task_path = self.task_dir
        self.metadata = json.loads((task_path / "metadata.json").read_text(encoding="utf-8"))
        task_id = self.metadata["task_id"]
        self.max_steps = int(self.config.max_steps or self.metadata.get("max_steps", 40))
        self.step_count = 0
        self.terminated = False
        self.truncated = False
        self._last_public_tests = None
        self._last_read = None
        self._last_verification = None

        self.cleanup()
        if self.config.work_dir is None:
            episode_dir = Path(tempfile.mkdtemp(prefix=f"patchgym-{task_id}-"))
            self._owned_work_dir = episode_dir
        else:
            episode_dir = Path(self.config.work_dir).resolve() / task_id
            if episode_dir.exists():
                shutil.rmtree(episode_dir)
            episode_dir.mkdir(parents=True, exist_ok=True)
            self._owned_work_dir = None

        self.episode_dir = episode_dir
        self.repo_dir = episode_dir / "repo"
        shutil.copytree(task_path / "repo", self.repo_dir)
        self.trace_path = episode_dir / "trace.jsonl"
        _append_trace(self.trace_path, "episode_started", task_id=task_id)
        return self._observation()

    def close(self) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self._owned_work_dir is not None and self._owned_work_dir.exists():
            shutil.rmtree(self._owned_work_dir)
        self._owned_work_dir = None

    def step(self, action: PatchGymAction | dict[str, Any]) -> PatchGymStepResult:
        if self.repo_dir is None or self.task_dir is None or self.trace_path is None:
            raise RuntimeError("reset must be called before step")
        if self.terminated or self.truncated:
            raise RuntimeError("episode is already done")

        normalized = self._normalize_action(action)
        self.step_count += 1
        info: dict[str, Any] = {
            "task_id": self.metadata["task_id"],
            "action": normalized.type,
            "repo_dir": str(self.repo_dir),
            "trace_path": str(self.trace_path),
            "accepted": True,
        }
        reward = 0.0

        if normalized.type == "read_file":
            self._handle_read_file(normalized, info)
        elif normalized.type == "write_file":
            self._handle_write_file(normalized, info)
        elif normalized.type == "run_public_tests":
            self._handle_run_public_tests(info)
        elif normalized.type in {"submit_patch", "submit"}:
            summary = build_verification_summary(self.task_dir, self.repo_dir)
            self._last_verification = self._sanitize_verification(summary)
            reward = score_verification_summary(summary, reward_mode=self.config.reward_mode)
            self.terminated = True
            info["verification"] = self._last_verification
            info["solved"] = summary["solved"]
            _append_trace(self.trace_path, "submit_patch", solved=summary["solved"], reward=reward)
        else:
            info["accepted"] = False
            info["error"] = f"unsupported action type: {normalized.type}"
            _append_trace(self.trace_path, "action_rejected", action=normalized.type, reason=info["error"])

        if not self.terminated and self.step_count >= self.max_steps:
            self.truncated = True
            info["truncation_reason"] = "max_steps"
            _append_trace(self.trace_path, "episode_truncated", max_steps=self.max_steps)

        return PatchGymStepResult(
            observation=self._observation(),
            reward=reward,
            terminated=self.terminated,
            truncated=self.truncated,
            info=info,
        )

    def _normalize_action(self, action: PatchGymAction | dict[str, Any]) -> PatchGymAction:
        if isinstance(action, PatchGymAction):
            return action
        if not isinstance(action, dict):
            raise TypeError("action must be a PatchGymAction or dict")
        return PatchGymAction(
            type=str(action.get("type", "")),
            path=action.get("path") if isinstance(action.get("path"), str) else None,
            content=action.get("content") if isinstance(action.get("content"), str) else None,
        )

    def _handle_read_file(self, action: PatchGymAction, info: dict[str, Any]) -> None:
        assert self.repo_dir is not None and self.trace_path is not None
        if not action.path:
            info["accepted"] = False
            info["error"] = "read_file requires path"
            return
        safe, reason = _is_safe_relative_path(action.path, for_write=False)
        target = self.repo_dir / action.path
        if not safe or not target.is_file():
            info["accepted"] = False
            info["error"] = reason or "file does not exist"
            _append_trace(self.trace_path, "read_file_rejected", path=action.path, reason=info["error"])
            return
        content = target.read_text(encoding="utf-8")
        self._last_read = {"path": action.path, "content": content}
        info["path"] = action.path
        info["content"] = content
        _append_trace(self.trace_path, "read_file", path=action.path)

    def _handle_write_file(self, action: PatchGymAction, info: dict[str, Any]) -> None:
        assert self.repo_dir is not None and self.trace_path is not None
        if not action.path or action.content is None:
            info["accepted"] = False
            info["error"] = "write_file requires path and content"
            return
        safe, reason = _is_safe_relative_path(action.path, for_write=True)
        target = self.repo_dir / action.path
        if not safe or not target.is_file():
            info["accepted"] = False
            info["error"] = reason or "target file does not exist"
            _append_trace(self.trace_path, "write_file_rejected", path=action.path, reason=info["error"])
            return
        target.write_text(action.content, encoding="utf-8")
        info["path"] = action.path
        _append_trace(self.trace_path, "write_file", path=action.path)

    def _handle_run_public_tests(self, info: dict[str, Any]) -> None:
        assert self.repo_dir is not None and self.trace_path is not None
        result = run_pytest(self.repo_dir / "tests" / "test_public.py", cwd=self.repo_dir)
        self._last_public_tests = {
            "passed": result["passed"],
            "returncode": result["returncode"],
        }
        if self.config.include_test_output:
            self._last_public_tests["stdout"] = result["stdout"]
            self._last_public_tests["stderr"] = result["stderr"]
        info["public_tests"] = self._last_public_tests
        _append_trace(self.trace_path, "run_public_tests", passed=result["passed"])

    def _sanitize_verification(self, summary: dict[str, Any]) -> dict[str, Any]:
        if self.config.expose_hidden_feedback:
            return summary
        return {
            **summary,
            "hidden_tests": {"passed": summary["hidden_tests"]["passed"]},
        }

    def _observation(self) -> dict[str, Any]:
        if self.task_dir is None or self.repo_dir is None:
            return {}
        issue = (self.task_dir / "issue.md").read_text(encoding="utf-8")
        observation: dict[str, Any] = {
            "task_id": self.metadata["task_id"],
            "issue": issue,
            "step": self.step_count,
            "max_steps": self.max_steps,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "repo_dir": str(self.repo_dir),
            "action_types": sorted(ACTION_TYPES),
        }
        if self.config.include_repo_files:
            observation["repo_files"] = _repo_files(self.repo_dir)
        if self._last_read is not None:
            observation["last_read"] = self._last_read
        if self._last_public_tests is not None:
            observation["last_public_tests"] = self._last_public_tests
        if self._last_verification is not None:
            observation["last_verification"] = self._last_verification
        return observation


def run_edit_episode(
    task_dir: str | Path,
    edits: list[dict[str, str]],
    *,
    work_dir: str | Path | None = None,
    reward_mode: str = "sparse",
    keep_work_dir: bool = False,
) -> dict[str, Any]:
    env = PatchGymEnv(
        config=PatchGymEnvConfig(
            work_dir=work_dir,
            reward_mode=reward_mode,
            include_repo_files=False,
        )
    )
    env.reset(task_dir)
    step_records: list[dict[str, Any]] = []
    try:
        for edit in edits:
            step_records.append(
                env.step(
                    {
                        "type": "write_file",
                        "path": edit["path"],
                        "content": edit["content"],
                    }
                ).to_record()
            )
        final = env.step({"type": "submit_patch"})
        step_records.append(final.to_record())
        return {
            "task_id": env.metadata["task_id"],
            "reward": final.reward,
            "terminated": final.terminated,
            "truncated": final.truncated,
            "verification": final.info.get("verification"),
            "steps": step_records,
            "repo_dir": str(env.repo_dir),
        }
    finally:
        if not keep_work_dir:
            env.close()


def score_completion_edits(
    task_dir: str | Path,
    completion_text: str,
    *,
    reward_mode: str = "sparse",
) -> dict[str, Any]:
    try:
        edits = extract_json_edits(completion_text)
    except Exception as exc:
        return {
            "reward": 0.0,
            "terminated": True,
            "truncated": False,
            "verification": None,
            "error": str(exc),
        }
    return run_edit_episode(task_dir, edits, reward_mode=reward_mode)
