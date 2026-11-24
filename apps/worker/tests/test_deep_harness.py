"""Deep mode's harness: the process is enforced by code, not only asked for in the prompt.
Map before plan, a plan that covers the whole checklist, every item ticked before finishing,
screenshots at every viewport, and a re-check between flagging a candidate and reporting it.
A scripted driver plays the model, against real pages: no model, no cost."""

from urllib.parse import urlsplit

import pytest

from worker.deep.checklist import AREAS, VIEWPORTS
from worker.deep.harness import Harness, HarnessConfig, MemoryRecorder
from worker.deep.scripted import ScriptedDriver
from worker.deep.toolbox import Toolbox, ToolboxConfig
from worker.llm import UsageLimitReached
from worker.safety.network import NetworkGuard

MAP = {
    "pages": [{"url": "/deep.html", "purpose": "a counter and a search field"}],
    "flows": [{"name": "count", "description": "press Add one, the total goes up"}],
    "summary": "a one-page tool",
}


def full_plan() -> dict:
    """A plan that covers every area, with layout at every viewport."""
    items = [
        {"id": f"{area.key}-1", "area": area.key, "description": f"check {area.title}"}
        for area in AREAS
        if area.key != "layout"
    ]
    items += [
        {"id": f"layout-{v}", "area": "layout", "viewport": v, "description": "layout"}
        for v in VIEWPORTS
    ]
    return {"items": items, "not_applicable": []}


def ticks(plan: dict) -> list[tuple[str, dict]]:
    return [("tick", {"item_id": i["id"], "status": "done", "note": "ok"}) for i in plan["items"]]


def screenshots_at_every_viewport() -> list[tuple[str, dict]]:
    calls = []
    for v in VIEWPORTS:
        width, height = (int(n) for n in v.split("x"))
        calls += [("set_viewport", {"width": width, "height": height}), ("screenshot", {})]
    return calls


@pytest.fixture
def make(context, site_url):
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )

    def build(path="/deep.html", coverage=None, **config):
        page = context.new_page()
        toolbox = Toolbox(page, guard, ToolboxConfig(target_url=f"{site_url}{path}"))
        toolbox.start()
        recorder = MemoryRecorder()
        fields = {"max_steps": 200, "max_seconds": 120, **config}
        harness = Harness(toolbox, HarnessConfig(**fields), recorder, coverage=coverage)
        return harness, recorder, page

    return build


# --- phases --------------------------------------------------------------------------------


def test_a_full_run_goes_map_plan_execute_review_and_finishes(make):
    harness, recorder, _ = make()
    plan = full_plan()
    driver = ScriptedDriver(
        [
            [("snapshot", {}), ("save_map", MAP)],
            [("save_plan", plan)],
            [*screenshots_at_every_viewport(), *ticks(plan)],
            [("finish", {"summary": "all done"})],
        ]
    )
    result = driver.run(harness)
    assert result.stop_reason == "finished"
    coverage = recorder.coverage
    assert coverage["phase"] == "done"
    assert coverage["map"]["pages"][0]["url"] == "/deep.html"
    assert len(coverage["plan"]) == len(plan["items"])
    assert all(p["status"] == "done" for p in coverage["progress"].values())
    assert set(coverage["screenshots"]) == set(VIEWPORTS)


def test_the_first_prompt_asks_for_the_map(make):
    harness, _, _ = make()
    assert "map" in harness.next_prompt().lower()


def test_no_plan_before_the_map(make):
    harness, _, _ = make()
    harness.next_prompt()
    result = harness.call("save_plan", full_plan())
    assert result.is_error and "map" in result.text.lower()


def test_a_map_needs_pages_and_flows(make):
    harness, _, _ = make()
    harness.next_prompt()
    assert harness.call("save_map", {"pages": [], "flows": [], "summary": ""}).is_error


def test_a_plan_must_cover_every_checklist_area(make):
    harness, _, _ = make()
    harness.next_prompt()
    harness.call("save_map", MAP)
    harness.next_prompt()
    plan = full_plan()
    plan["items"] = [i for i in plan["items"] if i["area"] != "accessibility"]
    result = harness.call("save_plan", plan)
    assert result.is_error and "accessibility" in result.text


def test_an_area_can_be_marked_not_applicable_with_a_reason(make):
    harness, _, _ = make()
    harness.next_prompt()
    harness.call("save_map", MAP)
    harness.next_prompt()
    plan = full_plan()
    plan["items"] = [i for i in plan["items"] if i["area"] != "meta"]
    plan["not_applicable"] = [{"area": "meta", "reason": "an internal tool with no public pages"}]
    assert not harness.call("save_plan", plan).is_error


def test_layout_must_be_planned_at_every_viewport(make):
    harness, _, _ = make()
    harness.next_prompt()
    harness.call("save_map", MAP)
    harness.next_prompt()
    plan = full_plan()
    plan["items"] = [i for i in plan["items"] if i.get("viewport") != "768x1024"]
    result = harness.call("save_plan", plan)
    assert result.is_error and "768x1024" in result.text


def test_execute_prompts_hand_out_pending_items(make):
    harness, _, _ = make()
    harness.next_prompt()
    harness.call("save_map", MAP)
    harness.next_prompt()
    harness.call("save_plan", full_plan())
    prompt = harness.next_prompt()
    assert "flows-1" in prompt


def test_finish_is_refused_while_items_are_open(make):
    harness, _, _ = make()
    harness.next_prompt()
    harness.call("save_map", MAP)
    harness.next_prompt()
    harness.call("save_plan", full_plan())
    harness.next_prompt()
    result = harness.call("finish", {"summary": "done"})
    assert result.is_error and "flows-1" in result.text


def test_finish_is_refused_without_screenshots_at_every_viewport(make):
    harness, _, _ = make()
    plan = full_plan()
    harness.next_prompt()
    harness.call("save_map", MAP)
    harness.next_prompt()
    harness.call("save_plan", plan)
    harness.next_prompt()
    for name, args in ticks(plan):
        harness.call(name, args)
    result = harness.call("finish", {"summary": "done"})
    assert result.is_error and "390x844" in result.text


def test_tick_only_knows_planned_items(make):
    harness, _, _ = make()
    harness.next_prompt()
    harness.call("save_map", MAP)
    harness.next_prompt()
    harness.call("save_plan", full_plan())
    harness.next_prompt()
    assert harness.call("tick", {"item_id": "nope", "status": "done", "note": ""}).is_error


# --- candidates and reports ---------------------------------------------------------------


def executing(make):
    harness, recorder, page = make()
    harness.next_prompt()
    harness.call("save_map", MAP)
    harness.next_prompt()
    harness.call("save_plan", full_plan())
    harness.next_prompt()
    return harness, recorder, page


BUG = {
    "title": "Total doesn't go up",
    "severity": "high",
    "category": "functional",
    "expected": "1",
    "actual": "0",
    "self_review": "re-checked after a reload: still 0; not a deliberate limit",
}


def test_a_report_needs_a_flagged_candidate(make):
    harness, _, _ = executing(make)
    result = harness.call(
        "report_bug", {**BUG, "candidate_id": "c9", "verify": {"kind": "replay", "steps": []}}
    )
    assert result.is_error and "candidate" in result.text


def test_a_report_needs_a_recheck_after_the_flag(make):
    harness, _, _ = executing(make)
    harness.call("flag_candidate", {"title": "total", "observation": "stays 0"})
    result = harness.call(
        "report_bug", {**BUG, "candidate_id": "c1", "verify": {"kind": "replay", "steps": [1]}}
    )
    assert result.is_error and "re-check" in result.text


def test_a_replay_report_names_steps_that_happened(make):
    harness, recorder, _ = executing(make)
    harness.call("snapshot", {})
    click = harness.call("click", {"selector": "#add"})
    harness.call("flag_candidate", {"title": "total", "observation": "check"})
    harness.call("visible_text", {})
    step = click.step
    bad = harness.call(
        "report_bug", {**BUG, "candidate_id": "c1", "verify": {"kind": "replay", "steps": [999]}}
    )
    assert bad.is_error
    good = harness.call(
        "report_bug", {**BUG, "candidate_id": "c1", "verify": {"kind": "replay", "steps": [step]}}
    )
    assert not good.is_error
    bug = recorder.bugs[-1]
    assert bug.step_indexes == [step]
    assert bug.evidence["verify"] == {"kind": "replay", "steps": [step]}
    assert bug.evidence["self_review"].startswith("re-checked")
    assert bug.evidence["engine"] == "deep"
    assert bug.source == "agent" and bug.status == "candidate"


def test_a_measurement_report_stores_what_the_harness_measured_itself(make):
    harness, recorder, _ = executing(make)
    harness.call("flag_candidate", {"title": "faint text", "observation": "light grey"})
    harness.call("screenshot", {})
    snippet = "return getComputedStyle(document.querySelector('#faint')).color"
    result = harness.call(
        "report_bug",
        {
            **BUG,
            "title": "Faint text",
            "category": "accessibility",
            "candidate_id": "c1",
            "verify": {
                "kind": "measure",
                "snippet": snippet,
                "setup_steps": [],
                "observed_value": "rgb(187, 187, 187)",
            },
        },
    )
    assert not result.is_error
    measured = recorder.bugs[-1].evidence["verify"]
    assert measured["kind"] == "measure" and measured["snippet"] == snippet
    assert measured["result"] == "rgb(187, 187, 187)"  # measured by the harness, not claimed
    assert measured["viewport"] and measured["url"].endswith("/deep.html")


def test_a_check_report_must_name_a_rule_the_check_finds_now(make):
    harness, recorder, _ = executing(make)
    harness.call("flag_candidate", {"title": "contrast", "observation": "faint"})
    harness.call("run_axe", {})
    missing = harness.call(
        "report_bug",
        {
            **BUG,
            "candidate_id": "c1",
            "verify": {"kind": "check", "check": "run_axe", "rule": "image-alt"},
        },
    )
    assert missing.is_error and "image-alt" in missing.text
    found = harness.call(
        "report_bug",
        {
            **BUG,
            "candidate_id": "c1",
            "verify": {"kind": "check", "check": "run_axe", "rule": "color-contrast"},
        },
    )
    assert not found.is_error
    assert recorder.bugs[-1].evidence["verify"]["rule"] == "color-contrast"


def test_a_dropped_candidate_is_resolved(make):
    harness, recorder, _ = executing(make)
    harness.call("flag_candidate", {"title": "x", "observation": "y"})
    assert not harness.call("drop_candidate", {"candidate_id": "c1", "reason": "standard"}).is_error
    assert recorder.coverage["candidates"][0]["status"] == "dropped"


def test_finish_is_refused_while_candidates_are_open(make):
    harness, _, _ = executing(make)
    plan = full_plan()
    for name, args in screenshots_at_every_viewport() + ticks(plan):
        harness.call(name, args)
    harness.call("flag_candidate", {"title": "x", "observation": "y"})
    result = harness.call("finish", {"summary": "done"})
    assert result.is_error and "c1" in result.text


# --- budgets, stopping, pausing -----------------------------------------------------------


def test_every_call_is_a_numbered_step_and_is_recorded(make):
    harness, recorder, _ = make()
    harness.next_prompt()
    result = harness.call("snapshot", {})
    assert result.step == 1 and result.text.startswith("#1 ")
    assert recorder.actions[0].tool == "snapshot"


def test_the_step_budget_stops_the_run(make):
    harness, _, _ = make(max_steps=3)
    harness.next_prompt()
    for _ in range(3):
        harness.call("snapshot", {})
    result = harness.call("snapshot", {})
    assert result.is_error and "budget" in result.text
    assert harness.stop_reason.startswith("step budget")
    assert harness.next_prompt() is None


def test_near_the_end_of_the_budget_it_asks_to_resolve_candidates(make):
    harness, _, _ = executing(make)
    harness.config.max_steps = harness.steps + 2  # almost used up
    harness.call("flag_candidate", {"title": "x", "observation": "y"})
    prompt = harness.next_prompt()
    assert "c1" in prompt and "budget" in prompt.lower()


def test_a_model_that_stops_making_progress_is_stopped(make):
    harness, _, _ = make()
    driver = ScriptedDriver([[("snapshot", {})]] * 10)
    result = driver.run(harness)
    assert "no progress" in result.stop_reason


def test_a_usage_limit_pauses_and_saves_everything(make):
    harness, recorder, _ = make()

    class LimitDriver(ScriptedDriver):
        def run_turn(self, harness, prompt):
            if harness.phase == "plan":
                raise UsageLimitReached("weekly limit")
            super().run_turn(harness, prompt)

    driver = LimitDriver([[("save_map", MAP)], [("save_plan", full_plan())]])
    result = driver.run(harness)
    assert result.stop_reason == "paused: usage limit"
    assert harness.paused
    assert recorder.coverage["phase"] == "plan" and recorder.coverage["map"]["pages"]


def test_a_paused_run_resumes_where_it_stopped(make):
    first, recorder, _ = make()
    first.next_prompt()
    first.call("save_map", MAP)
    first.next_prompt()
    first.call("save_plan", full_plan())
    first.next_prompt()
    first.call("tick", {"item_id": "flows-1", "status": "done", "note": "ok"})
    saved = recorder.coverage

    second, _, _ = make(coverage=saved)
    assert second.phase == "execute" and second.steps == first.steps
    prompt = second.next_prompt()
    assert "resum" in prompt.lower()
    assert "flows-1" not in prompt.split("PENDING")[-1]  # already done
    assert second.call("snapshot", {}).step == first.steps + 1


def test_finish_near_the_end_of_the_budget_lists_what_was_left(make):
    harness, recorder, _ = executing(make)
    harness.config.max_steps = harness.steps + 1
    result = harness.call("finish", {"summary": "out of steps"})
    assert not result.is_error
    assert "flows-1" in recorder.coverage["unticked"]


FAINT = "return getComputedStyle(document.querySelector('#faint')).color"


def report_measured(harness, **verify):
    harness.call("flag_candidate", {"title": "faint text", "observation": "light grey"})
    harness.call("screenshot", {})
    spec = {"kind": "measure", "snippet": FAINT, "setup_steps": [], **verify}
    return harness.call("report_bug", {**BUG, "candidate_id": "c1", "verify": spec})


def test_a_measurement_report_must_say_the_value_it_saw(make):
    harness, recorder, _ = executing(make)
    result = report_measured(harness)
    assert result.is_error and "observed_value" in result.text
    assert recorder.bugs == []


def test_a_claimed_value_the_harness_doesnt_measure_now_is_refused(make):
    # The evaluation's $NaN report: the snippet was run on a page where the bug didn't show.
    harness, recorder, _ = executing(make)
    result = report_measured(harness, observed_value="rgb(0, 0, 0)")
    assert result.is_error
    assert "rgb(187, 187, 187)" in result.text and "rgb(0, 0, 0)" in result.text
    assert recorder.bugs == []
    retry = harness.call(
        "report_bug",
        {
            **BUG,
            "candidate_id": "c1",
            "verify": {
                "kind": "measure",
                "snippet": FAINT,
                "setup_steps": [],
                "observed_value": "rgb(187, 187, 187)",
            },
        },
    )
    assert not retry.is_error  # the candidate stays open, so it can be reported correctly


def test_the_claim_allows_rounding_only(make):
    harness, _, _ = executing(make)
    harness.call("flag_candidate", {"title": "width", "observation": "w"})
    harness.call("screenshot", {})
    spec = {"kind": "measure", "snippet": "return 12.04", "setup_steps": [], "observed_value": 12}
    assert not harness.call("report_bug", {**BUG, "candidate_id": "c1", "verify": spec}).is_error
