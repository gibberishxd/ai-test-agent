import json
from types import SimpleNamespace

import httpx
import pytest

from worker.config import Settings
from worker.llm import ConfigError, FakeClient, ToolCall, ToolSpec, Usage, make_client
from worker.llm.claude import ClaudeClient, tool_definitions
from worker.llm.ollama import OllamaClient, parse_text_tool_call
from worker.llm.pricing import FALLBACK, cost_usd

CLICK = ToolSpec(
    name="click",
    description="Click an element",
    parameters={
        "type": "object",
        "properties": {"element_id": {"type": "integer"}},
        "required": ["element_id"],
    },
)


# --- FakeClient --------------------------------------------------------------------------------


def test_fake_returns_scripted_calls_then_finishes():
    fake = FakeClient(decisions=[ToolCall("click", {"element_id": 3})])
    assert fake.decide("sys", "obs", [CLICK]).tool_call == ToolCall("click", {"element_id": 3})
    assert fake.decide("sys", "obs", [CLICK]).tool_call.name == "finish"
    assert [c["method"] for c in fake.calls] == ["decide", "decide"]


def test_fake_texts_and_default():
    fake = FakeClient(texts=["first"], default_text="later")
    assert fake.complete("a").text == "first"
    assert fake.complete("b").text == "later"


# --- Pricing -----------------------------------------------------------------------------------


def test_sonnet_cost():
    usage = Usage(model="claude-sonnet-5-5", input_tokens=1_000_000, output_tokens=100_000)
    assert cost_usd("claude-sonnet-5-5", usage) == pytest.approx(2.00 + 1.00)


def test_cache_reads_are_cheap():
    usage = Usage(model="claude-sonnet-5-5", cache_read_tokens=1_000_000)
    assert cost_usd("claude-sonnet-5-5", usage) == pytest.approx(0.20)


def test_unknown_model_is_charged_the_highest_price():
    usage = Usage(model="mystery", output_tokens=1_000_000)
    assert cost_usd("mystery", usage) == pytest.approx(FALLBACK.output)


# --- ClaudeClient (with a stand-in SDK client, no network) -------------------------------------


class StubMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def claude_response(content, stop_reason="tool_use"):
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=200,
        cache_read_input_tokens=3000,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(
        content=content, model="claude-sonnet-5-5", usage=usage, stop_reason=stop_reason
    )


def stub_claude(response):
    messages = StubMessages(response)
    client = ClaudeClient(
        "key", "claude-sonnet-5-5", "claude-haiku-5-5", SimpleNamespace(messages=messages)
    )
    return client, messages


def test_claude_decide_parses_the_tool_call_and_cost():
    tool_use = SimpleNamespace(type="tool_use", name="click", input={"element_id": 7})
    client, messages = stub_claude(claude_response([tool_use]))

    decision = client.decide("system prompt", "observation", [CLICK], image=b"\x89PNG")

    assert decision.tool_call == ToolCall("click", {"element_id": 7})
    expected = (1000 * 2.00 + 200 * 10.00 + 3000 * 0.20) / 1_000_000
    assert decision.usage.cost_usd == pytest.approx(expected)
    sent = messages.kwargs
    assert sent["tool_choice"]["type"] == "auto"  # forced tool use is rejected by Sonnet 5.5
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert sent["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert sent["messages"][0]["content"][0]["type"] == "image"


def test_claude_decide_without_tool_call():
    text = SimpleNamespace(type="text", text="I'm not sure")
    client, _ = stub_claude(claude_response([text], stop_reason="end_turn"))
    decision = client.decide("s", "o", [CLICK])
    assert decision.tool_call is None
    assert decision.text == "I'm not sure"


def test_tool_definitions_are_strict():
    [definition] = tool_definitions([CLICK])
    assert definition["strict"] is True
    assert definition["input_schema"]["additionalProperties"] is False


# --- OllamaClient (with a mocked HTTP transport) -----------------------------------------------


def ollama_with(reply: dict) -> tuple[OllamaClient, list]:
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=reply)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaClient("http://ollama.test", "qwen3-vl:8b", http=http), sent


def test_ollama_decide_reads_tool_calls():
    reply = {
        "message": {
            "content": "",
            "tool_calls": [{"function": {"name": "click", "arguments": {"element_id": 2}}}],
        },
        "prompt_eval_count": 500,
        "eval_count": 20,
    }
    client, sent = ollama_with(reply)
    decision = client.decide("sys", "obs", [CLICK], image=b"png")
    assert decision.tool_call == ToolCall("click", {"element_id": 2})
    assert decision.usage.cost_usd == 0
    assert decision.usage.input_tokens == 500
    assert sent[0]["messages"][1]["images"]  # the screenshot went along


def test_ollama_falls_back_to_json_in_text():
    reply = {"message": {"content": 'Sure: {"name": "click", "arguments": {"element_id": 4}}'}}
    client, _ = ollama_with(reply)
    assert client.decide("s", "o", [CLICK]).tool_call == ToolCall("click", {"element_id": 4})


def test_parse_text_tool_call_ignores_unknown_tools():
    assert parse_text_tool_call('{"name": "rm_rf", "arguments": {}}', {"click"}) is None


# --- make_client -------------------------------------------------------------------------------


def test_make_client_defaults_to_fake_without_key():
    settings = Settings(_env_file=None, llm_provider="", anthropic_api_key="")
    assert make_client(settings).provider == "fake"


def test_make_client_claude_without_key_is_an_error():
    settings = Settings(_env_file=None, llm_provider="claude", anthropic_api_key="")
    with pytest.raises(ConfigError):
        make_client(settings)


def test_make_client_ollama():
    settings = Settings(_env_file=None, llm_provider="ollama")
    assert make_client(settings).provider == "ollama"
