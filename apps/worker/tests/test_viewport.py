"""A run's own viewport ("390x844"): the screen the crawl, the agent and replay start on."""

from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from worker.agent.loop import AgentConfig, AgentRun
from worker.agent.policy import Budget
from worker.browser import VIEWPORTS, parse_viewport, viewport_label, viewport_size
from worker.execute import replay_viewport
from worker.llm import FakeClient, ToolCall
from worker.safety.network import NetworkGuard
from worker.verify import verify_bug

# --- parsing ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "size"),
    [
        ("390x844", {"width": 390, "height": 844}),
        ("768x1024", {"width": 768, "height": 1024}),
        ("1440x900", {"width": 1440, "height": 900}),
        (" 1440X900 ", {"width": 1440, "height": 900}),
    ],
)
def test_parses_width_by_height(text, size):
    assert parse_viewport(text) == size


@pytest.mark.parametrize("text", ["", "390", "390x", "x844", "abcxdef", "390x844x2", "0x844"])
def test_rejects_what_is_not_a_size(text):
    with pytest.raises(ValueError):
        parse_viewport(text)


@pytest.mark.parametrize("text", ["100x844", "390x100", "5000x900", "1440x5000"])
def test_rejects_sizes_no_screen_has(text):
    with pytest.raises(ValueError):
        parse_viewport(text)


def test_named_viewports_keep_their_sizes():
    assert viewport_size("desktop") == VIEWPORTS["desktop"]
    assert viewport_size("mobile") == VIEWPORTS["mobile"]
    assert viewport_size("768x1024") == {"width": 768, "height": 1024}


def test_labels_name_the_size():
    assert viewport_label("desktop") == "desktop (1280×800)"
    assert viewport_label("768x1024") == "768×1024"


# --- the agent starts on the run's viewport -------------------------------------------------------


def make_agent(context, site_url, decisions, viewport=None):
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )
    budget = Budget(max_steps=10, max_seconds=60, max_cost_usd=1.0)
    extra = {"viewport": viewport} if viewport else {}
    config = AgentConfig(
        target_url=f"{site_url}/counter.html", mode="interactive", budget=budget, **extra
    )
    page = context.new_page()
    return AgentRun(page, FakeClient(decisions=decisions), guard, config), page


def call(name, **args):
    return ToolCall(name, {"reasoning": "test", **args})


def test_agent_starts_on_the_runs_viewport(context, site_url):
    run, page = make_agent(context, site_url, [call("finish", summary="")], viewport="390x844")
    assert page.viewport_size == {"width": 390, "height": 844}
    result = run.run()
    assert result.steps[0].viewport == {"width": 390, "height": 844}


def test_agent_without_a_viewport_starts_on_desktop(context, site_url):
    run, page = make_agent(context, site_url, [call("finish", summary="")])
    run.run()
    assert page.viewport_size == VIEWPORTS["desktop"]


def test_agent_can_still_switch_to_mobile_and_desktop(context, site_url):
    sizes = []
    run, page = make_agent(
        context,
        site_url,
        [
            call("set_viewport", size="mobile"),
            call("set_viewport", size="desktop"),
            call("finish", summary=""),
        ],
        viewport="768x1024",
    )
    run.on_step = lambda step: sizes.append(page.viewport_size)
    run.run()
    assert sizes[:2] == [VIEWPORTS["mobile"], VIEWPORTS["desktop"]]


# --- replay checks a report on the screen it was seen on -----------------------------------------


def test_replay_uses_the_runs_viewport_by_default():
    run = SimpleNamespace(viewport="768x1024")
    assert replay_viewport(SimpleNamespace(evidence={}), run) == "768x1024"
    assert replay_viewport(SimpleNamespace(evidence=None), run) == "768x1024"


def test_replay_prefers_the_viewport_the_report_names():
    run = SimpleNamespace(viewport="768x1024")
    assert replay_viewport(SimpleNamespace(evidence={"viewport": "mobile"}), run) == "mobile"


def test_replay_of_a_run_without_a_viewport_is_on_desktop():
    run = SimpleNamespace(viewport=None)
    assert replay_viewport(SimpleNamespace(evidence={}), run) == "desktop"


def test_verification_looks_at_the_page_at_a_custom_size(context, site_url):
    llm = FakeClient(texts=['{"reproduced": true, "reason": "clipped"}'])
    url = f"{site_url}/counter.html"
    verify_bug(context, llm, url, [], "Title clipped", None, None, "768x1024")
    image = llm.calls[0]["image"]
    assert int.from_bytes(image[16:20], "big") == 768  # the PNG's width
    assert "768×1024" in llm.calls[0]["prompt"]


# --- the crawl's contexts open at the run's viewport ---------------------------------------------


def test_guarded_browser_opens_contexts_at_the_given_viewport(site_url, browser):
    from worker.config import Settings
    from worker.scan import guarded_browser

    settings = Settings(_env_file=None, dev_mode=True, demo_url=f"{site_url}/")
    size = {"width": 390, "height": 844}
    with guarded_browser(settings, f"{site_url}/", browser, viewport=size) as (new_context, _):
        context = new_context()
        try:
            assert context.new_page().viewport_size == size
        finally:
            context.close()
