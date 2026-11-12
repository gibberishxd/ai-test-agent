"""Retention (run 4, J6): a workspace keeps screenshots and step timelines for its retention period;
older runs lose them but keep their findings (history across releases needs the fingerprints)."""

from datetime import UTC, datetime, timedelta

from worker.db.models import ApiKey, ApiRateWindow, Bug, Run, Step, Workspace
from worker.retention import apply_retention
from worker.storage import LocalStorage

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def add_run(session, workspace, finished_days_ago, status="done") -> Run:
    finished = NOW - timedelta(days=finished_days_ago)
    run = Run(
        workspace_id=workspace.id,
        target_url="https://x.test/",
        mode="passive",
        status=status,
        started_at=finished,
        finished_at=finished,
    )
    session.add(run)
    session.commit()
    session.add(
        Step(
            run_id=run.id,
            index=0,
            action="visit",
            args={},
            url=run.target_url,
            screenshot=f"{run.id}/page-001.png",
        )
    )
    session.add(
        Bug(
            run_id=run.id,
            title="404",
            severity="low",
            category="broken-link",
            page_url=run.target_url,
            source="deterministic",
            screenshot=f"{run.id}/page-001.png",
        )
    )
    session.commit()
    return run


def test_old_runs_lose_screenshots_and_steps_but_keep_findings(sessions, tmp_path):
    storage = LocalStorage(tmp_path)
    with sessions() as session:
        short = Workspace(name="Short", slug="short", retention_days=7)
        session.add(short)
        session.commit()
        old = add_run(session, short, finished_days_ago=8)
        recent = add_run(session, short, finished_days_ago=6)
        for run in (old, recent):
            storage.save(f"{run.id}/page-001.png", b"png")

        # The database purges (apply_retention, run 5); the worker deletes the files.
        assert apply_retention(session, storage, now=NOW) == {"runs": 1, "files": 1}
        session.refresh(old)
        assert old.purged_at is not None
        assert session.query(Step).filter_by(run_id=old.id).count() == 0
        bug = session.query(Bug).filter_by(run_id=old.id).one()
        assert bug.screenshot is None and bug.fingerprint  # the finding itself stays
        assert session.query(Step).filter_by(run_id=recent.id).count() == 1
        assert storage.load(f"{recent.id}/page-001.png") == b"png"
        assert apply_retention(session, storage, now=NOW)["runs"] == 0  # done once


def test_running_runs_and_old_rate_windows(sessions, workspace, tmp_path):
    with sessions() as session:
        add_run(session, workspace, finished_days_ago=90, status="running")
        key = ApiKey(workspace_id=workspace.id, name="CI", prefix="ata_x", key_hash="h")
        session.add(key)
        session.commit()
        session.add_all(
            [
                ApiRateWindow(api_key_id=key.id, window_start=NOW - timedelta(hours=2), count=5),
                ApiRateWindow(api_key_id=key.id, window_start=NOW - timedelta(minutes=1), count=5),
            ]
        )
        session.commit()
        result = apply_retention(session, LocalStorage(tmp_path), now=NOW)
        assert result["runs"] == 0
        assert session.query(ApiRateWindow).count() == 1  # the old window is gone
