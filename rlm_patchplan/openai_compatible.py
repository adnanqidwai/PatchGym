from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_OPENAI_COMPATIBLE_MODEL = "openai/gpt-4o-mini"


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    model_name: str
    api_key: str | None
    api_base: str | None

    def to_dspy_lm_kwargs(self, *, max_tokens: int, temperature: float) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout": 180.0,
        }
        if self.api_key is not None:
            kwargs["api_key"] = self.api_key
        if self.api_base is not None:
            kwargs["api_base"] = self.api_base
        return kwargs


def resolve_openai_compatible_config(
    model_name: str | None = None,
    *,
    api_key: str | None = None,
    api_base: str | None = None,
) -> OpenAICompatibleConfig:
    model = model_name or DEFAULT_OPENAI_COMPATIBLE_MODEL
    key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
    base_url = api_base if api_base is not None else os.environ.get("OPENAI_BASE_URL")
    return OpenAICompatibleConfig(model_name=model, api_key=key, api_base=base_url)
