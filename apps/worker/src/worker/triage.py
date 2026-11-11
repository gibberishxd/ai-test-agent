"""Triage that follows a finding into later runs (run 4, J4).

A workspace member marks a finding confirmed, false positive or won't fix (web: lib/triage.ts);
the decision is stored per workspace, target origin and fingerprint. When a later run of that
target finishes, its findings whose fingerprint was triaged as a false positive are suppressed:
hidden from the report, the API, JUnit and webhooks, and counted, so the workspace (and we) learn
how often each model is wrong on real sites.
"""

from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from worker.db.models import Bug, FindingTriage, Run
from worker.fingerprint import fingerprint


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def apply_triage(session: Session, run: Run) -> int:
    """Suppress the run's findings the workspace triaged as false positives; returns how many."""
    false_positives = select(FindingTriage.fingerprint).where(
        FindingTriage.workspace_id == run.workspace_id,
        FindingTriage.origin == origin_of(run.target_url),
        FindingTriage.state == "false_positive",
    )
    result = session.execute(
        update(Bug)
        .where(Bug.run_id == run.id, Bug.fingerprint.in_(false_positives))
        .values(suppressed=True)
    )
    session.commit()
    return result.rowcount


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
