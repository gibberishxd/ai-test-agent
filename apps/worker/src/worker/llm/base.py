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
    """Tokens and cost for one model call. Cost is computed by the client (Ollama: always 0).

    `input_tokens` are the uncached input tokens; cache reads and writes are counted apart
    (`cache_write_1h_tokens` is the share of the writes kept for an hour, priced higher).
    `cost_usd` is what the call was charged. `estimated_cost_usd` is what the same call would
    cost on the Claude API at list price (run 6): set by claude-cli, whose calls are charged
    nothing on the Pro plan but still have to be budgeted and compared.
    """

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    cache_write_1h_tokens: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def api_cost_usd(self) -> float:
        """The API-equivalent cost: the charged cost, or the estimate where nothing is charged.
        Budgets use this, so a run on a flat-rate plan still stops when it runs away."""
        return max(self.cost_usd, self.estimated_cost_usd)


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


class ModelTimeout(Exception):
    """The model didn't answer within the client's time limit (a slow local model, usually)."""


class UsageLimitReached(Exception):
    """The provider says the plan's usage limit is reached, or calls are now paid from credits.

    Never retried: a benchmark stops at once and records what finished (run 6 rule)."""


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
