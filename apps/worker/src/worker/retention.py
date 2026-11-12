"""Retention (run 4, J6): delete what a workspace no longer wants to keep.

For each finished run older than its workspace's `retention_days`: delete its screenshots from
storage and its step timeline from the database, clear the findings' screenshot references, and
mark the run purged. The run and its findings stay: comparing releases needs their fingerprints,
and they are small. Rate-limit windows older than an hour are deleted too.
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from worker.storage import Storage

BATCH = 200


def apply_retention(
    session: Session, storage: Storage, now: datetime | None = None
) -> dict[str, int]:
    """Purge expired runs in the database (the apply_retention function, run 5), then delete
    their screenshots from storage. Returns how many runs and files were purged.

    The database part is one transaction per batch; if the worker dies before deleting the
    files, the runs are already marked purged and their files are orphans under `<run id>/`,
    which a later sweep of storage can remove: no data the workspace wanted is lost.
    """
    now = now or datetime.now(UTC)
    purged = (
        session.execute(
            text("SELECT run_id FROM apply_retention(:now, :batch)"), {"now": now, "batch": BATCH}
        )
        .scalars()
        .all()
    )
    session.commit()
    files = sum(storage.delete_prefix(f"{run_id}/") for run_id in purged)
    return {"runs": len(purged), "files": files}
