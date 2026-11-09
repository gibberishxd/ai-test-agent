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
    llm = FakeClient(texts=[json.dumps(issue)])

    process_next(sessions, llm, make_execute(settings, LocalStorage(tmp_path), browser))

    with sessions() as session:
        stored = session.get(Run, run.id)
        assert stored.status == RunStatus.DONE, stored.error
        steps = session.query(Step).filter_by(run_id=run.id).order_by(Step.index).all()
        bugs = session.query(Bug).filter_by(run_id=run.id).all()

    assert [s.action for s in steps][:2] == ["visit", "visit"]  # problems.html, then its links
    assert steps[-1].action == "review_screenshot"
    assert stored.pages_visited >= 2
    assert stored.step_count == len(steps)
    assert (tmp_path / steps[0].screenshot).exists()

    categories = {b.category for b in bugs}
    assert {"console-error", "network", "broken-link", "accessibility", "visual"} <= categories
    visual = next(b for b in bugs if b.category == "visual")
    assert visual.status == "candidate" and visual.source == "agent"
    assert stored.summary["bugs"] == len(bugs)


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
