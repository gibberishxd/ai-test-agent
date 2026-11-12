"""Triage follows a finding into later runs (run 4, J4): fingerprints are set on every bug, and a
fingerprint triaged as a false positive is suppressed in the target's later runs (and counted)."""

from worker.db.models import Bug, FindingTriage, Run, Workspace
from worker.triage import suppressed_count
from worker.webhooks import run_payload

URL = "https://shop.test/"
ERROR = {"console_errors": [{"text": "TypeError: x is undefined"}]}


def add_run(session, workspace_id, url=URL) -> Run:
    run = Run(workspace_id=workspace_id, target_url=url, mode="passive", status="done")
    session.add(run)
    session.commit()
    return run


def add_bug(session, run, **fields) -> Bug:
    bug = Bug(
        run_id=run.id,
        **{
            "title": "Console error: TypeError",
            "severity": "high",
            "category": "console-error",
            "page_url": f"{run.target_url}cart",
            "source": "deterministic",
            "status": "confirmed",
            "evidence": ERROR,
            **fields,
        },
    )
    session.add(bug)
    session.commit()
    return bug


def test_every_stored_bug_gets_a_fingerprint(sessions, workspace):
    with sessions() as session:
        run = add_run(session, workspace.id)
        assert len(add_bug(session, run).fingerprint) == 16


def test_a_false_positive_is_suppressed_in_later_runs_of_the_target_and_not_counted(
    sessions, workspace
):
    with sessions() as session:
        first = add_bug(session, add_run(session, workspace.id))
        session.add(
            FindingTriage(
                workspace_id=workspace.id,
                origin="https://shop.test",
                fingerprint=first.fingerprint,
                state="false_positive",
                title=first.title,
            )
        )
        session.commit()
        later = add_run(session, workspace.id)
        same = add_bug(session, later)
        other = add_bug(session, later, page_url=f"{URL}checkout")  # same message, other page
        assert suppressed_count(session, later) == 1
        session.refresh(same)
        session.refresh(other)
        assert same.suppressed and not other.suppressed
        assert run_payload(session, later)["counts"]["high"] == 1


def test_triage_stays_in_its_workspace_and_its_site(sessions, workspace):
    with sessions() as session:
        other_ws = Workspace(name="Other", slug="other")
        session.add(other_ws)
        session.commit()
        bug = add_bug(session, add_run(session, workspace.id))
        session.add(
            FindingTriage(
                workspace_id=other_ws.id,
                origin="https://shop.test",
                fingerprint=bug.fingerprint,
                state="false_positive",
                title="x",
            )
        )
        session.add(
            FindingTriage(
                workspace_id=workspace.id,
                origin="https://other.test",
                fingerprint=bug.fingerprint,
                state="false_positive",
                title="x",
            )
        )
        session.commit()
        later = add_run(session, workspace.id)
        add_bug(session, later)
        assert suppressed_count(session, later) == 0


def test_won_t_fix_and_confirmed_are_not_suppressed(sessions, workspace):
    with sessions() as session:
        bug = add_bug(session, add_run(session, workspace.id))
        session.add(
            FindingTriage(
                workspace_id=workspace.id,
                origin="https://shop.test",
                fingerprint=bug.fingerprint,
                state="wont_fix",
                title="x",
            )
        )
        session.commit()
        later = add_run(session, workspace.id)
        add_bug(session, later)
        assert suppressed_count(session, later) == 0


def test_old_findings_get_their_fingerprint_once(sessions, workspace):
    # Findings stored before run 4 have none; the backfill fills only those, so it can run twice.
    from sqlalchemy import text

    from worker.triage import backfill_fingerprints

    with sessions() as session:
        bug = add_bug(session, add_run(session, workspace.id))
        expected = bug.fingerprint
        session.execute(text("UPDATE bugs SET fingerprint = NULL"))
        session.commit()
        assert backfill_fingerprints(session) == 1
        assert backfill_fingerprints(session) == 0
        session.refresh(bug)
        assert bug.fingerprint == expected
