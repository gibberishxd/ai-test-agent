"""The run queue: Postgres is the queue, no Redis.

The web app inserts a row into `runs` with status "queued". Workers claim one with
SELECT ... FOR UPDATE SKIP LOCKED:
- FOR UPDATE locks the chosen row until the transaction ends;
- SKIP LOCKED makes other workers skip rows that are locked instead of waiting for them.
So two workers polling at the same moment always get different runs, and none blocks.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from worker.db.models import Run, RunStatus

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


def claim_next_run(session: Session, worker_id: str) -> Run | None:
    """Claim the oldest queued run, or return None if there is nothing to do.

    The status change is committed immediately: after that the row is no longer "queued", so
    no other worker can pick it up, and the lock can be released.
    """
    stmt = (
        select(Run)
        .where(Run.status == RunStatus.QUEUED)
        .order_by(Run.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    run = session.scalars(stmt).first()
    if run is None:
        session.rollback()
        return None
    transition(run, RunStatus.RUNNING)
    run.claimed_by = worker_id
    session.commit()
    return run
