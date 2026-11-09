import pytest

from worker.db.models import Run, RunStatus
from worker.llm import FakeClient
from worker.queue import InvalidTransition, claim_next_run, transition
from worker.runner import process_next


def add_run(sessions, workspace, **fields) -> Run:
    with sessions() as session:
        run = Run(workspace_id=workspace.id, target_url="http://localhost:5173", **fields)
        session.add(run)
        session.commit()
        return run


def load(sessions, run_id) -> Run:
    with sessions() as session:
        return session.get(Run, run_id)


def test_claim_returns_none_on_empty_queue(sessions):
    with sessions() as session:
        assert claim_next_run(session, "w1") is None


def test_claim_marks_the_run_running(sessions, workspace):
    run = add_run(sessions, workspace)
    with sessions() as session:
        claimed = claim_next_run(session, "w1")
    assert claimed.id == run.id
    stored = load(sessions, run.id)
    assert stored.status == RunStatus.RUNNING
    assert stored.claimed_by == "w1"
    assert stored.started_at is not None


def test_two_workers_never_get_the_same_run(sessions, workspace):
    first = add_run(sessions, workspace)
    second = add_run(sessions, workspace)
    with sessions() as a, sessions() as b:
        # Worker A locks the oldest run but hasn't committed yet...
        from sqlalchemy import select

        locked = a.scalars(
            select(Run).where(Run.id == first.id).with_for_update(skip_locked=True)
        ).one()
        # ...so worker B skips it instead of waiting, and takes the next one.
        claimed = claim_next_run(b, "worker-b")
        assert claimed.id == second.id
        assert locked.id == first.id
        a.rollback()


def test_illegal_transition_is_refused(sessions, workspace):
    run = add_run(sessions, workspace)
    with sessions() as session:
        run = session.get(Run, run.id)
        with pytest.raises(InvalidTransition):
            transition(run, RunStatus.DONE)  # queued → done skips "running"


def test_process_next_runs_a_queued_run_to_done(sessions, workspace):
    run = add_run(sessions, workspace)
    assert process_next(sessions, FakeClient()) is True
    stored = load(sessions, run.id)
    assert stored.status == RunStatus.DONE
    assert stored.provider == "fake"
    assert stored.finished_at is not None


def test_process_next_marks_failures_with_the_error(sessions, workspace):
    run = add_run(sessions, workspace)

    def explode(session, run, llm):
        raise RuntimeError("browser crashed")

    process_next(sessions, FakeClient(), execute=explode)
    stored = load(sessions, run.id)
    assert stored.status == RunStatus.FAILED
    assert stored.error == "RuntimeError: browser crashed"


def test_stop_requested_ends_as_stopped(sessions, workspace):
    run = add_run(sessions, workspace, stop_requested=True)
    process_next(sessions, FakeClient())
    assert load(sessions, run.id).status == RunStatus.STOPPED


def test_process_next_returns_false_when_queue_is_empty(sessions):
    assert process_next(sessions, FakeClient()) is False
