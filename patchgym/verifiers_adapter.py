from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from patchgym.agents.openai_compatible import build_openai_compatible_prompt
from patchgym.env import score_completion_edits


try:
    import verifiers as vf  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:
    vf = None  # type: ignore[assignment]
    _VERIFIERS_IMPORT_ERROR = exc
else:
    _VERIFIERS_IMPORT_ERROR = None


def _require_verifiers() -> Any:
    if vf is None:
        raise RuntimeError(
            "Prime Intellect `verifiers` is required for this adapter. "
            "Install it with `pip install -e '.[verifiers]'`."
        ) from _VERIFIERS_IMPORT_ERROR
    return vf


def _task_dirs(tasks_dir: str | Path, *, limit: int | None = None) -> list[Path]:
    root = Path(tasks_dir)
    tasks = sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "metadata.json").is_file()
    )
    return tasks[:limit] if limit is not None else tasks


def build_task_record(task_dir: str | Path) -> dict[str, Any]:
    task_path = Path(task_dir)
    metadata = json.loads((task_path / "metadata.json").read_text(encoding="utf-8"))
    prompt = build_openai_compatible_prompt(task_path, task_path / "repo")
    return {
        "task_id": metadata["task_id"],
        "task_dir": str(task_path.resolve()),
        "prompt": [{"role": "user", "content": prompt}],
        "max_turns": 1,
        "info": json.dumps(
            {
                "template": metadata.get("template"),
                "bug_family": metadata.get("bug_family"),
                "difficulty": metadata.get("difficulty", "standard"),
            }
        ),
    }


def score_patchgym_completion(
    *,
    task_dir: str | Path,
    completion_text: str,
    reward_mode: str = "sparse",
) -> dict[str, Any]:
    return score_completion_edits(task_dir, completion_text, reward_mode=reward_mode)


if vf is None:

    class PatchGymTasksetConfig:  # pragma: no cover - exercised through _require_verifiers.
        tasks_dir: str = "generated_tasks"
        limit: int | None = None
        reward_mode: str = "sparse"

    class PatchGymTaskset:  # pragma: no cover - exercised only when verifiers is installed.
        pass

else:

    class PatchGymTasksetConfig(vf.TasksetConfig):
        tasks_dir: str = "generated_tasks"
        limit: int | None = None
        reward_mode: str = "sparse"

    class PatchGymTaskset(vf.Taskset):
        config_type = PatchGymTasksetConfig

        def __init__(self, config: PatchGymTasksetConfig | dict[str, Any] | None = None) -> None:
            super().__init__(source=self.load_tasks, eval_source=self.load_tasks, config=config)

        def load_tasks(self) -> Any:
            return [
                build_task_record(task_dir)
                for task_dir in _task_dirs(self.config.tasks_dir, limit=self.config.limit)
            ]

        def _completion_text(self, state: Any) -> str:
            messages = state.get("completion") or []
            assistant_contents: list[str] = []
            for message in messages:
                if isinstance(message, dict):
                    role = message.get("role")
                    content = message.get("content")
                else:
                    role = getattr(message, "role", None)
                    content = getattr(message, "content", None)
                if role == "assistant":
                    assistant_contents.append(str(content or ""))
            return assistant_contents[-1] if assistant_contents else ""

        def _score_state(self, task: Any, state: Any) -> dict[str, Any]:
            cached = state.get("patchgym_result")
            if isinstance(cached, dict):
                return cached
            result = score_patchgym_completion(
                task_dir=task["task_dir"],
                completion_text=self._completion_text(state),
                reward_mode=self.config.reward_mode,
            )
            state["patchgym_result"] = result
            return result

        @vf.reward(weight=1.0)
        async def patch_reward(self, task: Any, state: Any) -> float:
            return float(self._score_state(task, state)["reward"])

        @vf.metric
        async def solved(self, task: Any, state: Any) -> float:
            result = self._score_state(task, state)
            verification = result.get("verification") or {}
            return float(bool(verification.get("solved")))

        @vf.metric
        async def public_tests_passed(self, task: Any, state: Any) -> float:
            result = self._score_state(task, state)
            verification = result.get("verification") or {}
            return float(bool((verification.get("public_tests") or {}).get("passed")))

        @vf.metric
        async def hidden_tests_passed(self, task: Any, state: Any) -> float:
            result = self._score_state(task, state)
            verification = result.get("verification") or {}
            return float(bool((verification.get("hidden_tests") or {}).get("passed")))

        @vf.metric
        async def api_contract_passed(self, task: Any, state: Any) -> float:
            result = self._score_state(task, state)
            verification = result.get("verification") or {}
            return float(bool((verification.get("api_contract") or {}).get("passed")))

        @vf.metric
        async def patch_budget_passed(self, task: Any, state: Any) -> float:
            result = self._score_state(task, state)
            verification = result.get("verification") or {}
            return float(bool((verification.get("patch_budget") or {}).get("passed")))


def load_taskset(config: PatchGymTasksetConfig) -> PatchGymTaskset:
    _require_verifiers()
    return PatchGymTaskset(config=config)  # type: ignore[call-arg]


def _config_value(config: Any, name: str, default: Any = None) -> Any:
    if isinstance(config, dict):
        return config.get(name, default)
    return getattr(config, name, default)


def load_environment(config: Any) -> Any:
    verifiers = _require_verifiers()
    harness_config = _config_value(config, "harness")
    harness = verifiers.Harness(config=harness_config) if harness_config is not None else verifiers.Harness()
    return verifiers.Env(
        taskset=load_taskset(_config_value(config, "taskset", {})),
        harness=harness,
    )
