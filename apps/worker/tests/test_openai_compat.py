"""OpenAICompatClient against recorded-style responses (OpenAI, Gemini, local): no network."""

import base64
import json
from pathlib import Path

import httpx
import pytest

from worker.llm import ToolCall, ToolSpec
from worker.llm.openai_compat import OpenAICompatClient

FIXTURES = Path(__file__).parent / "fixtures" / "openai"
CLICK = ToolSpec(
    "click", "Click.", {"type": "object", "properties": {"element_id": {"type": "integer"}}}
)
TYPE = ToolSpec("type", "Type.", {"type": "object", "properties": {"text": {"type": "string"}}})
SCROLL = ToolSpec("scroll", "Scroll.", {"type": "object", "properties": {}})


def recorded(name: str, sent: list):
    body = json.loads((FIXTURES / name).read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def client(fixture: str, sent: list, **fields) -> OpenAICompatClient:
    options = {"base_url": "https://api.example.test/v1/", "model": "gpt-5-mini", **fields}
    return OpenAICompatClient(**options, http=recorded(fixture, sent))


def test_decide_sends_an_openai_style_request_and_reads_the_tool_call():
    sent = []
    llm = client("tool_call.json", sent, api_key="sk-test-123", input_price=0.25, output_price=2.0)
    decision = llm.decide("system prompt", "observation", [CLICK], image=b"\x89PNG-bytes")

    assert decision.tool_call == ToolCall("click", {"element_id": 7, "reasoning": "open the cart"})
    assert decision.usage.input_tokens == 1200 and decision.usage.output_tokens == 40
    assert decision.usage.cost_usd == pytest.approx((1200 * 0.25 + 40 * 2.0) / 1e6)

    request = sent[0]
    assert str(request.url) == "https://api.example.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test-123"
    body = json.loads(request.content)
    assert body["model"] == "gpt-5-mini"
    assert body["messages"][0] == {"role": "system", "content": "system prompt"}
    image, text = body["messages"][1]["content"]
    png = base64.b64encode(b"\x89PNG-bytes").decode()
    assert image == {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png}"}}
    assert text == {"type": "text", "text": "observation"}
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["function"]["name"] == "click"
    assert body["tool_choice"] == "auto"


def test_reads_geminis_openai_endpoint_the_same_way():
    llm = client("gemini_tool_call.json", [], model="gemini-3-flash")
    decision = llm.decide("s", "o", [TYPE])
    assert decision.tool_call == ToolCall(
        "type", {"element_id": 3, "text": "ada@example", "reasoning": "invalid email"}
    )


def test_a_local_server_without_a_key_sends_no_authorization():
    sent = []
    llm = client("tool_call.json", sent, base_url="http://localhost:1234/v1")
    llm.decide("s", "o", [CLICK])
    assert "authorization" not in sent[0].headers
    assert llm.provider == "openai-compat"


def test_a_tool_call_written_as_text_is_still_understood():
    decision = client("text_tool_call.json", []).decide("s", "o", [SCROLL])
    assert decision.tool_call == ToolCall("scroll", {"direction": "down", "reasoning": "see more"})


def test_complete_uses_the_cheap_model_and_returns_text():
    sent = []
    llm = client("text_answer.json", sent, cheap_model="gpt-5-nano")
    result = llm.complete("prompt", system="judge")
    assert result.text == '{"match": 5, "reason": "same total"}'
    assert json.loads(sent[0].content)["model"] == "gpt-5-nano"
    assert "tools" not in json.loads(sent[0].content)


def test_review_screenshot_sends_the_image():
    sent = []
    client("text_answer.json", sent).review_screenshot("look", b"png", system="review")
    content = json.loads(sent[0].content)["messages"][1]["content"]
    assert content[0]["type"] == "image_url"


def test_an_http_error_names_the_status_but_never_the_key():
    def refuse(request):
        return httpx.Response(401, json={"error": {"message": "Incorrect API key sk-test-123"}})

    llm = OpenAICompatClient(
        base_url="https://api.example.test/v1",
        model="m",
        api_key="sk-test-123",
        http=httpx.Client(transport=httpx.MockTransport(refuse)),
    )
    with pytest.raises(RuntimeError) as error:
        llm.complete("p")
    assert "401" in str(error.value)
    assert "sk-test-123" not in str(error.value)


def test_the_key_never_appears_in_the_clients_repr():
    llm = OpenAICompatClient(base_url="https://x.test/v1", model="m", api_key="sk-test-123")
    assert "sk-test-123" not in repr(llm) and "sk-test-123" not in str(vars(llm))
