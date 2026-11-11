"""Retention (run 4, J6): delete what a workspace no longer wants to keep.

For each finished run older than its workspace's `retention_days`: delete its screenshots from
storage and its step timeline from the database, clear the findings' screenshot references, and
mark the run purged. The run and its findings stay: comparing releases needs their fingerprints,
and they are small. Rate-limit windows older than an hour are deleted too.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from worker.db.models import ApiRateWindow, Bug, Run, RunStatus, Step, Workspace
from worker.storage import Storage

FINAL = (RunStatus.DONE, RunStatus.FAILED, RunStatus.STOPPED)
BATCH = 200


def apply_retention(
    session: Session, storage: Storage, now: datetime | None = None
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    expired = session.scalars(
        select(Run)
        .join(Workspace, Workspace.id == Run.workspace_id)
        .where(
            Run.status.in_(FINAL),
            Run.purged_at.is_(None),
            Run.finished_at < now - func.make_interval(0, 0, 0, Workspace.retention_days),
        )
        .limit(BATCH)
    ).all()
    counts = {"runs": 0, "files": 0, "steps": 0, "rate_windows": 0}
    for run in expired:
        counts["files"] += storage.delete_prefix(f"{run.id}/")
        counts["steps"] += session.execute(delete(Step).where(Step.run_id == run.id)).rowcount
        session.execute(update(Bug).where(Bug.run_id == run.id).values(screenshot=None))
        run.purged_at = now
        counts["runs"] += 1
        session.commit()  # one run at a time: a crash halfway loses nothing
    counts["rate_windows"] = session.execute(
        delete(ApiRateWindow).where(ApiRateWindow.window_start < now - timedelta(hours=1))
    ).rowcount
    session.commit()
    return counts
