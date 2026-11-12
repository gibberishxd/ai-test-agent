"""The run queue under load and after crashes, against the real test database.

1. Many workers claiming at once: every run is claimed exactly once (no run lost, none twice).
2. A worker that dies mid-run: its run doesn't stay "running" forever. Workers renew a lease
   (heartbeat_at) while they work; any live worker fails runs whose lease has expired.
"""

import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from worker.db.models import Run, RunStatus
from worker.llm import FakeClient
from worker.queue import Heartbeat, claim_next_run, recover_expired_leases
from worker.runner import process_next

WORKERS = 8
RUNS = 300


def queue_runs(sessions, workspace, count: int) -> set:
    with sessions() as session:
        runs = [
            Run(workspace_id=workspace.id, target_url=f"http://localhost:5173/{i}")
            for i in range(count)
        ]
        session.add_all(runs)
        session.commit()
        return {run.id for run in runs}


def test_many_workers_claim_every_run_exactly_once(sessions, workspace):
    queued = queue_runs(sessions, workspace, RUNS)
    claims: dict[str, list] = {f"w{n}": [] for n in range(WORKERS)}
    start = threading.Barrier(WORKERS)  # all workers hit the queue at the same moment

    def worker(name: str) -> None:
        start.wait()
        while True:
            with sessions() as session:  # one connection and transaction per claim
                run = claim_next_run(session, name)
                if run is None:
                    return
                claims[name].append(run.id)

    threads = [threading.Thread(target=worker, args=(name,)) for name in claims]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    claimed = [run_id for ids in claims.values() for run_id in ids]
    assert len(claimed) == len(set(claimed)), "a run was claimed twice"
    assert set(claimed) == queued, "a run was never claimed"
    assert sum(1 for ids in claims.values() if ids) > 1, "the work wasn't shared at all"
    with sessions() as session:
        stored = session.query(Run).filter(Run.id.in_(queued)).all()
        assert {run.status for run in stored} == {RunStatus.RUNNING}
        # Each run records the one worker that claimed it.
        owner = {run_id: name for name, ids in claims.items() for run_id in ids}
        assert all(run.claimed_by == owner[run.id] for run in stored)


def claim(sessions, workspace) -> Run:
    queue_runs(sessions, workspace, 1)
    with sessions() as session:
        return claim_next_run(session, "crashed-worker")


def age_lease(sessions, run_id, seconds: int) -> None:
    with sessions() as session:
        old = datetime.now(UTC) - timedelta(seconds=seconds)
        session.execute(update(Run).where(Run.id == run_id).values(heartbeat_at=old))
        session.commit()


def test_claiming_a_run_starts_its_lease(sessions, workspace):
    run = claim(sessions, workspace)
    with sessions() as session:
        assert session.get(Run, run.id).heartbeat_at is not None


def test_a_run_whose_lease_expired_is_failed_by_any_live_worker(sessions, workspace):
    run = claim(sessions, workspace)
    age_lease(sessions, run.id, 120)  # the worker died two minutes ago

    with sessions() as session:
        assert recover_expired_leases(session, lease_s=60) == 1
        stored = session.get(Run, run.id)
        assert stored.status == RunStatus.FAILED
        assert "no heartbeat" in stored.error
        assert stored.finished_at is not None


def test_a_long_run_with_a_fresh_heartbeat_is_left_alone(sessions, workspace):
    run = claim(sessions, workspace)
    with sessions() as session:  # started an hour ago, but its worker is alive
        hour_ago = datetime.now(UTC) - timedelta(hours=1)
        session.execute(update(Run).where(Run.id == run.id).values(started_at=hour_ago))
        session.commit()

    with sessions() as session:
        assert recover_expired_leases(session, lease_s=60) == 0
        assert session.get(Run, run.id).status == RunStatus.RUNNING


def test_heartbeat_renews_the_lease_while_the_work_runs(sessions, workspace):
    run = claim(sessions, workspace)
    age_lease(sessions, run.id, 120)

    with Heartbeat(sessions, run.id, interval_s=0.05):
        threading.Event().wait(0.3)

    with sessions() as session:
        renewed = session.get(Run, run.id).heartbeat_at
    assert renewed > datetime.now(UTC) - timedelta(seconds=5)


def test_a_worker_that_comes_back_late_does_not_undo_the_recovery(sessions, workspace):
    # The worker was only frozen (laptop asleep), not dead: when it wakes up and finishes, the
    # run must stay failed, not jump back to done.
    queue_runs(sessions, workspace, 1)

    def frozen_then_finishes(session, run, llm):
        age_lease(sessions, run.id, 120)
        with sessions() as other:
            recover_expired_leases(other, lease_s=60)

    assert process_next(sessions, FakeClient(), frozen_then_finishes)
    with sessions() as session:
        [run] = session.query(Run).filter(Run.claimed_by.isnot(None)).all()
        assert run.status == RunStatus.FAILED
