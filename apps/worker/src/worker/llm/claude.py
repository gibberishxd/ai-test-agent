"""Claude via the official Anthropic Python SDK: tool use, vision and prompt caching.

Notes on the current API (Claude Sonnet 5.5):
- Forced tool use (tool_choice "any") is rejected, so we send tool_choice "auto", mark tools
  `strict` (arguments always match the schema) and the system prompt says to always call one
  tool. A reply without a tool call becomes Decision(tool_call=None) for the loop to handle.
- Prompt caching: cache_control on the last tool and on the system prompt caches that whole
  prefix (tools, then system) across steps. Only the observation changes per step.
- Server-side refusal fallback ("default" routing) is enabled on agent calls.
"""

import base64
from typing import Any

import anthropic

from worker.llm.base import Decision, LLMClient, TextResult, ToolCall, ToolSpec, Usage
from worker.llm.pricing import cost_usd

CACHE = {"type": "ephemeral"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _image_block(png: bytes) -> dict[str, Any]:
    data = base64.standard_b64encode(png).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


def tool_definitions(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Our ToolSpecs in Claude's format; the last one carries the cache breakpoint."""
    defs = []
    for tool in tools:
        schema = {"additionalProperties": False, **tool.parameters}
        defs.append(
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": schema,
                "strict": True,
            }
        )
    if defs:
        defs[-1]["cache_control"] = CACHE
    return defs


class ClaudeClient(LLMClient):
    provider = "claude"

    def __init__(self, api_key: str, agent_model: str, cheap_model: str, client: Any = None):
        self.agent_model = agent_model
        self.cheap_model = cheap_model
        # `client` lets tests pass a stand-in; normally we build the real SDK client.
        self._client = client or anthropic.Anthropic(api_key=api_key)

    def decide(
        self, system: str, observation: str, tools: list[ToolSpec], image: bytes | None = None
    ) -> Decision:
        content: list[dict[str, Any]] = [_image_block(image)] if image else []
        content.append({"type": "text", "text": observation})
        response = self._client.messages.create(
            model=self.agent_model,
            max_tokens=4096,
            system=[{"type": "text", "text": system, "cache_control": CACHE}],
            tools=tool_definitions(tools),
            tool_choice={"type": "auto", "disable_parallel_tool_use": True},
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": content}],
            extra_headers={"anthropic-beta": FALLBACK_BETA},
            extra_body={"fallbacks": "default"},
        )
        call = None
        texts = []
        for block in response.content:
            if block.type == "tool_use" and call is None:
                call = ToolCall(name=block.name, args=dict(block.input))
            elif block.type == "text":
                texts.append(block.text)
        if response.stop_reason == "refusal":
            texts.append("[the model declined this request]")
        return Decision(tool_call=call, text="\n".join(texts), usage=self._usage(response))

    def review_screenshot(self, prompt: str, image: bytes, system: str | None = None) -> TextResult:
        content = [_image_block(image), {"type": "text", "text": prompt}]
        return self._text_call(self.agent_model, content, system)

    def complete(self, prompt: str, system: str | None = None, cheap: bool = True) -> TextResult:
        model = self.cheap_model if cheap else self.agent_model
        return self._text_call(model, [{"type": "text", "text": prompt}], system)

    def _text_call(
        self, model: str, content: list[dict[str, Any]], system: str | None
    ) -> TextResult:
        kwargs: dict[str, Any] = {}
        if system:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": CACHE}]
        response = self._client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": content}],
            **kwargs,
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return TextResult(text=text, usage=self._usage(response))

    def _usage(self, response: Any) -> Usage:
        u = response.usage
        usage = Usage(
            model=response.model,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )
        usage.cost_usd = cost_usd(usage.model, usage)
        return usage
