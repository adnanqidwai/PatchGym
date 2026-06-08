import json
from pathlib import Path

import pytest

from patchgym.env import PatchGymEnv, PatchGymEnvConfig, score_completion_edits
from patchgym.generate import generate_tasks
from patchgym import verifiers_adapter
from test_patchgym_mvp import run_patchgym


def generate_parser_task(out_dir: Path) -> Path:
    generate_tasks(out_dir=out_dir, templates=["parser"], n=1, seed=42)
    return out_dir / "parser.boundary.0042"


def fixed_parser_source(task_dir: Path) -> str:
    source = (task_dir / "repo" / "src" / "miniparse" / "date_parser.py").read_text()
    return source.replace(
        "if value is None:",
        "if value is None or value.strip() == \"\":",
    )


def test_env_episode_accepts_file_edit_and_verifier_reward(tmp_path: Path) -> None:
    task_dir = generate_parser_task(tmp_path / "generated_tasks")
    env = PatchGymEnv(config=PatchGymEnvConfig(work_dir=tmp_path / "episodes"))

    obs = env.reset(task_dir)

    assert obs["task_id"] == "parser.boundary.0042"
    assert "src/miniparse/date_parser.py" in obs["repo_files"]
    assert "hidden_tests" not in json.dumps(obs)

    write_result = env.step(
        {
            "type": "write_file",
            "path": "src/miniparse/date_parser.py",
            "content": fixed_parser_source(task_dir),
        }
    )
    assert write_result.info["accepted"] is True
    assert write_result.reward == 0.0
    assert write_result.done is False

    public_result = env.step({"type": "run_public_tests"})
    assert public_result.info["public_tests"]["passed"] is True

    final = env.step({"type": "submit_patch"})

    assert final.terminated is True
    assert final.truncated is False
    assert final.reward == 1.0
    assert final.info["verification"]["solved"] is True


def test_env_rejects_test_file_edits(tmp_path: Path) -> None:
    task_dir = generate_parser_task(tmp_path / "generated_tasks")
    env = PatchGymEnv(config=PatchGymEnvConfig(work_dir=tmp_path / "episodes"))
    env.reset(task_dir)

    result = env.step(
        {
            "type": "write_file",
            "path": "tests/test_public.py",
            "content": "def test_cheat():\n    assert True\n",
        }
    )

    assert result.info["accepted"] is False
    assert result.info["error"] == "test edits are not allowed"
    assert "test_cheat" not in (Path(result.info["repo_dir"]) / "tests" / "test_public.py").read_text()


def test_env_layered_reward_exposes_partial_verifier_score(tmp_path: Path) -> None:
    task_dir = generate_parser_task(tmp_path / "generated_tasks")
    env = PatchGymEnv(
        config=PatchGymEnvConfig(
            work_dir=tmp_path / "episodes",
            reward_mode="layered",
        )
    )
    env.reset(task_dir)

    final = env.step({"type": "submit_patch"})

    assert final.terminated is True
    assert final.info["verification"]["public_tests"]["passed"] is True
    assert final.info["verification"]["hidden_tests"]["passed"] is False
    assert final.reward == pytest.approx(0.55)


def test_episode_cli_replays_jsonl_actions(tmp_path: Path) -> None:
    task_dir = generate_parser_task(tmp_path / "generated_tasks")
    actions_path = tmp_path / "actions.jsonl"
    actions = [
        {
            "type": "write_file",
            "path": "src/miniparse/date_parser.py",
            "content": fixed_parser_source(task_dir),
        },
        {"type": "run_public_tests"},
        {"type": "submit_patch"},
    ]
    actions_path.write_text("\n".join(json.dumps(action) for action in actions) + "\n")

    result = run_patchgym(
        "episode",
        "--task",
        str(task_dir),
        "--actions",
        str(actions_path),
        "--out",
        str(tmp_path / "episodes"),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["reward"] == 1.0
    assert summary["terminated"] is True
    assert summary["verification"]["solved"] is True
    assert (tmp_path / "episodes" / "parser.boundary.0042" / "episode_summary.json").is_file()


def test_completion_scoring_uses_patchgym_verifier(tmp_path: Path) -> None:
    task_dir = generate_parser_task(tmp_path / "generated_tasks")
    completion = json.dumps(
        {
            "edits": [
                {
                    "path": "src/miniparse/date_parser.py",
                    "content": fixed_parser_source(task_dir),
                }
            ]
        }
    )

    result = score_completion_edits(task_dir, completion)

    assert result["reward"] == 1.0
    assert result["verification"]["solved"] is True


def test_verifiers_adapter_pure_helpers_do_not_require_prime_install(tmp_path: Path) -> None:
    task_dir = generate_parser_task(tmp_path / "generated_tasks")
    record = verifiers_adapter.build_task_record(task_dir)

    assert record["task_id"] == "parser.boundary.0042"
    assert "hidden_tests" not in record["prompt"][0]["content"]

    scored = verifiers_adapter.score_patchgym_completion(
        task_dir=task_dir,
        completion_text=json.dumps(
            {
                "edits": [
                    {
                        "path": "src/miniparse/date_parser.py",
                        "content": fixed_parser_source(task_dir),
                    }
                ]
            }
        ),
    )
    assert scored["reward"] == 1.0


def test_verifiers_adapter_loader_has_clear_missing_dependency_error() -> None:
    if verifiers_adapter.vf is not None:
        pytest.skip("Prime Intellect verifiers is installed in this environment")

    with pytest.raises(RuntimeError, match="Prime Intellect `verifiers` is required"):
        verifiers_adapter.load_environment(object())


def test_verifiers_adapter_loads_prime_environment_when_installed(tmp_path: Path) -> None:
    if verifiers_adapter.vf is None:
        pytest.skip("Prime Intellect verifiers is not installed in this environment")

    tasks_root = tmp_path / "generated_tasks"
    task_dir = generate_parser_task(tasks_root)
    del task_dir

    env = verifiers_adapter.load_environment(
        verifiers_adapter.vf.EnvConfig(
            taskset=verifiers_adapter.PatchGymTasksetConfig(
                tasks_dir=str(tasks_root),
                limit=1,
            )
        )
    )

    rows = env.taskset.rows()
    signal_names = {
        signal["name"]
        for signal in getattr(env.harness.runtime, "rollout_signals", [])
    }
    assert rows[0]["task_id"] == "parser.boundary.0042"
    assert "patch_reward" in signal_names
    assert "solved" in signal_names
