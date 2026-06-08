from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Protocol


class OpenAICompatibleClient(Protocol):
    def _generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = 0.0,
        return_token_usage: bool = False,
        verbose: bool = False,
    ) -> Any:
        ...


DEFAULT_OPENAI_COMPATIBLE_MODEL = "gpt-4o-mini"
READABLE_SUFFIXES = {".py", ".toml", ".md", ".txt", ".json"}


def _repo_files(repo_dir: Path) -> list[Path]:
    ignored_dirs = {"__pycache__", ".pytest_cache", ".git"}
    return [
        path
        for path in sorted(repo_dir.rglob("*"))
        if path.is_file()
        and not ignored_dirs.intersection(path.parts)
        and path.suffix in READABLE_SUFFIXES
    ]


def build_openai_compatible_prompt(task_dir: str | Path, repo_dir: str | Path) -> str:
    task_path = Path(task_dir)
    repo_path = Path(repo_dir)
    issue = (task_path / "issue.md").read_text(encoding="utf-8")
    file_sections: list[str] = []

    for file_path in _repo_files(repo_path):
        relative = file_path.relative_to(repo_path).as_posix()
        content = file_path.read_text(encoding="utf-8")
        file_sections.append(f"### {relative}\n```text\n{content}\n```")

    files_text = "\n\n".join(file_sections)
    return f"""\
You are fixing a small generated Python repository.

The hidden tests are unavailable. Do not modify tests or generated metadata.
Return only JSON with this schema:
{{"edits": [{{"path": "relative/path.py", "content": "full replacement file content"}}]}}
The response must be valid JSON. Escape newlines inside file content as \\n.

Issue:
{issue}

Repository files:
{files_text}
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(stripped[start : end + 1])

    raise ValueError("OpenAI-compatible response did not contain a JSON object")


def _is_safe_edit_path(relative_path: str) -> tuple[bool, str | None]:
    normalized = Path(relative_path)
    if normalized.is_absolute() or ".." in normalized.parts:
        return False, "path escapes repository"
    if normalized.parts and normalized.parts[0] == "tests":
        return False, "test edits are not allowed"
    if normalized.name in {"metadata.json", "oracle.json"}:
        return False, "generated metadata edits are not allowed"
    return True, None


def apply_openai_compatible_response(repo_dir: str | Path, response_text: str) -> dict[str, Any]:
    repo_path = Path(repo_dir)
    payload = _extract_json_object(response_text)
    edits = payload.get("edits", [])
    if not isinstance(edits, list):
        raise ValueError("OpenAI-compatible response field `edits` must be a list")

    applied: list[str] = []
    rejected: list[dict[str, str]] = []

    for edit in edits:
        if not isinstance(edit, dict):
            rejected.append({"path": "<unknown>", "reason": "edit must be an object"})
            continue
        relative = edit.get("path")
        content = edit.get("content")
        if not isinstance(relative, str) or not isinstance(content, str):
            rejected.append({"path": str(relative), "reason": "edit requires path and content strings"})
            continue

        safe, reason = _is_safe_edit_path(relative)
        if not safe:
            rejected.append({"path": relative, "reason": reason or "unsafe path"})
            continue

        target = repo_path / relative
        if not target.is_file():
            rejected.append({"path": relative, "reason": "target file does not exist"})
            continue

        target.write_text(content, encoding="utf-8")
        applied.append(relative)

    return {"edits_applied": applied, "rejected_edits": rejected}


class OpenAICompatibleChatClient:
    def __init__(
        self,
        *,
        model_name: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install `openai` to use the OpenAI-compatible agent.") from exc

        self.model_name = model_name
        self.client = OpenAI(
            api_key=api_key if api_key is not None else os.environ.get("OPENAI_API_KEY"),
            base_url=base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL"),
        )

    def _generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = 0.0,
        return_token_usage: bool = False,
        verbose: bool = False,
    ) -> tuple[str | None, str] | tuple[str | None, str, int | None, int | None]:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        if verbose:
            print(content)

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None

        if return_token_usage:
            return None, content, input_tokens, output_tokens
        return None, content


def create_openai_compatible_client(
    model_name: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> OpenAICompatibleClient:
    return OpenAICompatibleChatClient(model_name=model_name, api_key=api_key, base_url=base_url)


def run_openai_compatible_agent(
    task_dir: str | Path,
    repo_dir: str | Path,
    *,
    model_name: str = DEFAULT_OPENAI_COMPATIBLE_MODEL,
    client: OpenAICompatibleClient | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int | None = 4096,
    temperature: float = 0.0,
) -> dict[str, Any]:
    prompt = build_openai_compatible_prompt(task_dir, repo_dir)
    llm = client if client is not None else create_openai_compatible_client(
        model_name,
        api_key=api_key,
        base_url=base_url,
    )
    generated = llm._generate(
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        return_token_usage=True,
    )

    reasoning: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    if isinstance(generated, tuple) and len(generated) == 4:
        reasoning, content, input_tokens, output_tokens = generated
    elif isinstance(generated, tuple) and len(generated) == 2:
        reasoning, content = generated
    else:
        content = str(generated)

    edit_result = apply_openai_compatible_response(repo_dir, str(content))
    return {
        "model": model_name,
        "prompt_chars": len(prompt),
        "response_chars": len(str(content)),
        "reasoning_chars": len(reasoning or ""),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        **edit_result,
    }
