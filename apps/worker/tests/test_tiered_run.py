"""A whole interactive run with the reviewer tier (run 5, K2).

The explorer drives the browser; the reviewer decides on the flagged step and on the explorer's
own report; the run stores the reviewer's tokens and cost apart from the total.
"""

import json

import pytest

from worker.config import Settings
from worker.db.models import Bug, Run, RunStatus, Step
from worker.execute import make_execute
from worker.llm import FakeClient, ToolCall, Usage
from worker.runner import process_next
from worker.storage import LocalStorage

QTY, UPDATE = 1, 2  # element ids on expect.html (see test_expectations.py)


def call(name, **args):
    return ToolCall(name, {"reasoning": "test", **args})


@pytest.fixture
def settings(site_url, tmp_path):
    return Settings(
        _env_file=None, demo_url=site_url, clean_demo_url=site_url, dev_mode=True,
        data_dir=str(tmp_path), max_steps=8, review_pages=0,
    )  # fmt: skip


class PricedFake(FakeClient):
    """A reviewer with a price, so its cost can be told apart from the explorer's ($0)."""

    def _usage(self, model, text):
        return Usage(model=model, input_tokens=1000, output_tokens=100, cost_usd=0.01)


def test_a_tiered_run_lets_the_reviewer_decide_and_records_its_cost(
    sessions, workspace, settings, site_url, tmp_path, browser
):
    explorer = FakeClient(
        decisions=[
            call("type", element_id=QTY, text="3"),
            call("click", element_id=UPDATE, expect="Total: $36.00"),
            call(
                "report_bug",
                title="Notes box looks plain",
                severity="low",
                category="ux",
                expected="nicer",
                actual="plain",
                step_ids=[1],
                evidence="plain",
            ),
            call("finish", summary="done"),
        ],
        default_text='{"duplicates": [], "reproduced": true, "reason": "seen"}',
    )
    reviewer = PricedFake(
        texts=[
            json.dumps(
                {
                    "bug": True,
                    "reason": "total ignores quantity",
                    "title": "Total ignores quantity",
                    "severity": "high",
                    "category": "functional",
                    "expected": "$36.00",
                    "actual": "$12.00",
                }
            ),
            '{"bug": false, "reason": "a design preference, not a bug"}',
        ]
    )
    reviewer.agent_model = "big-reviewer"
    with sessions() as session:
        run = Run(
            workspace_id=workspace.id, target_url=f"{site_url}/expect.html", mode="interactive"
        )
        session.add(run)
        session.commit()

    execute = make_execute(settings, LocalStorage(tmp_path), browser, reviewer=reviewer)
    process_next(sessions, explorer, execute)

    with sessions() as session:
        stored = session.get(Run, run.id)
        assert stored.status == RunStatus.DONE, stored.error
        bugs = {b.title: b for b in session.query(Bug).filter_by(run_id=run.id, source="agent")}
        assert bugs["Total ignores quantity"].status == "confirmed"
        assert bugs["Total ignores quantity"].evidence["reviewer"] == "big-reviewer"
        plain = bugs["Notes box looks plain"]
        assert plain.status == "dismissed"
        assert plain.dismiss_reason == "reviewer: a design preference, not a bug"
        assert (stored.reviewer_provider, stored.reviewer_model) == ("fake", "big-reviewer")
        assert stored.reviewer_input_tokens == 2000 and stored.reviewer_output_tokens == 200
        assert stored.reviewer_cost_usd == pytest.approx(0.02)
        assert stored.cost_usd >= stored.reviewer_cost_usd
        reviews = session.query(Step).filter_by(run_id=run.id, action="review").all()
        assert len(reviews) == 2
    replay_judge = [c for c in explorer.calls if c["method"] == "review_screenshot"]
    assert len(replay_judge) <= 1  # the reviewer's bug is replayed; the dropped one isn't


def test_without_a_reviewer_nothing_is_recorded_for_one(
    sessions, workspace, settings, site_url, tmp_path, browser
):
    explorer = FakeClient(decisions=[call("finish", summary="done")])
    with sessions() as session:
        run = Run(
            workspace_id=workspace.id, target_url=f"{site_url}/expect.html", mode="interactive"
        )
        session.add(run)
        session.commit()
    process_next(sessions, explorer, make_execute(settings, LocalStorage(tmp_path), browser))
    with sessions() as session:
        stored = session.get(Run, run.id)
        assert stored.reviewer_model is None and stored.reviewer_cost_usd == 0
