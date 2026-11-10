"""A whole passive run through the queue: real browser, real database, FakeClient for the model."""

import json

import pytest

from worker.config import Settings
from worker.db.models import Bug, Run, RunStatus, Step
from worker.execute import make_execute
from worker.llm import FakeClient
from worker.review import parse_issues
from worker.runner import process_next
from worker.storage import LocalStorage


@pytest.fixture
def settings(site_url, tmp_path):
    # The test site plays the demo shop: dev mode lets the guard allow it on localhost.
    return Settings(
        _env_file=None,
        demo_url=site_url,
        clean_demo_url=site_url,
        dev_mode=True,
        review_pages=1,
        data_dir=str(tmp_path),
    )


def queue_run(sessions, workspace, url) -> Run:
    with sessions() as session:
        run = Run(workspace_id=workspace.id, target_url=url, mode="passive")
        session.add(run)
        session.commit()
        return run


def test_passive_run_writes_steps_bugs_and_cost(
    sessions, workspace, settings, site_url, tmp_path, browser
):
    run = queue_run(sessions, workspace, f"{site_url}/problems.html")
    issue = [{"title": "Price shows NaN", "severity": "high", "expected": "$5", "actual": "$NaN"}]
    # 1st answer: the screenshot review; 2nd: replay confirms it; then dedup finds nothing.
    llm = FakeClient(texts=[json.dumps(issue), '{"reproduced": true, "reason": "NaN is shown"}'])

    process_next(sessions, llm, make_execute(settings, LocalStorage(tmp_path), browser))

    with sessions() as session:
        stored = session.get(Run, run.id)
        assert stored.status == RunStatus.DONE, stored.error
        steps = session.query(Step).filter_by(run_id=run.id).order_by(Step.index).all()
        bugs = session.query(Bug).filter_by(run_id=run.id).all()

    assert [s.action for s in steps][:2] == ["visit", "visit"]  # problems.html, then its links
    assert [s.action for s in steps if s.action != "visit"] == [
        "review_screenshot",
        "verify_bug",
        "dedupe",
    ]
    assert stored.pages_visited >= 2
    assert stored.step_count == len(steps)
    assert (tmp_path / steps[0].screenshot).exists()

    categories = {b.category for b in bugs}
    assert {"console-error", "network", "broken-link", "accessibility", "visual"} <= categories
    visual = next(b for b in bugs if b.category == "visual")
    assert visual.status == "confirmed" and visual.source == "agent"
    assert visual.evidence["replay"] == "NaN is shown"
    assert stored.summary["bugs"] == len(bugs)
    assert stored.summary["verification"]["confirmed"] == 1


def test_private_target_is_refused(sessions, workspace, settings, browser):
    run = queue_run(sessions, workspace, "http://10.1.2.3/")
    execute = make_execute(settings, LocalStorage(settings.data_path()), browser)
    process_next(sessions, FakeClient(), execute)
    with sessions() as session:
        stored = session.get(Run, run.id)
    assert stored.status == RunStatus.FAILED
    assert "not allowed" in stored.error


def test_parse_issues_ignores_prose_and_bad_json():
    assert parse_issues("No problems found.") == []
    assert parse_issues("[not json]") == []
    assert parse_issues('Here: [{"title": "x", "severity": "low"}]') == [
        {"title": "x", "severity": "low"}
    ]


def test_interactive_run_records_agent_steps_bugs_and_cost(
    sessions, workspace, settings, site_url, tmp_path, browser
):
    from worker.llm import ToolCall

    with sessions() as session:
        run = Run(workspace_id=workspace.id, target_url=f"{site_url}/form.html", mode="interactive")
        session.add(run)
        session.commit()
    llm = FakeClient(
        decisions=[
            ToolCall("type", {"element_id": 1, "text": "Test User", "reasoning": "fill the name"}),
            # Blocked. (A deny-list click wouldn't be: this site plays the demo shop.)
            ToolCall("navigate", {"url": "https://example.com/", "reasoning": "leave"}),
            ToolCall(
                "report_bug",
                {
                    "title": "Save does nothing",
                    "severity": "high",
                    "category": "functional",
                    "expected": "Saved",
                    "actual": "nothing",
                    "step_ids": [1],
                    "evidence": "",
                    "reasoning": "seen",
                },
            ),
            ToolCall("finish", {"summary": "done", "reasoning": "done"}),
        ]
    )
    process_next(sessions, llm, make_execute(settings, LocalStorage(tmp_path), browser))

    with sessions() as session:
        stored = session.get(Run, run.id)
        assert stored.status == RunStatus.DONE, stored.error
        steps = session.query(Step).filter_by(run_id=run.id).order_by(Step.index).all()
        bugs = session.query(Bug).filter_by(run_id=run.id).all()

    agent_steps = [s for s in steps if s.action != "visit"]
    assert [s.action for s in agent_steps] == [
        "type",
        "navigate",
        "report_bug",
        "finish",
        "verify_bug",  # no "dedupe": fewer than two bugs survive, so there's nothing to merge
    ]
    assert agent_steps[1].blocked and "origin" in agent_steps[1].block_reason
    assert agent_steps[0].reasoning == "fill the name"
    assert [s.index for s in steps] == list(range(len(steps)))  # one numbering for the run
    [agent_bug] = [b for b in bugs if b.source == "agent"]
    assert agent_bug.step_indexes == [agent_steps[0].index]
    # Replay covers every agent action before the report, not just the steps the model listed.
    assert agent_bug.evidence["replay_from"] == agent_steps[0].index
    assert agent_bug.evidence["reported_at"] == agent_steps[2].index
    # FakeClient's default answer isn't a "reproduced" verdict, so replay dismisses it.
    assert agent_bug.status == "dismissed" and agent_bug.dismiss_reason.startswith("replay:")
    assert stored.summary["stop_reason"] == "finished"


def test_interactive_mode_is_refused_on_other_targets(sessions, workspace, settings, browser):
    with sessions() as session:
        run = Run(workspace_id=workspace.id, target_url="https://example.com/", mode="interactive")
        session.add(run)
        session.commit()
    process_next(
        sessions, FakeClient(), make_execute(settings, LocalStorage(settings.data_path()), browser)
    )
    with sessions() as session:
        stored = session.get(Run, run.id)
    assert stored.status == RunStatus.FAILED
    assert "interactive mode" in stored.error
