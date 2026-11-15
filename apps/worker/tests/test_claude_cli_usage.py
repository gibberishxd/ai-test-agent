"""Run 6, L1: claude-cli runs made measurable, from recorded (and two synthetic) CLI answers.

The recorded fixture is one real `claude -p --output-format json` call with Haiku that read a
screenshot (two turns). See tests/fixtures/claude_cli/README.md.
"""

import json
from pathlib import Path

import pytest

from worker.config import Settings
from worker.llm import ToolSpec, Usage, make_client, make_reviewer
from worker.llm.base import UsageLimitReached
from worker.llm.claude_cli import (
    ClaudeCliClient,
    CliFailed,
    is_pinned_model_id,
    limit_reached,
    reset_limit_latch,
    usage_from_cli,
)
from worker.llm.pricing import cost_usd

FIXTURES = Path(__file__).parent / "fixtures" / "claude_cli"
ANSWER = '{"name": "finish", "arguments": {"summary": "Blue"}}'
FINISH = ToolSpec(
    "finish",
    "End.",
    {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
)


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _fresh_latch():
    reset_limit_latch()
    yield
    reset_limit_latch()


class Replay:
    """Answers every call with the same recorded CLI output and counts the calls."""

    def __init__(self, data: dict | str):
        self.out = data if isinstance(data, str) else json.dumps(data)
        self.calls: list[list[str]] = []

    def __call__(self, command, stdin, cwd):
        self.calls.append(command)
        return self.out


# --- tokens, model and the API-equivalent cost ------------------------------------------------


def test_all_four_token_types_and_the_reported_model_are_read():
    usage = usage_from_cli(fixture("haiku_screenshot.json"), requested="claude-haiku-5-5")
    assert usage.model == "claude-haiku-5-5"  # modelUsage's canonicalModel
    assert (usage.input_tokens, usage.output_tokens) == (4, 210)
    assert (usage.cache_read_tokens, usage.cache_write_tokens) == (12726, 12958)
    assert usage.cache_write_1h_tokens == 12958


def test_charged_cost_stays_zero_and_the_estimate_matches_the_cli_list_price():
    data = fixture("haiku_screenshot.json")
    usage = usage_from_cli(data, requested="claude-haiku-5-5")
    assert usage.cost_usd == 0.0  # the Pro plan: nothing is charged per call
    # Our price table gives the same number the CLI computes at list price.
    assert usage.estimated_cost_usd == pytest.approx(data["total_cost_usd"], rel=1e-6)
    assert usage.api_cost_usd == usage.estimated_cost_usd


def test_one_hour_cache_writes_cost_twice_the_input_price():
    five_min = Usage(model="claude-sonnet-5-5", cache_write_tokens=1_000_000)
    one_hour = Usage(
        model="claude-sonnet-5-5", cache_write_tokens=1_000_000, cache_write_1h_tokens=1_000_000
    )
    assert cost_usd("claude-sonnet-5-5", five_min) == pytest.approx(2.50)
    assert cost_usd("claude-sonnet-5-5", one_hour) == pytest.approx(4.00)


def test_an_answer_without_model_usage_falls_back_to_the_requested_model():
    data = {"result": ANSWER, "usage": {"input_tokens": 900, "output_tokens": 30}}
    usage = usage_from_cli(data, requested="claude-sonnet-5-5")
    assert usage.model == "claude-sonnet-5-5"
    assert usage.estimated_cost_usd == pytest.approx((900 * 2.00 + 30 * 10.00) / 1e6)


def test_several_models_in_one_answer_are_each_priced_at_their_own_rate():
    data = {
        "result": ANSWER,
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "modelUsage": {
            "claude-sonnet-5-5": {"inputTokens": 1000, "outputTokens": 100},
            "claude-haiku-5-5": {"inputTokens": 1000, "outputTokens": 100},
        },
    }
    usage = usage_from_cli(data, requested="claude-sonnet-5-5")
    assert usage.model == "claude-sonnet-5-5+claude-haiku-5-5"
    assert (usage.input_tokens, usage.output_tokens) == (2000, 200)
    sonnet = (1000 * 2.00 + 100 * 10.00) / 1e6
    haiku = (1000 * 0.10 + 100 * 0.50) / 1e6
    assert usage.estimated_cost_usd == pytest.approx(sonnet + haiku)


def test_decide_records_the_reported_model_and_the_estimate():
    cli = Replay(fixture("haiku_screenshot.json"))
    decision = ClaudeCliClient(agent_model="claude-haiku-5-5", run=cli).decide("s", "o", [FINISH])
    assert len(cli.calls) == 1
    assert decision.usage.model == "claude-haiku-5-5"
    assert decision.usage.cache_read_tokens == 12726
    assert decision.usage.estimated_cost_usd > 0 and decision.usage.cost_usd == 0


# --- pinned model IDs -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "pinned"),
    [
        ("claude-sonnet-5-5", True),
        ("claude-haiku-5-5", True),
        ("claude-opus-5-5", True),
        ("claude-sonnet-4-5-20250929", True),
        ("sonnet", False),
        ("opus", False),
        ("haiku", False),
        ("", False),
        ("claude-sonnet", False),
    ],
)
def test_a_pinned_model_id_is_a_full_name_not_an_alias(model, pinned):
    assert is_pinned_model_id(model) is pinned


def test_the_cli_client_takes_its_models_from_the_settings(monkeypatch):
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    settings = Settings(
        _env_file=None,
        llm_provider="claude-cli",
        dev_mode=True,
        claude_cli_model="claude-opus-5-5",
        claude_cli_cheap_model="claude-sonnet-5-5",
    )
    client = make_client(settings)
    assert (client.agent_model, client.cheap_model) == ("claude-opus-5-5", "claude-sonnet-5-5")


def test_the_cli_defaults_are_pinned_ids_not_aliases():
    settings = Settings(_env_file=None)
    assert is_pinned_model_id(settings.claude_cli_model)
    assert is_pinned_model_id(settings.claude_cli_cheap_model)


def test_a_cli_reviewer_uses_the_reviewer_model(monkeypatch):
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    settings = Settings(
        _env_file=None,
        llm_provider="ollama",
        dev_mode=True,
        reviewer_provider="claude-cli",
        reviewer_model="claude-opus-5-5",
    )
    reviewer = make_reviewer(settings)
    assert reviewer.provider == "claude-cli" and reviewer.agent_model == "claude-opus-5-5"


# --- a usage limit stops everything ------------------------------------------------------------


def test_a_usage_limit_answer_raises():
    cli = Replay(fixture("usage_limit.json"))
    with pytest.raises(UsageLimitReached, match="usage limit"):
        ClaudeCliClient(run=cli).complete("hi")


def test_after_a_usage_limit_no_client_calls_the_cli_again():
    first = Replay(fixture("usage_limit.json"))
    with pytest.raises(UsageLimitReached):
        ClaudeCliClient(run=first).complete("hi")
    other = Replay(fixture("haiku_screenshot.json"))  # another client, e.g. the reviewer
    with pytest.raises(UsageLimitReached):
        ClaudeCliClient(run=other).decide("s", "o", [FINISH])
    assert other.calls == []  # refused before the CLI ran
    assert limit_reached()


def test_a_call_paid_from_usage_credits_stops_like_a_limit():
    cli = Replay(fixture("fallback_credit.json"))
    with pytest.raises(UsageLimitReached, match="credit"):
        ClaudeCliClient(run=cli).complete("hi")
    assert limit_reached()


def test_a_failed_cli_that_mentions_the_limit_stops_too():
    def run(command, stdin, cwd):
        raise CliFailed(1, "Error: You've hit your usage limit · resets 5pm")

    with pytest.raises(UsageLimitReached):
        ClaudeCliClient(run=run).complete("hi")
    assert limit_reached()


def test_another_cli_error_is_an_ordinary_failure():
    data = {"type": "result", "is_error": True, "result": "API Error: 500 overloaded"}
    with pytest.raises(RuntimeError, match="overloaded") as caught:
        ClaudeCliClient(run=Replay(data)).complete("hi")
    assert not isinstance(caught.value, UsageLimitReached)
    assert not limit_reached()
