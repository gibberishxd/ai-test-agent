"""Swappable model clients. `make_client(settings)` returns the one LLM_PROVIDER selects."""

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
