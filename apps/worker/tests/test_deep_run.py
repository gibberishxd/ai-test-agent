"""Deep mode end to end, at $0: a queued deep run is claimed by the worker, crawled, driven by
the fake model (DEEP_SCRIPT) through map, plan, execute and review, and its findings verified:
one confirmed by re-measurement, one kept apart as unverified. Also: pausing on a usage limit
and resuming from the saved coverage."""

import json

import pytest

from worker.config import Settings
from worker.db.models import Bug, Run, Step, Workspace
from worker.deep.checklist import AREAS, VIEWPORTS
from worker.deep.run import resume, run_deep
from worker.deep.scripted import ScriptedDriver
from worker.execute import make_execute
from worker.llm import FakeClient, UsageLimitReached
from worker.runner import process_next
from worker.storage import LocalStorage

NO_DUPLICATES = json.dumps({"duplicates": []})
MAP = {
    "pages": [{"url": "/deep.html", "purpose": "a counter and a search"}],
    "flows": [{"name": "count", "description": "Add one raises the total"}],
    "summary": "one page",
}


def plan() -> dict:
    items = [
        {"id": f"{a.key}-1", "area": a.key, "description": a.title}
        for a in AREAS
        if a.key != "layout"
    ]
    items += [
        {"id": f"layout-{v}", "area": "layout", "viewport": v, "description": "layout"}
        for v in VIEWPORTS
    ]
    return {"items": items}


def script() -> list[list]:
    """The fake model's turns; harness step numbers are in the comments."""
    viewports = []
    for v in VIEWPORTS:  # steps 4–9
        w, h = (int(n) for n in v.split("x"))
        viewports += [["set_viewport", {"width": w, "height": h}], ["screenshot", {}]]
    total = "return document.querySelector('#total').textContent"
    execute = (
        viewports
        + [
            ["click", {"selector": "#add"}],  # 10
            ["flag_candidate", {"title": "Total after one add", "observation": "shows 1"}],  # 11
            ["visible_text", {}],  # 12: the re-check
            [
                "report_bug",
                {  # 13: re-measured in a fresh browser after replaying step 10
                    "candidate_id": "c1",
                    "title": "Total shows the count",
                    "severity": "low",
                    "category": "functional",
                    "expected": "1",
                    "actual": "1",
                    "self_review": "measured twice",
                    "verify": {"kind": "measure", "snippet": total, "setup_steps": [10]},
                },
            ],
            ["evaluate_js", {"snippet": "window.__seen = [1, 2]; return 1"}],  # 14
            ["flag_candidate", {"title": "Only in this tab", "observation": "a global"}],  # 15
            ["screenshot", {}],  # 16
            [
                "report_bug",
                {  # 17: a fresh browser has no such global: unverified
                    "candidate_id": "c2",
                    "title": "Depends on this tab's state",
                    "severity": "low",
                    "category": "other",
                    "expected": "-",
                    "actual": "2",
                    "self_review": "checked",
                    "verify": {
                        "kind": "measure",
                        "snippet": "return window.__seen.length",
                        "setup_steps": [],
                    },
                },
            ],
        ]
        + [["tick", {"item_id": i["id"], "status": "done", "note": "ok"}] for i in plan()["items"]]
    )
    return [
        [["snapshot", {}], ["save_map", MAP]],  # 1, 2
        [["save_plan", plan()]],  # 3
        execute,
        [["finish", {"summary": "tested everything on the list"}]],
    ]


@pytest.fixture
def settings(site_url, tmp_path):
    return Settings(
        _env_file=None,
        demo_url=site_url,
        clean_demo_url=site_url,
        dev_mode=True,
        data_dir=str(tmp_path),
        llm_provider="fake",
        deep_script=json.dumps(script()),
        review_pages=0,
        max_pages=1,
    )


def queue(sessions, site_url) -> str:
    with sessions() as session:
        ws = Workspace(name="w", slug="w")
        session.add(ws)
        session.flush()
        run = Run(
            workspace_id=ws.id,
            target_url=f"{site_url}/deep.html",
            mode="interactive",
            engine="deep",
        )
        session.add(run)
        session.commit()
        return str(run.id)


def test_a_deep_run_end_to_end_with_the_fake_model(sessions, settings, site_url, browser, tmp_path):
    run_id = queue(sessions, site_url)
    execute = make_execute(settings, LocalStorage(tmp_path), browser)
    assert process_next(sessions, FakeClient(texts=[NO_DUPLICATES]), execute, only=[run_id])
    with sessions() as session:
        run = session.get(Run, run_id)
        assert run.status == "done", run.error
        bugs = {b.title: b for b in session.query(Bug).filter_by(run_id=run.id)}
        assert bugs["Total shows the count"].status == "confirmed"
        assert bugs["Depends on this tab's state"].status == "unverified"
        assert run.coverage["phase"] == "done" and run.coverage["unticked"] == []
        assert set(run.coverage["screenshots"]) == set(VIEWPORTS)
        assert run.summary["engine"] == "deep" and run.summary["stop_reason"] == "finished"
        assert run.summary["verification"]["unverified"] == 1
        # The crawl's visits come first, then the deep steps, each with its screenshot.
        shots = [s for s in session.query(Step).filter_by(run_id=run.id) if s.screenshot]
        assert any(s.screenshot.endswith(".jpg") for s in shots)
        replayed = bugs["Total shows the count"].evidence["verify"]["setup_steps"]
        assert (
            session.query(Step).filter_by(run_id=run.id, index=replayed[0]).one().action == "click"
        )


class LimitDriver(ScriptedDriver):
    """Hits the plan's usage limit when the plan phase starts."""

    def run_turn(self, harness, prompt):
        if harness.phase == "plan":
            raise UsageLimitReached("weekly limit")
        super().run_turn(harness, prompt)


def test_a_usage_limit_pauses_the_run_and_resume_continues_it(
    sessions, settings, site_url, browser, tmp_path
):
    storage = LocalStorage(tmp_path)
    run_id = queue(sessions, site_url)
    turns = script()

    def first(session, run, llm):
        run_deep(session, run, llm, settings, storage, browser, driver=LimitDriver(turns[:1]))

    process_next(sessions, FakeClient(texts=[NO_DUPLICATES]), first, only=[run_id])
    with sessions() as session:
        run = session.get(Run, run_id)
        assert run.status == "paused" and "weekly limit" in run.paused_reason
        assert run.coverage["phase"] == "plan" and run.coverage["map"]
        steps_before = run.step_count
        resume(session, run_id)
        assert session.get(Run, run_id).status == "queued"

    def second(session, run, llm):
        run_deep(session, run, llm, settings, storage, browser, driver=ScriptedDriver(turns[1:]))

    process_next(sessions, FakeClient(texts=[NO_DUPLICATES] * 3), second, only=[run_id])
    with sessions() as session:
        run = session.get(Run, run_id)
        assert run.status == "done", run.error
        assert run.paused_reason is None
        assert run.coverage["phase"] == "done"
        assert run.step_count > steps_before  # numbering continued, nothing overwritten


def test_only_a_paused_run_can_be_resumed(sessions, site_url):
    run_id = queue(sessions, site_url)
    with sessions() as session, pytest.raises(ValueError):
        resume(session, run_id)


class LimitedJudge(FakeClient):
    """The judge's model is out of its plan's usage too (the same login): every call refuses."""

    def complete(self, prompt, system=None, cheap=True):
        raise UsageLimitReached("usage limit reached (five_hour)")

    def review_screenshot(self, prompt, image, system=None):
        raise UsageLimitReached("usage limit reached (five_hour)")


class MustNotRun(ScriptedDriver):
    def run(self, harness):
        raise AssertionError("the agent ran again although it had finished")


def test_a_usage_limit_during_verification_pauses_instead_of_failing(
    sessions, settings, site_url, browser, tmp_path
):
    storage = LocalStorage(tmp_path)
    run_id = queue(sessions, site_url)

    def first(session, run, llm):
        run_deep(session, run, llm, settings, storage, browser, driver=LimitDriver(script()[:1]))

    process_next(sessions, LimitedJudge(), first, only=[run_id])
    with sessions() as session:
        run = session.get(Run, run_id)
        assert run.status == "paused", run.error
        # The first reason is kept: the agent's own limit, before verification hit it too.
        assert run.error is None and "weekly limit" in run.paused_reason


def test_a_run_whose_agent_finished_resumes_with_verification_only(
    sessions, settings, site_url, browser, tmp_path
):
    storage = LocalStorage(tmp_path)
    run_id = queue(sessions, site_url)

    def first(session, run, llm):
        run_deep(session, run, llm, settings, storage, browser, driver=ScriptedDriver(script()))

    process_next(sessions, LimitedJudge(), first, only=[run_id])
    with sessions() as session:
        run = session.get(Run, run_id)
        assert run.status == "paused" and run.coverage["stop_reason"] == "finished"
        pending = session.query(Bug).filter_by(run_id=run.id, status="candidate").count()
        assert pending >= 2  # the agent's findings wait for verification
        resume(session, run_id)

    def second(session, run, llm):
        run_deep(session, run, llm, settings, storage, browser, driver=MustNotRun([]))

    process_next(sessions, FakeClient(texts=[NO_DUPLICATES] * 3), second, only=[run_id])
    with sessions() as session:
        run = session.get(Run, run_id)
        assert run.status == "done", run.error
        bugs = {b.title: b.status for b in session.query(Bug).filter_by(run_id=run.id)}
        assert bugs["Total shows the count"] == "confirmed"
        assert bugs["Depends on this tab's state"] == "unverified"
