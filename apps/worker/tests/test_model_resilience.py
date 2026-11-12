"""A slow local model gets one second chance with a smaller observation (run 4, J1).

Run 3, R3b: 3 of 7 Gemma runs ended when one Ollama call took over 300 s on a 16 GB Mac. A
long observation is the main thing that makes a call slow, so a timed-out decision is retried
once with a trimmed observation (less page text, fewer elements and steps, no image) before
the run ends.
"""

from urllib.parse import urlsplit

import httpx
import pytest

from worker.agent.loop import AgentConfig, AgentRun
from worker.agent.policy import Budget
from worker.llm import FakeClient, ModelTimeout, ToolCall
from worker.llm.ollama import OllamaClient
from worker.safety.network import NetworkGuard


def test_ollama_turns_a_read_timeout_into_model_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OllamaClient("http://ollama.test", "gemma4:12b", http=http)
    with pytest.raises(ModelTimeout):
        client.decide("system", "observation", [], None)


class SlowOnce(FakeClient):
    """Times out on the first `slow` decisions, then answers from the script."""

    def __init__(self, slow: int, decisions):
        super().__init__(decisions=decisions)
        self.slow = slow

    def decide(self, system, observation, tools, image=None):
        if self.slow:
            self.slow -= 1
            self.calls.append({"method": "decide", "observation": observation, "image": image})
            raise ModelTimeout("timed out after 300 s")
        return super().decide(system, observation, tools, image)


@pytest.fixture
def agent(context, site_url):
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )

    def make(llm):
        config = AgentConfig(
            target_url=f"{site_url}/products.html",
            mode="interactive",
            budget=Budget(max_steps=5, max_seconds=60, max_cost_usd=1.0),
        )
        return AgentRun(context.new_page(), llm, guard, config)

    return make


def test_a_timed_out_decision_is_retried_once_with_a_trimmed_observation(agent):
    llm = SlowOnce(1, [ToolCall("finish", {"reasoning": "t", "summary": "done"})])
    result = agent(llm).run()
    assert result.stop_reason == "finished"
    first, retry = llm.calls[0], llm.calls[1]
    assert len(retry["observation"]) < len(first["observation"])
    assert retry["image"] is None
    assert "shortened" in retry["observation"]


def test_a_second_timeout_ends_the_run_cleanly(agent):
    result = agent(SlowOnce(2, [])).run()
    assert result.stop_reason.startswith("the model call failed: ModelTimeout")
