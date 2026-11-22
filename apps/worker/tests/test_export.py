"""Exporting a run's findings to a JSON file (worker export RUN_ID --out FILE)."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from worker.db.models import Bug, Run, Step
from worker.export import evidence_of, export_run, replay_verified, write_export

STARTED = datetime(2026, 11, 22, 10, 0, tzinfo=UTC)


@pytest.fixture
def run_id(sessions, workspace):
    with sessions() as session:
        run = Run(
            workspace_id=workspace.id,
            target_url="http://localhost:9999/",
            mode="interactive",
            status="done",
            provider="claude",
            model="claude-haiku-5-5",
            viewport="390x844",
            cost_usd=0.0412,
            estimated_cost_usd=0.0412,
            step_count=3,
            started_at=STARTED,
            finished_at=STARTED + timedelta(seconds=125.5),
        )
        session.add(run)
        session.flush()
        session.add_all(
            [
                Step(
                    run_id=run.id,
                    index=2,
                    action="click",
                    screenshot=f"{run.id}/agent-002-step-001.png",
                    # As the worker stores an agent step's events (execute._save_agent_step).
                    events=[
                        {"type": "event", "text": "console error: TypeError: x is undefined"},
                        {"type": "event", "text": "network: POST /api → 500"},
                    ],
                ),
                Step(
                    run_id=run.id,
                    index=3,
                    action="report_bug",
                    screenshot=f"{run.id}/agent-003-step-002.png",
                ),
                Bug(
                    run_id=run.id,
                    title="Submit does nothing",
                    severity="high",
                    category="functional",
                    page_url="http://localhost:9999/",
                    expected="A confirmation appears",
                    actual="Nothing happens",
                    repro_steps=["Open /", 'Click button "Submit"'],
                    evidence={"observed": "no change", "reported_at": 3, "replay": "reproduced"},
                    step_indexes=[2],
                    source="agent",
                    status="confirmed",
                ),
                Bug(
                    run_id=run.id,
                    title="Accessibility: Images must have alternate text",
                    severity="medium",
                    category="accessibility",
                    page_url="http://localhost:9999/",
                    evidence={"a11y": [{"rule_id": "image-alt", "targets": ["img"]}]},
                    screenshot=f"{run.id}/page-001.png",
                    source="deterministic",
                    status="confirmed",
                ),
                Bug(
                    run_id=run.id,
                    title="Price looks wrong",
                    severity="low",
                    category="functional",
                    page_url="http://localhost:9999/",
                    actual="Shows 0",
                    evidence={"replay": "the page showed the right price"},
                    source="agent",
                    status="dismissed",
                    dismiss_reason="replay: the page showed the right price",
                ),
            ]
        )
        session.commit()
        return str(run.id)


def test_export_has_the_runs_facts(sessions, run_id, tmp_path):
    with sessions() as session:
        data = export_run(session, run_id, data_dir=tmp_path)
    assert data["run_id"] == run_id
    assert data["model"] == "claude-haiku-5-5"
    assert data["provider"] == "claude"
    assert data["viewport"] == "390x844"
    assert data["cost_usd"] == pytest.approx(0.0412)
    assert data["duration_s"] == pytest.approx(125.5)
    assert data["target_url"] == "http://localhost:9999/"


def test_every_finding_is_exported_with_its_status(sessions, run_id, tmp_path):
    with sessions() as session:
        findings = export_run(session, run_id, data_dir=tmp_path)["findings"]
    assert [f["title"] for f in findings] == [
        "Submit does nothing",
        "Accessibility: Images must have alternate text",
        "Price looks wrong",
    ]
    agent = findings[0]
    assert agent["severity"] == "high"
    assert agent["steps"] == ["Open /", 'Click button "Submit"']
    assert "A confirmation appears" in agent["description"]
    assert "Nothing happens" in agent["description"]
    assert [f["status"] for f in findings] == ["confirmed", "confirmed", "dismissed"]


def test_replay_verified_only_for_reports_replay_confirmed(sessions, run_id, tmp_path):
    with sessions() as session:
        findings = export_run(session, run_id, data_dir=tmp_path)["findings"]
    # The agent's report was replayed and reproduced; the axe finding was never replayed (it has
    # hard evidence); the dismissed report was replayed and did not reproduce.
    assert [f["replay_verified"] for f in findings] == [True, False, False]


def test_agent_finding_evidence_comes_from_its_steps(sessions, run_id, tmp_path):
    with sessions() as session:
        agent = export_run(session, run_id, data_dir=tmp_path)["findings"][0]
    assert agent["evidence"]["console"] == ["console error: TypeError: x is undefined"]
    assert agent["evidence"]["network"] == ["network: POST /api → 500"]
    assert agent["evidence"]["accessibility"] == []


def test_deterministic_finding_keeps_its_axe_results(sessions, run_id, tmp_path):
    with sessions() as session:
        axe = export_run(session, run_id, data_dir=tmp_path)["findings"][1]
    assert axe["evidence"]["accessibility"] == [{"rule_id": "image-alt", "targets": ["img"]}]


def test_screenshot_paths_point_into_the_data_dir(sessions, run_id, tmp_path):
    with sessions() as session:
        findings = export_run(session, run_id, data_dir=tmp_path)["findings"]
    # The agent's report: the screenshot of the step it was reported at.
    assert findings[0]["screenshot"] == str(tmp_path / run_id / "agent-003-step-002.png")
    assert findings[1]["screenshot"] == str(tmp_path / run_id / "page-001.png")
    assert findings[2]["screenshot"] is None


def test_write_export_creates_the_file_and_its_folder(sessions, run_id, tmp_path):
    out = tmp_path / "results" / "run.json"
    with sessions() as session:
        write_export(session, run_id, out, data_dir=tmp_path)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["run_id"] == run_id and len(data["findings"]) == 3


def test_unknown_run_is_an_error(sessions, tmp_path):
    with sessions() as session, pytest.raises(LookupError):
        export_run(session, "00000000-0000-0000-0000-000000000000", data_dir=tmp_path)


# --- pure helpers -------------------------------------------------------------------------------


def test_evidence_splits_console_network_and_accessibility():
    evidence = {
        "console_errors": [{"kind": "console", "text": "boom"}],
        "failed_requests": [{"url": "/x", "status": 404}],
        "pages": ["/"],
    }
    step_events = [
        {"type": "event", "text": "pageerror error: oops"},  # an agent step
        {"type": "event", "text": "network: GET /y → 500"},
        {"type": "event", "text": "the page went to another site and was brought back"},
        {"type": "console", "text": "crawl error"},  # a crawl step (execute.page_events)
        {"type": "network", "text": "GET /z → 404"},
        {"type": "a11y", "text": "image-alt: Images must have alternate text"},
    ]
    split = evidence_of(evidence, step_events)
    assert split["console"] == [
        {"kind": "console", "text": "boom"},
        "pageerror error: oops",
        "crawl error",
    ]
    assert split["network"] == [
        {"url": "/x", "status": 404},
        "network: GET /y → 500",
        "GET /z → 404",
    ]
    assert split["accessibility"] == ["image-alt: Images must have alternate text"]
    assert split["other"] == {"pages": ["/"]}


@pytest.mark.parametrize(
    ("status", "evidence", "verified"),
    [
        ("confirmed", {"replay": "reproduced"}, True),
        ("confirmed", {}, False),  # deterministic: confirmed by hard evidence, never replayed
        ("dismissed", {"replay": "did not show"}, False),
        ("candidate", {}, False),  # out of budget before replay
    ],
)
def test_replay_verified(status, evidence, verified):
    assert replay_verified(status, evidence) is verified


def test_a_unique_prefix_finds_the_run(sessions, run_id):
    from worker.export import find_run_id

    with sessions() as session:
        assert find_run_id(session, run_id[:8]) == run_id
        with pytest.raises(LookupError):
            find_run_id(session, "ffffffff-no-such-run")
