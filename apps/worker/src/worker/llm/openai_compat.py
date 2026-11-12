"""Any model behind an OpenAI-style chat completions API: one client for many providers.

OpenAI, Gemini's OpenAI endpoint, OpenRouter, Groq, LM Studio, vLLM and Ollama's /v1 all accept
the same request: `POST {base_url}/chat/completions` with `messages`, `tools` (function
schemas) and images as `data:` URLs. This is what lets a team bring their own model.

Only parameters every one of them accepts are sent (no temperature, max_tokens or
parallel_tool_calls: some models reject each of those). Prices are per million tokens and
come from the configuration, since this client can't know what a given endpoint charges.
"""

import base64
import json
from typing import Any

import httpx
from pydantic import SecretStr

from worker.llm.base import Decision, LLMClient, TextResult, ToolCall, ToolSpec, Usage
from worker.llm.ollama import parse_text_tool_call
from worker.safety.secrets import redact

TIMEOUT_S = 120


class OpenAICompatClient(LLMClient):
    provider = "openai-compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        cheap_model: str | None = None,
        input_price: float = 0.0,
        output_price: float = 0.0,
        http: httpx.Client | None = None,
    ):
        self.agent_model = model
        self.cheap_model = cheap_model or model
        self._url = base_url.rstrip("/") + "/chat/completions"
        # SecretStr: the key never shows in repr(), logs or error messages.
        self._key = SecretStr(api_key or "")
        self._prices = (input_price, output_price)
        self._http = http or httpx.Client(timeout=TIMEOUT_S)

    def __repr__(self) -> str:
        return f"OpenAICompatClient(url={self._url!r}, model={self.agent_model!r})"

    def decide(
        self, system: str, observation: str, tools: list[ToolSpec], image: bytes | None = None
    ) -> Decision:
        tool_defs = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]
        data = self._chat(
            self.agent_model, system, observation, image, tools=tool_defs, tool_choice="auto"
        )
        message = (data.get("choices") or [{}])[0].get("message") or {}
        text = message.get("content") or ""
        call = None
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            call = ToolCall(function.get("name", ""), _arguments(function.get("arguments")))
            break
        if call is None:  # some models write the call as JSON in their text
            call = parse_text_tool_call(text, {t.name for t in tools})
        return Decision(tool_call=call, text=text, usage=self._usage(data, self.agent_model))

    def review_screenshot(self, prompt: str, image: bytes, system: str | None = None) -> TextResult:
        data = self._chat(self.agent_model, system, prompt, image)
        return TextResult(_text(data), self._usage(data, self.agent_model))

    def complete(self, prompt: str, system: str | None = None, cheap: bool = True) -> TextResult:
        model = self.cheap_model if cheap else self.agent_model
        data = self._chat(model, system, prompt, None)
        return TextResult(_text(data), self._usage(data, model))

    def _chat(
        self, model: str, system: str | None, text: str, image: bytes | None, **extra: Any
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        if image:
            data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        content.append({"type": "text", "text": text})
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": content})
        headers = {"Content-Type": "application/json"}
        key = self._key.get_secret_value()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = {"model": model, "messages": messages, **extra}
        response = self._http.post(self._url, json=body, headers=headers)
        if response.status_code >= 400:
            detail = redact(response.text[:300], known_secrets=(key,))
            raise RuntimeError(f"model endpoint answered HTTP {response.status_code}: {detail}")
        return response.json()

    def _usage(self, data: dict[str, Any], model: str) -> Usage:
        usage = data.get("usage") or {}
        tokens_in = usage.get("prompt_tokens", 0) or 0
        tokens_out = usage.get("completion_tokens", 0) or 0
        input_price, output_price = self._prices
        return Usage(
            model=model,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cost_usd=(tokens_in * input_price + tokens_out * output_price) / 1_000_000,
        )


def _arguments(raw: Any) -> dict:
    """Tool arguments arrive as a JSON string (OpenAI) or, from some servers, as an object."""
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _text(data: dict[str, Any]) -> str:
    message = (data.get("choices") or [{}])[0].get("message") or {}
    return message.get("content") or ""
