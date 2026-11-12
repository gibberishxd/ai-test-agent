"""A local model through Ollama's HTTP API (/api/chat). Free, offline, lower quality.

Ollama accepts OpenAI-style function tools and base64 images on a message. Small models
sometimes answer with a JSON object in plain text instead of a real tool call, so we parse that
too. Cost is always 0.
"""

import base64
import json
import re
from typing import Any

import httpx

from worker.llm.base import (
    Decision,
    LLMClient,
    ModelTimeout,
    TextResult,
    ToolCall,
    ToolSpec,
    Usage,
)

TIMEOUT_S = 300  # local models on a laptop can be slow, especially the first (loading) call
CONTEXT_TOKENS = 16384  # Ollama's default context is small; observations need more room


def parse_text_tool_call(text: str, tool_names: set[str]) -> ToolCall | None:
    """Find {"name": ..., "arguments": {...}} in plain text (a model that didn't use tools)."""
    for match in re.finditer(r"\{.*\}", text, flags=re.DOTALL):
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("name") in tool_names:
            args = data.get("arguments") or data.get("parameters") or {}
            return ToolCall(name=data["name"], args=args if isinstance(args, dict) else {})
    return None


class OllamaClient(LLMClient):
    provider = "ollama"

    def __init__(self, base_url: str, model: str, http: httpx.Client | None = None):
        # Ollama serves one model for everything; "cheap" and "agent" are the same model.
        self.agent_model = model
        self.cheap_model = model
        self._url = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=TIMEOUT_S)

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
        data = self._chat(system, observation, image, tools=tool_defs)
        message = data.get("message", {})
        text = message.get("content", "") or ""
        call = None
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function", {})
            args = function.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args) if args.strip() else {}
            call = ToolCall(name=function.get("name", ""), args=args)
            break
        if call is None:
            call = parse_text_tool_call(text, {t.name for t in tools})
        return Decision(tool_call=call, text=text, usage=self._usage(data))

    def review_screenshot(self, prompt: str, image: bytes, system: str | None = None) -> TextResult:
        data = self._chat(system, prompt, image)
        return TextResult(text=data.get("message", {}).get("content", ""), usage=self._usage(data))

    def complete(self, prompt: str, system: str | None = None, cheap: bool = True) -> TextResult:
        data = self._chat(system, prompt, None)
        return TextResult(text=data.get("message", {}).get("content", ""), usage=self._usage(data))

    def _chat(
        self, system: str | None, text: str, image: bytes | None, tools: list | None = None
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        user: dict[str, Any] = {"role": "user", "content": text}
        if image:
            user["images"] = [base64.standard_b64encode(image).decode("ascii")]
        messages.append(user)
        body: dict[str, Any] = {
            "model": self.agent_model,
            "messages": messages,
            "stream": False,
            "think": False,  # faster; reasoning goes in the tool's "reasoning" argument instead
            "options": {"num_ctx": CONTEXT_TOKENS, "temperature": 0.2},
        }
        if tools:
            body["tools"] = tools
        try:
            response = self._http.post(f"{self._url}/api/chat", json=body)
        except httpx.TimeoutException as error:
            raise ModelTimeout(f"no answer within {TIMEOUT_S} s") from error
        response.raise_for_status()
        return response.json()

    def _usage(self, data: dict[str, Any]) -> Usage:
        return Usage(
            model=self.agent_model,
            input_tokens=data.get("prompt_eval_count", 0) or 0,
            output_tokens=data.get("eval_count", 0) or 0,
            cost_usd=0.0,
        )
