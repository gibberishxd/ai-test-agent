"""The provider-neutral interface every model client implements.

The agent loop, screenshot review and benchmark matching only talk to `LLMClient`, so Claude,
Ollama and the scripted FakeClient are interchangeable (chosen by LLM_PROVIDER).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call. `parameters` is a JSON Schema object."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    """Tokens and cost for one model call. Cost is computed by the client (Ollama: always 0)."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class Decision:
    """The model's choice for one agent step: one tool call, or None if it didn't make one."""

    tool_call: ToolCall | None
    text: str
    usage: Usage


@dataclass
class TextResult:
    text: str
    usage: Usage


class LLMClient(ABC):
    provider: str
    agent_model: str
    cheap_model: str

    @abstractmethod
    def decide(
        self, system: str, observation: str, tools: list[ToolSpec], image: bytes | None = None
    ) -> Decision:
        """Pick exactly one tool to call, given the current observation (and optional PNG)."""

    @abstractmethod
    def review_screenshot(self, prompt: str, image: bytes, system: str | None = None) -> TextResult:
        """Look at a PNG screenshot and answer `prompt` (visual / UX review)."""

    @abstractmethod
    def complete(self, prompt: str, system: str | None = None, cheap: bool = True) -> TextResult:
        """Plain text in, text out: summaries, dedup, judging. `cheap` picks CHEAP_MODEL."""
