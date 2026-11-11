"""The run queue: Postgres is the queue, no Redis.

The web app inserts a row into `runs` with status "queued". Workers claim one with
SELECT ... FOR UPDATE SKIP LOCKED:
- FOR UPDATE locks the chosen row until the transaction ends;
- SKIP LOCKED makes other workers skip rows that are locked instead of waiting for them.
So two workers polling at the same moment always get different runs, and none blocks.

A claimed run is leased: its worker renews `heartbeat_at` every few seconds (Heartbeat), and
any worker fails runs whose lease expired (recover_expired_leases): the worker died.
Lease times use the database's clock (now()), so workers with skewed clocks still agree.
"""

import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from worker.db.models import Run, RunStatus, Workspace

BENCHMARK_SLUG = "benchmark"  # the workspace the benchmark queues its runs in

# Which status changes are allowed. Anything else is a bug in the worker.
TRANSITIONS: dict[str, set[str]] = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.STOPPED},
    RunStatus.RUNNING: {RunStatus.DONE, RunStatus.FAILED, RunStatus.STOPPED},
}
FINAL = {RunStatus.DONE, RunStatus.FAILED, RunStatus.STOPPED}


class InvalidTransition(Exception):
    pass


def transition(run: Run, new_status: RunStatus, error: str | None = None) -> None:
    """Move a run to `new_status`, refusing illegal moves (e.g. done → running)."""
    if new_status not in TRANSITIONS.get(run.status, set()):
        raise InvalidTransition(f"run {run.id}: {run.status} → {new_status} is not allowed")
    run.status = new_status
    now = datetime.now(UTC)
    if new_status == RunStatus.RUNNING:
        run.started_at = now
    if new_status in FINAL:
        run.finished_at = now
    if error is not None:
        run.error = error


def recover_stale_runs(session: Session, older_than_s: float) -> int:
    """Fail runs stuck in "running" for longer than any run may take.

    If a worker process dies mid-run (crash, deploy, laptop closed), its run would stay
    "running" forever. Called when a worker starts; returns how many runs were recovered.
    A run whose worker still heartbeats is alive, however old it is: a run's time limit is its
    own worker's setting, not the setting of the worker that is starting (run 4).
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=older_than_s)
    stale = session.scalars(
        select(Run).where(
            Run.status == RunStatus.RUNNING,
            Run.started_at < cutoff,
            func.coalesce(Run.heartbeat_at, Run.started_at) < cutoff,
        )
    ).all()
    for run in stale:
        transition(run, RunStatus.FAILED, error="the worker stopped before the run finished")
    session.commit()
    return len(stale)


def claim_next_run(
    session: Session,
    worker_id: str,
    only: list | None = None,
    skip_benchmark: bool = False,
) -> Run | None:
    """Claim the oldest queued run, or return None if there is nothing to do.

    The status change is committed immediately: after that the row is no longer "queued", so
    no other worker can pick it up, and the lock can be released.

    - `only`: claim only these runs (a benchmark processes exactly the runs it queued, with its
      own model, and never a customer's).
    - `skip_benchmark`: a regular worker leaves the benchmark workspace's runs alone, so a
      worker started with another model can't run part of someone's benchmark.
    """
    stmt = select(Run).where(Run.status == RunStatus.QUEUED)
    if only is not None:
        stmt = stmt.where(Run.id.in_(only))
    if skip_benchmark:
        benchmark = select(Workspace.id).where(Workspace.slug == BENCHMARK_SLUG)
        stmt = stmt.where(Run.workspace_id.not_in(benchmark.scalar_subquery()))
    stmt = stmt.order_by(Run.created_at).limit(1).with_for_update(skip_locked=True, of=Run)
    run = session.scalars(stmt).first()
    if run is None:
        session.rollback()
        return None
    transition(run, RunStatus.RUNNING)
    run.claimed_by = worker_id
    run.heartbeat_at = func.now()  # the lease starts with the claim
    session.commit()
    return run


LEASE_ERROR = "the worker stopped responding (no heartbeat for {lease} s)"
log = logging.getLogger(__name__)


def recover_expired_leases(session: Session, lease_s: float) -> int:
    """Fail running runs whose worker hasn't renewed the lease for `lease_s` seconds.

    One UPDATE with the condition in its WHERE: if two workers recover at once, Postgres runs
    the updates one after the other, and the second finds the row no longer "running".
    Runs from before leases existed fall back to started_at. Returns how many were failed.
    """
    lease = timedelta(seconds=lease_s)
    last_sign_of_life = func.coalesce(Run.heartbeat_at, Run.started_at)
    result = session.execute(
        update(Run)
        .where(Run.status == RunStatus.RUNNING, last_sign_of_life < func.now() - lease)
        .values(
            status=RunStatus.FAILED,
            finished_at=func.now(),
            error=LEASE_ERROR.format(lease=round(lease_s)),
        )
        .returning(Run.id)
    )
    failed = result.scalars().all()
    session.commit()
    return len(failed)


class Heartbeat:
    """Renews a run's lease from a background thread while the `with` block runs.

    The thread has its own database session (a session isn't thread-safe). It renews only
    while the run is still "running", so it can't revive a run another worker failed.
    """

    def __init__(self, sessions: sessionmaker[Session], run_id: uuid.UUID, interval_s: float):
        self._sessions, self._run_id, self._interval = sessions, run_id, interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._beat, name=f"heartbeat-{run_id}", daemon=True)

    def __enter__(self) -> "Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()

    def _beat(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                with self._sessions() as session:
                    session.execute(
                        update(Run)
                        .where(Run.id == self._run_id, Run.status == RunStatus.RUNNING)
                        .values(heartbeat_at=func.now())
                    )
                    session.commit()
            except Exception:  # a missed beat is fine; the lease is several beats long
                log.warning("heartbeat for run %s failed", self._run_id, exc_info=True)
