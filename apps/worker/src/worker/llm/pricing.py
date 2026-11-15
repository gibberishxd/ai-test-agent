"""Claude prices in USD per million tokens, used to compute the cost of every call.

Source: Anthropic's model table (cached 2026-11-03). Cache writes (5-minute TTL) cost 1.25x
the input price, 1-hour writes 2x (Claude Code's own calls use those: run 6, D88); cache reads
~0.1x, except where a model publishes its own read price (Sonnet 5.5: $0.10, Opus 5.5: $0.20).
Update this table when prices change; the benchmark records cost per run, so a change shows up.
"""

from dataclasses import dataclass

from worker.llm.base import Usage


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float  # 5-minute TTL

    @property
    def cache_write_1h(self) -> float:
        return self.input * 2


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read=0.20, cache_write=5.00),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read=0.10, cache_write=2.50),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
}

# Unknown model: charge the most expensive known price, so budgets err on the safe side.
FALLBACK = max(PRICES.values(), key=lambda p: p.output)


def cost_usd(model: str, usage: Usage) -> float:
    price = PRICES.get(model, FALLBACK)
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + (usage.cache_write_tokens - usage.cache_write_1h_tokens) * price.cache_write
        + usage.cache_write_1h_tokens * price.cache_write_1h
    )
    return total / 1_000_000
