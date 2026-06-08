import json
from pathlib import Path

from patchgym.agents.openai_compatible import build_openai_compatible_prompt
from patchgym.runner import run_task
from test_patchgym_mvp import run_patchgym


class FakeOpenAICompatibleClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def _generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        return_token_usage: bool = False,
        verbose: bool = False,
    ):
        self.prompts.append(prompt)
        if return_token_usage:
            return None, self.response, 11, 17
        return None, self.response


def generate_task(out_dir: Path) -> Path:
    result = run_patchgym(
        "generate",
        "--out",
        str(out_dir),
        "--templates",
        "parser",
        "--n",
        "1",
        "--seed",
        "42",
    )
    assert result.returncode == 0, result.stderr
    return out_dir / "parser.boundary.0042"


def test_openai_prompt_includes_issue_and_public_repo_but_not_hidden_tests(tmp_path: Path) -> None:
    task_dir = generate_task(tmp_path / "generated_tasks")

    prompt = build_openai_compatible_prompt(task_dir, task_dir / "repo")

    assert "# Fix date parsing for empty inputs" in prompt
    assert "src/miniparse/date_parser.py" in prompt
    assert "tests/test_public.py" in prompt
    assert "hidden_tests" not in prompt
    assert "Return only JSON" in prompt


def test_run_openai_agent_applies_json_file_edit_and_solves_task(tmp_path: Path) -> None:
    task_dir = generate_task(tmp_path / "generated_tasks")
    parser_source = (task_dir / "repo" / "src" / "miniparse" / "date_parser.py").read_text()
    fixed_source = parser_source.replace(
        "if value is None:",
        "if value is None or value.strip() == \"\":",
    )
    fake_llm = FakeOpenAICompatibleClient(
        json.dumps(
            {
                "edits": [
                    {
                        "path": "src/miniparse/date_parser.py",
                        "content": fixed_source,
                    }
                ]
            }
        )
    )

    summary = run_task(
        task_dir,
        agent="openai-compatible",
        out_dir=tmp_path / "runs" / "openai",
        model="fake-model",
        openai_client=fake_llm,
    )

    assert fake_llm.prompts
    assert summary["agent"] == "openai-compatible"
    assert summary["agent_result"]["model"] == "fake-model"
    assert summary["agent_result"]["edits_applied"] == ["src/miniparse/date_parser.py"]
    assert summary["agent_result"]["input_tokens"] == 11
    assert summary["agent_result"]["output_tokens"] == 17
    assert summary["verification"]["solved"] is True

    trace_path = tmp_path / "runs" / "openai" / "parser.boundary.0042" / "trace.jsonl"
    events = [json.loads(line)["event"] for line in trace_path.read_text().splitlines()]
    assert "agent_openai_response_received" in events
    assert "agent_openai_edit_applied" in events


def test_openai_agent_rejects_test_file_edits(tmp_path: Path) -> None:
    task_dir = generate_task(tmp_path / "generated_tasks")
    fake_llm = FakeOpenAICompatibleClient(
        json.dumps(
            {
                "edits": [
                    {
                        "path": "tests/test_public.py",
                        "content": "def test_cheat():\n    assert True\n",
                    }
                ]
            }
        )
    )

    summary = run_task(
        task_dir,
        agent="openai-compatible",
        out_dir=tmp_path / "runs" / "openai",
        model="fake-model",
        openai_client=fake_llm,
    )

    assert summary["agent_result"]["edits_applied"] == []
    assert summary["agent_result"]["rejected_edits"] == [
        {"path": "tests/test_public.py", "reason": "test edits are not allowed"}
    ]
    assert summary["verification"]["solved"] is False


def test_openai_agent_records_malformed_response_without_crashing(tmp_path: Path) -> None:
    task_dir = generate_task(tmp_path / "generated_tasks")
    fake_llm = FakeOpenAICompatibleClient("this is not json")

    summary = run_task(
        task_dir,
        agent="openai-compatible",
        out_dir=tmp_path / "runs" / "openai",
        model="fake-model",
        openai_client=fake_llm,
    )

    assert summary["agent_result"]["status"] == "error"
    assert "OpenAI-compatible response did not contain a JSON object" in summary["agent_result"]["error"]
    assert summary["verification"]["public_tests"]["passed"] is True
    assert summary["verification"]["hidden_tests"]["passed"] is False
    assert summary["verification"]["solved"] is False
