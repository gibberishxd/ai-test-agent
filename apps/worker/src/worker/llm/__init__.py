"""Swappable model clients. `make_client(settings)` returns the one LLM_PROVIDER selects;
`make_judge(settings, agent)` returns the one that judges benchmark matches."""

from worker.config import Settings
from worker.llm.base import Decision, LLMClient, TextResult, ToolCall, ToolSpec, Usage
from worker.llm.fake import FakeClient

__all__ = [
    "Decision",
    "FakeClient",
    "LLMClient",
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
    return FakeClient()


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
    return make_client(settings.model_copy(update=pinned))
