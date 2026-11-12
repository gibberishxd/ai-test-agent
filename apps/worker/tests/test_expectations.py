"""Expected vs. actual after each state-changing action (run 4, J1).

Run 3's traces: a 12B model reached 7 of 12 judgement-bug states and reported 1. It acted,
glanced at the result line and moved on. Now the model writes one line of what it expects before
a state-changing action, the worker compares that with what actually changed (cheaply, without
another model call), and a mismatch becomes a candidate the model must report or dismiss with a
reason. Nothing here knows about any particular site.
"""

from urllib.parse import urlsplit

import pytest

from worker.agent.expect import (
    EXPECT_ACTIONS,
    Effect,
    expected_values,
    mismatches,
)
from worker.agent.loop import AgentConfig, AgentRun
from worker.agent.policy import Budget
from worker.agent.tools import TOOLS
from worker.llm import FakeClient, ToolCall
from worker.safety.network import NetworkGuard

# --- which actions need an expectation --------------------------------------------------------


def test_state_changing_actions_need_an_expectation_and_the_others_dont():
    assert {"click", "double_click", "select", "reload", "set_viewport"} <= EXPECT_ACTIONS
    assert not {"scroll", "navigate", "type", "note", "go_back", "finish"} & EXPECT_ACTIONS
    by_name = {tool.name: tool for tool in TOOLS}
    for name in EXPECT_ACTIONS:
        assert "expect" in by_name[name].parameters["properties"], name
    assert "expect" not in by_name["scroll"].parameters["properties"]


def test_dismiss_tool_takes_a_step_and_a_reason():
    dismiss = next(tool for tool in TOOLS if tool.name == "dismiss")
    assert {"step_id", "reason"} <= set(dismiss.parameters["properties"])


# --- what the model predicted ------------------------------------------------------------------


def test_expected_values_are_amounts_numbers_quoted_text_and_paths():
    values = expected_values("Total becomes $36.00 for 3 mugs, 'Saved' message, then /cart")
    assert values == ["$36.00", "3", "Saved", "/cart"]


def test_values_after_a_negation_are_not_expected_and_dates_are_skipped():
    assert expected_values("total should be $24, not $12") == ["$24"]
    assert expected_values("booking from 2027-02-01 to 2027-02-04 shows 3 nights") == ["3"]
    assert expected_values("the page updates") == []


# --- comparing with what happened --------------------------------------------------------------


def effect(**fields):
    return Effect(**{"url_before": "/a", "url_after": "/a", **fields})


def test_a_predicted_amount_missing_from_the_page_is_a_mismatch():
    found = mismatches("Total: $36.00", effect(added=["Total: $12.00"]), "Total: $12.00", {})
    assert found == ["$36.00 is not on the page"]


def test_amounts_match_whatever_their_formatting():
    page = "Total: $1,236.00"
    assert mismatches("total $1236", effect(added=[page]), page, {}) == []


def test_quoted_text_is_found_case_insensitively_in_text_or_field_values():
    assert (
        mismatches("'profile saved'", effect(added=["Profile saved."]), "Profile saved.", {}) == []
    )
    fields = {"Display name": "Test User"}
    changed = effect(fields=["Display name: Demo → Test User"])
    assert mismatches("'Test User' in the name field", changed, "", fields) == []


def test_expecting_a_change_when_nothing_changed_is_a_mismatch():
    found = mismatches("a confirmation appears", effect(), "Profile", {})
    assert found == ["you expected a change, but nothing on the page changed"]


def test_expecting_nothing_to_change_is_fine_when_nothing_changed():
    for text in ["nothing changes", "the total stays the same", "page unchanged", ""]:
        assert mismatches(text, effect(), "x", {}) == [], text


def test_a_predicted_path_is_checked_against_the_url():
    went = effect(url_after="http://shop.test/cart")
    assert mismatches("goes to /cart", went, "", {}) == []
    assert mismatches("goes to /checkout", went, "", {}) == ["/checkout is not on the page"]


def test_effect_description_is_short_and_lists_what_changed():
    text = Effect(
        url_before="http://s/a",
        url_after="http://s/b",
        added=["Added to cart"],
        removed=["Cart (0)"],
        fields=["Quantity: 0 → 1"],
        events=["console error: boom"],
    ).describe()
    assert "now on http://s/b" in text and "Added to cart" in text and "Quantity: 0 → 1" in text
    assert "gone: Cart (0)" in text and "console error: boom" in text
    assert len(Effect("/a", "/a", added=["x" * 2000]).describe()) <= 400
    assert Effect("/a", "/a").describe() == "nothing on the page changed"


# --- in the loop -------------------------------------------------------------------------------

QTY, UPDATE, SAVE, ADD = 1, 2, 3, 4  # element ids on expect.html, in page order


def call(name, **args):
    return ToolCall(name, {"reasoning": "test", **args})


@pytest.fixture
def agent(context, site_url):
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )

    def make(decisions):
        llm = FakeClient(decisions=decisions)
        config = AgentConfig(
            target_url=f"{site_url}/expect.html",
            mode="interactive",
            budget=Budget(max_steps=20, max_seconds=60, max_cost_usd=1.0),
        )
        return AgentRun(context.new_page(), llm, guard, config), llm

    return make


def test_a_mismatch_is_shown_and_must_be_resolved_before_other_actions(agent):
    run, llm = agent(
        [
            call("type", element_id=QTY, text="3"),
            call("click", element_id=UPDATE, expect="Total: $36.00"),
            call("click", element_id=ADD, expect="'Note added'"),  # refused: mismatch open
            call(
                "report_bug",
                title="Total ignores quantity",
                severity="high",
                category="functional",
                expected="$36.00",
                actual="$12.00",
                step_ids=[1, 2],
                evidence="Total: $12.00",
            ),
            call("click", element_id=ADD, expect="'Note added'"),
        ]
    )
    result = run.run()
    update = result.steps[1]
    assert "MISMATCH" in update.result and "$36.00 is not on the page" in update.result
    assert update.args["check"]["flags"] == ["$36.00 is not on the page"]
    assert "UNRESOLVED MISMATCH" in llm.calls[2]["observation"]
    assert result.steps[2].blocked and "#2" in result.steps[2].block_reason
    assert "resolves the mismatch from #2" in result.steps[3].result
    assert not result.steps[4].blocked
    assert "UNRESOLVED MISMATCH" not in llm.calls[4]["observation"]
    assert len(result.bugs) == 1


def test_a_mismatch_can_be_dismissed_with_a_reason_but_not_without(agent):
    run, llm = agent(
        [
            call("click", element_id=SAVE, expect="a confirmation appears"),
            call("dismiss", step_id=1, reason=""),
            call("dismiss", step_id=1, reason="Save is disabled until something changes"),
            call("click", element_id=ADD, expect="'Note added'"),
        ]
    )
    result = run.run()
    assert "nothing on the page changed" in result.steps[0].args["check"]["flags"][0]
    assert result.steps[1].result.startswith("error")
    assert result.steps[2].result.startswith("dismissed")
    assert result.dismissed == [
        {
            "step": 1,
            "reason": "Save is disabled until something changes",
            "flags": result.steps[0].args["check"]["flags"],
        }
    ]
    assert not result.steps[3].blocked and result.steps[3].args["check"]["flags"] == []


def test_an_ignored_mismatch_blocks_once_then_expires(agent):
    run, _ = agent(
        [
            call("click", element_id=SAVE, expect="a confirmation appears"),
            call("click", element_id=ADD, expect="'Note added'"),
            call("click", element_id=ADD, expect="'Note added'"),
        ]
    )
    result = run.run()
    assert result.steps[1].blocked
    assert not result.steps[2].blocked  # a stubborn model can't stall the run
    assert result.ignored == [1]


def test_actions_that_dont_change_state_are_not_checked(agent):
    run, llm = agent([call("type", element_id=QTY, text="2"), call("scroll", direction="down")])
    result = run.run()
    assert "check" not in result.steps[0].args and "check" not in result.steps[1].args
    assert "UNRESOLVED" not in llm.calls[1]["observation"]


def test_a_viewport_switch_is_a_change_even_when_the_text_is_the_same():
    # Run 4's first J1 trace: "Mobile view of the Rooms page" was flagged as "nothing changed"
    # because the text stayed the same; the model had to spend a step dismissing it.
    switched = Effect("/a", "/a", viewport="desktop → mobile")
    assert switched.changed and "viewport desktop → mobile" in switched.describe()
    assert mismatches("mobile layout of the page", switched, "Rooms", {}) == []


def test_set_viewport_in_the_loop_raises_no_false_mismatch(agent):
    run, llm = agent([call("set_viewport", size="mobile", expect="the basket at phone width")])
    result = run.run()
    assert result.steps[0].args["check"]["flags"] == []


# --- the reviewer tier (run 5, K2) ---------------------------------------------------------------


@pytest.fixture
def tiered(context, site_url):
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )

    def make(decisions, reviewer_answers):
        explorer = FakeClient(decisions=decisions)
        reviewer = FakeClient(texts=reviewer_answers)
        reviewer.agent_model = "big-reviewer"
        config = AgentConfig(
            target_url=f"{site_url}/expect.html",
            mode="interactive",
            budget=Budget(max_steps=20, max_seconds=60, max_cost_usd=1.0),
        )
        run = AgentRun(context.new_page(), explorer, guard, config, reviewer=reviewer)
        return run, explorer, reviewer

    return make


BUG_ANSWER = (
    '{"bug": true, "reason": "total ignores quantity", "title": "Total ignores quantity", '
    '"severity": "high", "category": "functional", "expected": "$36.00", "actual": "$12.00"}'
)


def test_with_a_reviewer_a_flagged_step_is_decided_by_the_reviewer_not_the_explorer(tiered):
    run, explorer, reviewer = tiered(
        [
            call("type", element_id=QTY, text="3"),
            call("click", element_id=UPDATE, expect="Total: $36.00"),
            call("click", element_id=ADD, expect="'Note added'"),  # not refused: nothing open
        ],
        [BUG_ANSWER],
    )
    result = run.run()
    assert [c["method"] for c in reviewer.calls] == ["review_screenshot"]
    assert "$36.00" in reviewer.calls[0]["prompt"]
    update = result.steps[1]
    assert "reviewer filed a bug" in update.result and "Total ignores quantity" in update.result
    assert not result.steps[2].blocked
    assert all("UNRESOLVED MISMATCH" not in c["observation"] for c in explorer.calls)
    [bug] = result.bugs
    assert bug.title == "Total ignores quantity" and bug.severity == "high"
    assert bug.evidence["reported_at"] == 3  # replay repeats steps 1 and 2
    assert bug.evidence["reviewer"] == "big-reviewer"
    assert len(result.reviewer_usage) == 1


def test_a_flagged_step_the_reviewer_rejects_is_recorded_as_dismissed(tiered):
    run, _, _ = tiered(
        [call("click", element_id=SAVE, expect="a confirmation appears")],
        ['{"bug": false, "reason": "Save is disabled until something changes"}'],
    )
    result = run.run()
    assert result.bugs == []
    assert "reviewer: not a bug" in result.steps[0].result
    assert result.dismissed[0]["reason"] == "reviewer: Save is disabled until something changes"
    assert result.dismissed[0]["step"] == 1


def test_reviewer_cost_counts_against_the_run_budget(tiered):
    run, _, _ = tiered(
        [call("click", element_id=SAVE, expect="a confirmation appears")],
        ['{"bug": false, "reason": "r"}'],
    )
    run.reviewer._usage = lambda model, text: __import__("worker.llm", fromlist=["Usage"]).Usage(
        model=model, input_tokens=100, output_tokens=10, cost_usd=0.25
    )
    result = run.run()
    assert run.config.budget.cost_usd >= 0.25
    assert result.reviewer_usage[0].cost_usd == 0.25
