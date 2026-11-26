"""Deep mode in the export, the local CLI and the benchmark (run 9): which engine ran, what it
covered, how each finding was verified, and unverified findings listed apart."""

import pytest

from worker.benchmark import queue_runs, stop_reason
from worker.db.models import Bug, Run, Workspace
from worker.export import export_run, verification_of
from worker.local_run import queue_local_run


def workspace(session) -> Workspace:
    ws = Workspace(name="w", slug="w")
    session.add(ws)
    session.flush()
    return ws


def test_a_deep_run_exports_engine_coverage_and_unverified_apart(sessions):
    with sessions() as session:
        ws = workspace(session)
        run = Run(
            workspace_id=ws.id,
            target_url="http://x.test/",
            mode="interactive",
            engine="deep",
            coverage={"phase": "done", "plan": [{"id": "a"}]},
        )
        session.add(run)
        session.flush()
        base = {
            "run_id": run.id,
            "severity": "low",
            "category": "functional",
            "page_url": "http://x.test/",
            "source": "agent",
        }
        session.add(
            Bug(
                title="Measured",
                status="confirmed",
                evidence={"engine": "deep", "verification": {"kind": "measure"}},
                **base,
            )
        )
        session.add(
            Bug(
                title="Replayed",
                status="confirmed",
                evidence={"engine": "deep", "replay": "seen", "verification": {"kind": "replay"}},
                **base,
            )
        )
        session.add(
            Bug(
                title="Nobody could check",
                status="unverified",
                evidence={"engine": "deep", "verification": {"kind": "replay"}},
                **base,
            )
        )
        session.commit()
        data = export_run(session, str(run.id))
    assert data["engine"] == "deep" and data["coverage"]["phase"] == "done"
    verified = {f["title"]: f["verification"] for f in data["findings"]}
    assert verified == {"Measured": "measurement", "Replayed": "replay"}
    assert [f["title"] for f in data["unverified_findings"]] == ["Nobody could check"]
    assert data["unverified_findings"][0]["verification"] == "none"


def test_a_loop_run_exports_as_before(sessions):
    with sessions() as session:
        ws = workspace(session)
        run = Run(workspace_id=ws.id, target_url="http://x.test/", mode="interactive")
        session.add(run)
        session.commit()
        data = export_run(session, str(run.id))
    assert data["engine"] == "loop" and data["unverified_findings"] == []


@pytest.mark.parametrize(
    "status, source, evidence, expected",
    [
        ("confirmed", "deterministic", {}, "deterministic"),
        ("confirmed", "agent", {"replay": "seen"}, "replay"),
        ("dismissed", "agent", {"verification": {"kind": "check"}}, "measurement"),
        ("unverified", "agent", {"verification": {"kind": "measure"}}, "none"),
        ("candidate", "agent", {}, "none"),
    ],
)
def test_verification_of(status, source, evidence, expected):
    assert verification_of(status, source, evidence) == expected


def test_a_local_deep_run_is_queued_with_its_model(sessions):
    with sessions() as session:
        run_id = queue_local_run(
            session, "http://localhost:4000/", "390x844", "deep", "claude-opus-5-5"
        )
        run = session.get(Run, run_id)
        assert (run.engine, run.engine_model, run.mode) == (
            "deep",
            "claude-opus-5-5",
            "interactive",
        )


def test_the_benchmark_queues_deep_runs_as_interactive(sessions):
    with sessions() as session:
        ws = workspace(session)
        ids = queue_runs(session, ws.id, ["http://shop.test/"], "passive", engine="deep")
        run = session.get(Run, ids[0])
        assert (run.engine, run.mode) == ("deep", "interactive")


def test_a_paused_run_stops_the_benchmark(sessions):
    with sessions() as session:
        ws = workspace(session)
        run = Run(
            workspace_id=ws.id,
            target_url="http://shop.test/",
            engine="deep",
            status="paused",
            paused_reason="usage limit reached (five_hour)",
        )
        session.add(run)
        session.commit()
        reason = stop_reason(session, [str(run.id)], cap_usd=0)
    assert reason and "paused" in reason and "five_hour" in reason


def test_an_unverified_finding_never_counts_as_verified_in_the_benchmark(sessions):
    from types import SimpleNamespace

    from worker.benchmark import report_bugs, stage_of

    unverified = SimpleNamespace(
        duplicate_of_id=None, status="unverified", dismiss_reason=None, evidence={}
    )
    assert stage_of(unverified) == ("unverified", None)
    with sessions() as session:
        ws = workspace(session)
        run = Run(workspace_id=ws.id, target_url="http://shop.test/", engine="deep")
        session.add(run)
        session.flush()
        for status in ("confirmed", "unverified"):
            session.add(
                Bug(
                    run_id=run.id,
                    title=status,
                    severity="low",
                    category="x",
                    page_url="http://shop.test/",
                    source="agent",
                    status=status,
                )
            )
        session.commit()
        assert [b.title for b in report_bugs(session, str(run.id))] == ["confirmed"]
