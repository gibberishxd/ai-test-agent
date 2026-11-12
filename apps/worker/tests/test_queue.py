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


def test_stale_running_runs_are_failed(sessions, workspace):
    from datetime import UTC, datetime, timedelta

    from worker.queue import recover_stale_runs

    stale = add_run(sessions, workspace)
    fresh = add_run(sessions, workspace)
    with sessions() as session:
        for run_id, age in ((stale.id, 3600), (fresh.id, 10)):
            run = session.get(Run, run_id)
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now(UTC) - timedelta(seconds=age)
        session.commit()
        assert recover_stale_runs(session, older_than_s=600) == 1

    assert load(sessions, stale.id).status == RunStatus.FAILED
    assert "worker stopped" in load(sessions, stale.id).error
    assert load(sessions, fresh.id).status == RunStatus.RUNNING


def test_only_verified_domains_count(sessions, workspace):
    from datetime import UTC, datetime

    from worker.db.models import Domain, Workspace
    from worker.execute import is_verified_domain

    with sessions() as session:
        other = Workspace(name="Other", slug="other")
        session.add(other)
        session.flush()
        session.add_all(
            [
                Domain(
                    workspace_id=workspace.id, hostname="shop.test", verified_at=datetime.now(UTC)
                ),
                Domain(workspace_id=workspace.id, hostname="pending.test"),
                Domain(
                    workspace_id=other.id, hostname="theirs.test", verified_at=datetime.now(UTC)
                ),
            ]
        )
        session.commit()
        assert is_verified_domain(session, workspace.id, "https://SHOP.test/cart")
        assert not is_verified_domain(session, workspace.id, "https://pending.test/")
        assert not is_verified_domain(session, workspace.id, "https://theirs.test/")  # not ours


# --- run 4: a starting worker and a benchmark must not take or fail each other's runs --------
# A FakeClient worker started by the e2e tests failed a 16-minute benchmark run that was alive
# (it only looked at the start time) and then ran the rest of the benchmark with the fake model.


def test_a_run_whose_worker_still_heartbeats_is_never_failed_as_stale(sessions, workspace):
    from datetime import UTC, datetime, timedelta

    from worker.queue import recover_stale_runs

    with sessions() as session:
        alive = Run(
            workspace_id=workspace.id,
            target_url="http://x/",
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC) - timedelta(minutes=30),
            heartbeat_at=datetime.now(UTC),
        )
        session.add(alive)
        session.commit()
        assert recover_stale_runs(session, older_than_s=600) == 0
        session.refresh(alive)
        assert alive.status == RunStatus.RUNNING


def test_a_benchmark_claims_only_its_own_runs(sessions, workspace):
    with sessions() as session:
        theirs = Run(workspace_id=workspace.id, target_url="http://customer/")
        ours = Run(workspace_id=workspace.id, target_url="http://bench/")
        session.add_all([theirs, ours])
        session.commit()
        ours_id, theirs_id = ours.id, theirs.id
        claimed = claim_next_run(session, "bench", only=[ours_id])
        assert claimed.id == ours_id
        assert claim_next_run(session, "bench", only=[ours_id]) is None
        assert session.get(Run, theirs_id).status == RunStatus.QUEUED


def test_regular_workers_leave_benchmark_runs_to_the_benchmark(sessions, workspace):
    from worker.benchmark import benchmark_workspace

    with sessions() as session:
        bench = benchmark_workspace(session)
        session.add(Run(workspace_id=bench.id, target_url="http://bench/"))
        session.commit()
        assert claim_next_run(session, "worker-2", skip_benchmark=True) is None
        session.add(Run(workspace_id=workspace.id, target_url="http://customer/"))
        session.commit()
        assert (
            claim_next_run(session, "worker-2", skip_benchmark=True).target_url
            == "http://customer/"
        )


def test_a_claimed_run_is_processed_inside_its_own_workspace(sessions, workspace):
    """Run 5, K3: the worker sees only the run's workspace while it works on it (row-level
    security as app_tenant), so a bug in run code can't touch another workspace's rows."""
    from sqlalchemy import text

    from worker.db.models import Workspace

    with sessions() as session:
        other = Workspace(name="Other", slug="other")
        session.add(other)
        session.flush()
        session.add(Run(workspace_id=other.id, target_url="http://x", status="done"))
        session.commit()
    run = add_run(sessions, workspace)
    seen = {}

    def execute(session, claimed, llm):
        row = session.execute(
            text("SELECT current_user AS who, current_setting('app.workspace_id', true) AS ws")
        ).one()
        seen["who"], seen["ws"] = row.who, row.ws
        seen["workspaces"] = session.execute(text("SELECT count(*) FROM workspaces")).scalar()
        seen["runs"] = session.execute(text("SELECT count(*) FROM runs")).scalar()

    process_next(sessions, FakeClient(), execute)
    assert seen == {"who": "app_tenant", "ws": str(workspace.id), "workspaces": 1, "runs": 1}
    assert load(sessions, run.id).status == RunStatus.DONE


def test_the_worker_role_claims_and_finishes_a_run(worker_sessions, sessions, workspace):
    """End to end as ata_worker: claim (a database function), work inside the workspace."""
    run = add_run(sessions, workspace)
    assert process_next(worker_sessions, FakeClient()) is True
    assert load(sessions, run.id).status == RunStatus.DONE
