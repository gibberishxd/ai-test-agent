"""Triage that follows a finding into later runs (run 4, J4).

A workspace member marks a finding confirmed, false positive or won't fix (web: lib/triage.ts);
the decision is stored per workspace, target origin and fingerprint. When a later run of that
target finishes, its findings whose fingerprint was triaged as a false positive are suppressed:
hidden from the report, the API, JUnit and webhooks, and counted, so the workspace (and we) learn
how often each model is wrong on real sites.
"""

from urllib.parse import urlsplit

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from worker.db.models import Bug, Run
from worker.fingerprint import fingerprint


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def suppressed_count(session: Session, run: Run) -> int:
    """How many of the run's findings are suppressed: the workspace marked their fingerprint a
    false positive on this target earlier. The database does the suppressing when a finding is
    stored (trigger bugs_carry_triage, run 5); this only counts for the run's summary."""
    session.flush()
    return session.scalar(
        select(func.count()).select_from(Bug).where(Bug.run_id == run.id, Bug.suppressed)
    )


def backfill_fingerprints(session: Session, batch: int = 500) -> int:
    """Give findings stored before fingerprints existed their fingerprint. Idempotent.

    Writes with explicit UPDATEs and reads with populate_existing: the session keeps objects
    after a commit, and a stale object would make "set the same value" a no-op forever."""
    done, seen = 0, set()
    while True:
        bugs = session.scalars(
            select(Bug)
            .where(Bug.fingerprint.is_(None), Bug.id.not_in(seen) if seen else True)
            .limit(batch)
            .execution_options(populate_existing=True)
        ).all()
        if not bugs:
            return done
        for bug in bugs:
            seen.add(bug.id)
            session.execute(
                update(Bug).where(Bug.id == bug.id).values(fingerprint=fingerprint(bug))
            )
        session.commit()
        done += len(bugs)
