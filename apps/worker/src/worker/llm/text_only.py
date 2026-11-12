"""A reviewer that can't see images (run 5, K2): REVIEWER_VISION=false.

Text models (qwen3:14b and many hosted ones) refuse a screenshot; Ollama answers 400. The
reviewer's prompts already carry the evidence as text (page text, what the action changed), so
an image call becomes a text call to the model's main (not cheap) model, saying so.
"""

from worker.llm.base import Decision, LLMClient, TextResult, ToolSpec

NO_SCREENSHOT = "(No screenshot: this reviewer reads text only. Judge from the text above.)"


class TextOnlyClient(LLMClient):
    def __init__(self, inner: LLMClient):
        self.inner = inner
        self.provider = inner.provider
        self.agent_model = inner.agent_model
        self.cheap_model = inner.cheap_model

    def decide(
        self, system: str, observation: str, tools: list[ToolSpec], image: bytes | None = None
    ) -> Decision:
        return self.inner.decide(system, observation, tools, None)

    def review_screenshot(self, prompt: str, image: bytes, system: str | None = None) -> TextResult:
        return self.inner.complete(f"{prompt}\n\n{NO_SCREENSHOT}", system=system, cheap=False)

    def complete(self, prompt: str, system: str | None = None, cheap: bool = True) -> TextResult:
        return self.inner.complete(prompt, system=system, cheap=cheap)
