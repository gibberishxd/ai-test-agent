"""Deep mode's columns (run 9): which engine a run uses, its coverage, pausing, unverified bugs,
and the workspace's deep-mode limits. The database enforces what it can on its own."""

import pytest
from sqlalchemy.exc import IntegrityError

from worker.db.models import Bug, Run, Workspace


def workspace(session, **fields) -> Workspace:
    ws = Workspace(name="Deep", slug="deep", **fields)
    session.add(ws)
    session.flush()
    return ws


def test_a_run_uses_the_current_loop_unless_it_asks_for_deep(sessions):
    with sessions() as session:
        ws = workspace(session)
        run = Run(workspace_id=ws.id, target_url="http://localhost:5173", mode="interactive")
        session.add(run)
        session.commit()
        session.refresh(run)
        assert run.engine == "loop"
        assert run.engine_model is None
        assert run.coverage is None


def test_a_deep_run_stores_its_model_and_coverage(sessions):
    coverage = {"map": {"pages": ["/"]}, "plan": [], "progress": {}}
    with sessions() as session:
        ws = workspace(session)
        run = Run(
            workspace_id=ws.id,
            target_url="http://localhost:5173",
            mode="interactive",
            engine="deep",
            engine_model="claude-opus-5-5",
            coverage=coverage,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        assert (run.engine, run.engine_model, run.coverage) == ("deep", "claude-opus-5-5", coverage)


def test_only_a_deep_run_can_name_an_engine_model(sessions):
    with sessions() as session:
        ws = workspace(session)
        session.add(
            Run(workspace_id=ws.id, target_url="http://x.test", engine_model="claude-opus-5-5")
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_an_engine_model_is_a_pinned_id_not_an_alias(sessions):
    with sessions() as session:
        ws = workspace(session)
        session.add(
            Run(workspace_id=ws.id, target_url="http://x.test", engine="deep", engine_model="opus")
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_a_run_can_be_paused_with_a_reason(sessions):
    with sessions() as session:
        ws = workspace(session)
        run = Run(workspace_id=ws.id, target_url="http://x.test", engine="deep")
        session.add(run)
        session.commit()
        run.status, run.paused_reason = "paused", "usage limit"
        session.commit()
        session.refresh(run)
        assert (run.status, run.paused_reason) == ("paused", "usage limit")


def test_a_bug_can_be_kept_as_unverified(sessions):
    with sessions() as session:
        ws = workspace(session)
        run = Run(workspace_id=ws.id, target_url="http://x.test", engine="deep")
        session.add(run)
        session.flush()
        bug = Bug(
            run_id=run.id,
            title="t",
            severity="low",
            category="other",
            page_url="http://x.test/",
            source="agent",
            status="unverified",
        )
        session.add(bug)
        session.commit()
        session.refresh(bug)
        assert bug.status == "unverified"


def test_workspace_deep_limits_default_to_the_product_defaults(sessions):
    with sessions() as session:
        ws = workspace(session)
        session.commit()
        session.refresh(ws)
        assert (ws.deep_max_steps, ws.deep_max_seconds) == (None, None)


@pytest.mark.parametrize("field", ["deep_max_steps", "deep_max_seconds"])
def test_workspace_deep_limits_must_be_positive(sessions, field):
    with sessions() as session:
        with pytest.raises(IntegrityError):
            workspace(session, **{field: 0})
