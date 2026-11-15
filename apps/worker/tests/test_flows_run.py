"""Run 7, M4: critical flows in a whole run: the agent completes a journey and its script is
saved; the next run replays it without a model; a broken replay is repaired; a journey the agent
can't complete becomes a finding. Against the local test site (form.html: Name, Save)."""

import pytest

from worker.config import Settings
from worker.db.models import Bug, Flow, FlowResult, Run, RunStatus, Target
from worker.execute import make_execute
from worker.llm import FakeClient, ToolCall
from worker.runner import process_next
from worker.storage import LocalStorage

NAME, SAVE = 1, 2  # element ids on form.html
JOURNEY = "Change your name to Ada and save it."


def call(name, **args):
    return ToolCall(name, {"reasoning": "test", **args})


def completes(name="Ada", summary='PASSED: the page shows "Saved: Ada"'):
    return [
        call("type", element_id=NAME, text=name),
        call("click", element_id=SAVE, expect="'Saved'"),
        call("finish", summary=summary),
    ]


@pytest.fixture
def settings(site_url, tmp_path):
    return Settings(
        _env_file=None, demo_url=site_url, clean_demo_url=site_url, dev_mode=True,
        data_dir=str(tmp_path), max_steps=10, review_pages=0, use_specs=False,
    )  # fmt: skip


@pytest.fixture
def flow(sessions, workspace, site_url):
    with sessions() as session:
        target = Target(workspace_id=workspace.id, origin=site_url)
        session.add(target)
        session.flush()
        flow = Flow(
            workspace_id=workspace.id, target_id=target.id, name="Change name", goal=JOURNEY
        )
        session.add(flow)
        session.commit()
        return flow


def start_run(sessions, workspace, site_url, settings, tmp_path, browser, decisions):
    llm = FakeClient(
        decisions=decisions, default_text='{"duplicates": [], "reproduced": true, "reason": "seen"}'
    )
    with sessions() as session:
        run = Run(workspace_id=workspace.id, target_url=f"{site_url}/form.html", mode="interactive")
        session.add(run)
        session.commit()
        run_id = run.id
    process_next(sessions, llm, make_execute(settings, LocalStorage(tmp_path), browser))
    return run_id, llm


def result_of(sessions, run_id):
    with sessions() as session:
        run = session.get(Run, run_id)
        assert run.status == RunStatus.DONE, run.error
        [result] = session.query(FlowResult).filter_by(run_id=run_id).all()
        return result


def test_a_completed_journey_is_saved_then_replayed_without_the_model(
    sessions, workspace, site_url, settings, tmp_path, browser, flow
):
    first, llm = start_run(sessions, workspace, site_url, settings, tmp_path, browser, completes())
    assert "CRITICAL FLOW" in llm.calls[0]["observation"]  # the journey came first
    result = result_of(sessions, first)
    assert (result.status, result.replayed, result.model_calls) == ("passed", False, 3)
    with sessions() as session:
        saved = session.get(Flow, flow.id)
        assert [s["action"] for s in saved.script["steps"]] == ["type", "click"]
        assert saved.script["checks"] == ["Saved: Ada"]
        assert (saved.last_status, saved.last_run_id) == ("passed", first)

    # Run 2: the explorer only finishes; the journey is replayed with no model call for it.
    second, llm = start_run(
        sessions, workspace, site_url, settings, tmp_path, browser, [call("finish", summary="done")]
    )
    result = result_of(sessions, second)
    assert (result.status, result.replayed, result.model_calls) == ("replayed", True, 0)
    decisions = [c for c in llm.calls if c["method"] == "decide"]
    assert all("CRITICAL FLOW" not in c["observation"] for c in decisions)


def test_a_broken_replay_is_repaired_by_the_agent_and_the_script_updated(
    sessions, workspace, site_url, settings, tmp_path, browser, flow
):
    with sessions() as session:
        stale = session.get(Flow, flow.id)
        stale.script = {
            "start_url": f"{site_url}/form.html",
            "steps": [
                {
                    "action": "click",
                    "args": {},
                    "element": {"role": "button", "name": "Old save"},
                    "url": f"{site_url}/form.html",
                }
            ],
            "checks": ["Saved"],
            "end_path": "/form.html",
        }
        session.commit()
    run_id, _ = start_run(sessions, workspace, site_url, settings, tmp_path, browser, completes())
    result = result_of(sessions, run_id)
    assert result.status == "repaired" and "replay had broken" in result.detail
    with sessions() as session:
        assert [s["element"]["name"] for s in session.get(Flow, flow.id).script["steps"]] == [
            "Name",
            "Save",
        ]


def test_a_journey_the_agent_cant_complete_becomes_a_finding_and_is_rechecked_for_free(
    sessions, workspace, site_url, settings, tmp_path, browser, flow
):
    failing = [
        call("type", element_id=NAME, text="Ada"),
        call("click", element_id=SAVE, expect="'Profile saved'"),
        call("finish", summary='FAILED: nothing shown, expected "Profile saved"'),
    ]
    run_id, _ = start_run(sessions, workspace, site_url, settings, tmp_path, browser, failing)
    result = result_of(sessions, run_id)
    assert result.status == "failed" and result.model_calls == 3
    with sessions() as session:
        bug = (
            session.query(Bug)
            .filter(Bug.run_id == run_id, Bug.title.like("Critical flow failed%"))
            .one()
        )
        assert bug.expected == JOURNEY and bug.evidence["flow"]["name"] == "Change name"
        saved = session.get(Flow, flow.id).script
        assert saved["failing"] is True and saved["checks"] == ["Profile saved"]

    # Run 2: the failing script is replayed with no model; the same failure is found again.
    second, llm = start_run(
        sessions, workspace, site_url, settings, tmp_path, browser, [call("finish", summary="done")]
    )
    result = result_of(sessions, second)
    assert (result.status, result.replayed, result.model_calls) == ("failed", True, 0)
    assert "still failing" in result.detail
    assert all(
        "CRITICAL FLOW" not in c["observation"] for c in llm.calls if c["method"] == "decide"
    )
    with sessions() as session:
        again = (
            session.query(Bug)
            .filter(Bug.run_id == second, Bug.title.like("Critical flow failed%"))
            .one()
        )
        assert again.status == "confirmed" and again.evidence["replayed_script"] is True


def test_a_failure_without_a_quoted_expectation_saves_nothing(
    sessions, workspace, site_url, settings, tmp_path, browser, flow
):
    vague = [
        call("type", element_id=NAME, text="Ada"),
        call("finish", summary="FAILED: it didn't work"),
    ]
    start_run(sessions, workspace, site_url, settings, tmp_path, browser, vague)
    with sessions() as session:
        assert session.get(Flow, flow.id).script is None


def test_without_flows_a_run_explores_as_before(
    sessions, workspace, site_url, settings, tmp_path, browser
):
    with sessions() as session:
        session.add(Target(workspace_id=workspace.id, origin=site_url))
        session.commit()
    run_id, llm = start_run(
        sessions, workspace, site_url, settings, tmp_path, browser, [call("finish", summary="done")]
    )
    with sessions() as session:
        assert session.query(FlowResult).filter_by(run_id=run_id).count() == 0
    assert "CRITICAL FLOW" not in llm.calls[0]["observation"]
