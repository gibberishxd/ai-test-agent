"""A scripted LLM client for tests: no network, no cost, fully predictable."""

from worker.llm.base import Decision, LLMClient, TextResult, ToolCall, ToolSpec, Usage

FINISH = ToolCall("finish", {"summary": "Fake client: script finished.", "reasoning": ""})


class FakeClient(LLMClient):
    """Returns the scripted tool calls and texts in order, and records every call it gets.

    When the script runs out, `decide` calls `finish` and text methods return `default_text`,
    so a test can never hang waiting for the model.
    """

    provider = "fake"

    def __init__(
        self,
        decisions: list[ToolCall] | None = None,
        texts: list[str] | None = None,
        default_text: str = "OK",
    ):
        self.agent_model = "fake-agent"
        self.cheap_model = "fake-cheap"
        self._decisions = list(decisions or [])
        self._texts = list(texts or [])
        self._default_text = default_text
        self.calls: list[dict] = []

    def _usage(self, model: str, text: str) -> Usage:
        # Rough, deterministic token counts (~4 characters per token) so cost logic is exercised.
        return Usage(model=model, input_tokens=len(text) // 4, output_tokens=10)

    def decide(
        self, system: str, observation: str, tools: list[ToolSpec], image: bytes | None = None
    ) -> Decision:
        self.calls.append(
            {"method": "decide", "observation": observation, "tools": tools, "image": image}
        )
        call = self._decisions.pop(0) if self._decisions else FINISH
        return Decision(tool_call=call, text="", usage=self._usage(self.agent_model, observation))

    def review_screenshot(self, prompt: str, image: bytes, system: str | None = None) -> TextResult:
        self.calls.append({"method": "review_screenshot", "prompt": prompt, "image": image})
        return self._next_text(prompt, self.agent_model)

    def complete(self, prompt: str, system: str | None = None, cheap: bool = True) -> TextResult:
        self.calls.append({"method": "complete", "prompt": prompt, "cheap": cheap})
        return self._next_text(prompt, self.cheap_model if cheap else self.agent_model)

    def _next_text(self, prompt: str, model: str) -> TextResult:
        text = self._texts.pop(0) if self._texts else self._default_text
        return TextResult(text=text, usage=self._usage(model, prompt))
