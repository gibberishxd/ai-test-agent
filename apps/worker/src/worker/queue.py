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
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from worker.db.models import Run, RunStatus
from worker.db.tenant import enter_tenant, leave_tenant

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
    """Fail runs stuck in "running" whose worker hasn't shown a sign of life for `older_than_s`.

    If a worker process dies mid-run (crash, deploy, laptop closed), its run would stay
    "running" forever. Called when a worker starts. The rule lives in Postgres
    (recover_runs, run 5): a run whose worker still heartbeats is alive, however old it is.
    """
    return recover_expired_leases(session, older_than_s)


def claim_next_run(
    session: Session,
    worker_id: str,
    only: list | None = None,
    skip_benchmark: bool = False,
) -> Run | None:
    """Claim the oldest queued run, or return None if there is nothing to do.

    The claim is the database function claim_next_run (run 5): SELECT ... FOR UPDATE SKIP
    LOCKED, the status change and the lease in one statement, committed at once. It is the
    one place that looks across workspaces, so it runs as the schema owner and returns only
    the run's id; everything after that happens inside the run's own workspace.

    - `only`: claim only these runs (a benchmark processes exactly the runs it queued, with its
      own model, and never a customer's).
    - `skip_benchmark`: a regular worker leaves the benchmark workspace's runs alone, so a
      worker started with another model can't run part of someone's benchmark.
    """
    ids = [str(run_id) for run_id in only] if only is not None else None
    leave_tenant(session)  # a claim looks across workspaces: not as the last run's tenant
    session.commit()
    row = session.execute(
        text("SELECT id, workspace_id FROM claim_next_run(:worker, :only, :skip)"),
        {"worker": worker_id, "only": ids, "skip": skip_benchmark},
    ).first()
    session.commit()
    if row is None:
        return None
    enter_tenant(session, row.workspace_id)  # the session sees only this run's workspace now
    return session.get(Run, row.id, populate_existing=True)


LEASE_ERROR = "the worker stopped responding (no heartbeat for {lease} s)"
log = logging.getLogger(__name__)


def recover_expired_leases(session: Session, lease_s: float) -> int:
    """Fail running runs whose worker hasn't renewed the lease for `lease_s` seconds.

    The database function recover_runs does it in one UPDATE: if two workers recover at once,
    Postgres runs the updates one after the other, and the second finds the row no longer
    "running". Runs from before leases existed fall back to started_at.
    """
    failed = session.execute(text("SELECT recover_runs(:lease)"), {"lease": round(lease_s)})
    count = failed.scalar() or 0
    session.commit()
    return count


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
                    session.execute(text("SELECT renew_lease(:run)"), {"run": self._run_id})
                    session.commit()
            except Exception:  # a missed beat is fine; the lease is several beats long
                log.warning("heartbeat for run %s failed", self._run_id, exc_info=True)
