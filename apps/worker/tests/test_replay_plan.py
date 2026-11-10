"""Which steps replay repeats, and from where. Pure logic: no browser, no database."""

from types import SimpleNamespace

from worker.execute import replay_plans

TARGET = "http://shop.test/"


def step(action, page="http://shop.test/", blocked=False, **args):
    """A recorded step: `page` is where it happened, `args` what the agent passed."""
    return SimpleNamespace(action=action, url=page, blocked=blocked, args=args)


def agent_bug(reported_at, replay_from=10):
    return SimpleNamespace(
        evidence={"reported_at": reported_at, "replay_from": replay_from},
        step_indexes=[],
        page_url="http://shop.test/cart",
    )


def plan_actions(plan):
    start, steps = plan
    return start, [s.action for s in steps]


def test_without_a_navigation_replay_starts_at_the_target():
    steps = {10: step("click", element={}), 11: step("type", text="x", element={})}
    assert [plan_actions(p) for p in replay_plans(agent_bug(12), steps, TARGET)] == [
        (TARGET, ["click", "type"])
    ]


def test_replay_first_tries_from_the_last_navigation_before_the_bug():
    # Placing an order at step 11 must not be repeated if the bug only needs steps 13-14.
    steps = {
        10: step("set_viewport", size="mobile"),
        11: step("click", element={"name": "Place order"}),
        # Relative: resolved against the page it was typed on.
        12: step("navigate", page="http://shop.test/checkout", url="/profile"),
        13: step("click", element={}),
        14: step("scroll", direction="down"),
    }
    plans = [plan_actions(p) for p in replay_plans(agent_bug(15), steps, TARGET)]
    assert plans == [
        # The viewport survives a navigation, so it is set again first.
        ("http://shop.test/profile", ["set_viewport", "click", "scroll"]),
        (TARGET, ["set_viewport", "click", "navigate", "click", "scroll"]),
    ]


def test_blocked_steps_are_never_repeated_and_never_a_starting_point():
    steps = {
        10: step("navigate", blocked=True, url="https://elsewhere.test/"),
        11: step("click", element={}),
        12: step("click", blocked=True, element={}),
    }
    assert [plan_actions(p) for p in replay_plans(agent_bug(13), steps, TARGET)] == [
        (TARGET, ["click"])
    ]


def test_a_screenshot_finding_is_checked_on_its_own_page():
    bug = SimpleNamespace(evidence={}, step_indexes=[], page_url="http://shop.test/p/6")
    assert replay_plans(bug, {}, TARGET) == [("http://shop.test/p/6", [])]
