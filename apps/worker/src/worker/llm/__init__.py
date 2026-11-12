"""Swappable model clients. `make_client(settings)` returns the one LLM_PROVIDER selects;
`make_judge(settings, agent)` returns the one that judges benchmark matches."""

import json
import os

from worker.config import Settings
from worker.llm.base import (
    Decision,
    LLMClient,
    ModelTimeout,
    TextResult,
    ToolCall,
    ToolSpec,
    Usage,
)
from worker.llm.fake import FakeClient
from worker.llm.text_only import TextOnlyClient

__all__ = [
    "Decision",
    "FakeClient",
    "LLMClient",
    "ModelTimeout",
    "TextOnlyClient",
    "TextResult",
    "ToolCall",
    "ToolSpec",
    "Usage",
    "make_client",
    "make_judge",
]


class ConfigError(Exception):
    pass


def make_client(settings: Settings) -> LLMClient:
    provider = settings.provider()
    if provider == "claude":
        key = settings.anthropic_api_key.get_secret_value()
        if not key:
            raise ConfigError("LLM_PROVIDER=claude needs ANTHROPIC_API_KEY in .env")
        from worker.llm.claude import ClaudeClient

        return ClaudeClient(key, settings.agent_model, settings.cheap_model)
    if provider == "ollama":
        from worker.llm.ollama import OllamaClient

        return OllamaClient(settings.ollama_url, settings.ollama_model)
    if provider == "openai-compat":
        if not settings.openai_compat_base_url or not settings.openai_compat_model:
            raise ConfigError(
                "LLM_PROVIDER=openai-compat needs OPENAI_COMPAT_BASE_URL and OPENAI_COMPAT_MODEL"
            )
        from worker.llm.openai_compat import OpenAICompatClient

        return OpenAICompatClient(
            base_url=settings.openai_compat_base_url,
            model=settings.openai_compat_model,
            api_key=settings.openai_compat_api_key.get_secret_value() or None,
            cheap_model=settings.openai_compat_cheap_model or None,
            input_price=settings.openai_compat_input_price,
            output_price=settings.openai_compat_output_price,
        )
    if provider == "claude-cli":
        _check_local_only(settings)
        from worker.llm.claude_cli import ClaudeCliClient

        return ClaudeCliClient()
    return FakeClient(decisions=_fake_script(settings.fake_script))


def _check_local_only(settings: Settings) -> None:
    """claude-cli uses the owner's own Claude login: never on a server, never in production."""
    if not settings.dev_mode:
        raise ConfigError("LLM_PROVIDER=claude-cli only runs with DEV_MODE=true (local testing)")
    if "production" in (os.environ.get("NODE_ENV", ""), os.environ.get("ENV", "")):
        raise ConfigError("LLM_PROVIDER=claude-cli never runs in production")


def _fake_script(text: str) -> list[ToolCall]:
    """FAKE_SCRIPT as tool calls; each gets a reasoning line like a real model's would."""
    if not text.strip():
        return []
    try:
        return [
            ToolCall(name, {**args, "reasoning": "scripted step"})
            for name, args in json.loads(text)
        ]
    except (ValueError, TypeError) as error:
        message = f"FAKE_SCRIPT must be a JSON list of [name, args] pairs: {error}"
        raise ConfigError(message) from error


def make_judge(settings: Settings, agent: LLMClient) -> LLMClient:
    """The client for benchmark matching: pinned by JUDGE_PROVIDER / JUDGE_MODEL if set.

    A benchmark compares agent models, so the judge must stay the same while the agent
    changes. Matching calls `complete(cheap=True)`, so JUDGE_MODEL becomes the judge client's
    cheap model. With neither setting, the agent's own client judges (the old behaviour).
    """
    if not settings.judge_provider and not settings.judge_model:
        return agent
    pinned = {"llm_provider": settings.judge_provider or settings.provider()}
    if settings.judge_model:
        pinned["cheap_model"] = settings.judge_model
        pinned["ollama_model"] = settings.judge_model
        pinned["openai_compat_cheap_model"] = settings.judge_model
    return make_client(settings.model_copy(update=pinned))


def make_reviewer(settings: Settings) -> LLMClient | None:
    """The reviewer tier's client (REVIEWER_PROVIDER / REVIEWER_MODEL), or None when unset.

    The reviewer only answers `review_screenshot` calls, which use the client's agent model, so
    REVIEWER_MODEL pins that model for whichever provider is chosen.
    """
    if not settings.reviewer_provider and not settings.reviewer_model:
        return None
    pinned: dict = {"llm_provider": settings.reviewer_provider or settings.provider()}
    if settings.reviewer_model:
        model = settings.reviewer_model
        pinned.update(agent_model=model, ollama_model=model, openai_compat_model=model)
    client = make_client(settings.model_copy(update=pinned))
    if settings.reviewer_model:
        client.agent_model = settings.reviewer_model  # claude-cli takes no model setting
    return client if settings.reviewer_vision else TextOnlyClient(client)
