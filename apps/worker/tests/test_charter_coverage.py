"""Which charter techniques the agent hasn't tried yet, shown in every observation.

Run 3's traces: over 11 runs a 12B model used double_click, reload and the mobile viewport 0
times (Sonnet used each), so whole kinds of bugs were never triggered. The observation now
reminds the model which generic techniques are still untried; nothing in it is site-specific.
"""

from types import SimpleNamespace

from worker.agent.loop import untried_techniques


def step(action, blocked=False, element=None, **args):
    return SimpleNamespace(action=action, args=args, blocked=blocked, element=element)


EMAIL = {"role": "textbox", "name": "Email"}
QUANTITY = {"role": "spinbutton", "name": "Quantity"}


def test_a_fresh_run_has_every_technique_left():
    assert [key for key, _ in untried_techniques([])] == [
        "unusual_value",
        "double_click",
        "reload",
        "mobile",
    ]


def test_using_a_tool_ticks_its_technique_off():
    done = [step("double_click"), step("reload"), step("set_viewport", size="mobile")]
    assert [key for key, _ in untried_techniques(done)] == ["unusual_value"]


def test_a_blocked_step_does_not_count_and_desktop_is_not_mobile():
    done = [step("double_click", blocked=True), step("set_viewport", size="desktop")]
    assert {"double_click", "mobile"} <= {key for key, _ in untried_techniques(done)}


def test_ordinary_values_are_not_unusual():
    ordinary = [
        step("type", element=EMAIL, text="test+abc@example.com"),
        step("type", element=QUANTITY, text="1"),
        step("type", text="Test User"),
    ]
    assert "unusual_value" in {key for key, _ in untried_techniques(ordinary)}


def test_boundary_long_empty_and_malformed_values_are_unusual():
    for value, element in [
        ("0", QUANTITY),
        ("2", QUANTITY),
        ("-1", QUANTITY),
        ("x" * 60, None),
        ("", None),
        ("not-an-email", EMAIL),
        ("<b>&'\"", None),
    ]:
        done = [step("type", element=element, text=value)]
        assert "unusual_value" not in {k for k, _ in untried_techniques(done)}, value


def test_the_reminder_reads_as_one_line_per_technique():
    [(_, text)] = [t for t in untried_techniques([]) if t[0] == "double_click"]
    assert "double_click" in text and "twice" in text
