"""Deep-mode findings through the run's verification (execute.verify_and_dedupe): replayed from
the model's own steps, re-measured, or kept apart as unverified. Never dismissed just because
nothing could check them, and never left as plain candidates."""

import json

import pytest

from worker.config import Settings
from worker.db.models import Bug, Run, Step, Workspace
from worker.execute import verify_and_dedupe
from worker.llm import FakeClient

REPRODUCED = json.dumps({"reproduced": True, "reason": "seen"})
NO_DUPLICATES = json.dumps({"duplicates": []})
ADD = {"role": "button", "name": "Add one", "css": "#add", "nth": 0, "count": 1}
COLOR = "return getComputedStyle(document.querySelector('#faint')).color"


@pytest.fixture
def settings(site_url, tmp_path):
    return Settings(
        _env_file=None,
        demo_url=site_url,
        clean_demo_url=site_url,
        dev_mode=True,
        data_dir=str(tmp_path),
        max_run_cost_usd=1.0,
    )


def store(sessions, site_url, steps: list[dict], bugs: list[dict], **run_fields) -> str:
    with sessions() as session:
        ws = Workspace(name="w", slug="w")
        session.add(ws)
        session.flush()
        run = Run(
            workspace_id=ws.id,
            target_url=f"{site_url}/deep.html",
            mode="interactive",
            engine="deep",
            **run_fields,
        )
        session.add(run)
        session.flush()
        for index, step in enumerate(steps):
            session.add(Step(run_id=run.id, index=index, **step))
        for number, fields in enumerate(bugs, start=1):
            session.add(
                Bug(
                    run_id=run.id,
                    title=f"Deep {number}",
                    severity="medium",
                    category="functional",
                    page_url=f"{site_url}/deep.html",
                    source="agent",
                    status="candidate",
                    **fields,
                )
            )
        run.step_count = len(steps)
        session.commit()
        return str(run.id)


def verify(sessions, settings, run_id, browser, texts):
    with sessions() as session:
        run = session.get(Run, run_id)
        stats = verify_and_dedupe(session, run, FakeClient(texts=texts), settings, browser)
        bugs = {b.title: b for b in session.query(Bug).filter_by(run_id=run.id)}
        return stats, {t: (b.status, b.evidence, b.dismiss_reason) for t, b in bugs.items()}


def click_add(site_url) -> dict:
    return {"action": "click", "url": f"{site_url}/deep.html", "args": {"element": ADD}}


def deep_evidence(verify_spec: dict, **more) -> dict:
    return {"engine": "deep", "verify": verify_spec, "viewport": "1280x800", **more}


def test_a_replay_finding_is_replayed_from_the_models_own_steps(
    sessions, settings, site_url, browser
):
    run_id = store(
        sessions,
        site_url,
        [click_add(site_url)],
        [
            {
                "step_indexes": [0],
                "evidence": deep_evidence(
                    {"kind": "replay", "steps": [0]}, reported_at=1, replay_from=0
                ),
            }
        ],
    )
    # One finding: no dedup call, so the first answer is the replay judge's.
    stats, bugs = verify(sessions, settings, run_id, browser, [REPRODUCED])
    status, evidence, _ = bugs["Deep 1"]
    assert status == "confirmed"
    assert evidence["verification"]["kind"] == "replay"
    assert stats["confirmed"] == 1


def test_a_replay_that_cant_be_repeated_is_unverified_not_dismissed(
    sessions, settings, site_url, browser
):
    gone = {
        "action": "click",
        "url": f"{site_url}/deep.html",
        "args": {"element": {"role": "button", "name": "Not there", "nth": 0, "count": 1}},
    }
    run_id = store(
        sessions,
        site_url,
        [gone],
        [
            {
                "step_indexes": [0],
                "evidence": deep_evidence(
                    {"kind": "replay", "steps": [0]}, reported_at=1, replay_from=0
                ),
            }
        ],
    )
    stats, bugs = verify(sessions, settings, run_id, browser, [NO_DUPLICATES])
    status, evidence, _ = bugs["Deep 1"]
    assert status == "unverified"
    assert "replay" in evidence["verification"]["reason"]
    assert stats["unverified"] == 1


def test_a_measurement_is_measured_again(sessions, settings, site_url, browser):
    same = {
        "kind": "measure",
        "snippet": COLOR,
        "result": "rgb(187, 187, 187)",
        "url": f"{site_url}/deep.html",
        "viewport": "1280x800",
        "setup_steps": [],
    }
    wrong = {**same, "result": "rgb(1, 1, 1)"}
    run_id = store(
        sessions,
        site_url,
        [],
        [{"evidence": deep_evidence(same)}, {"evidence": deep_evidence(wrong)}],
    )
    _, bugs = verify(sessions, settings, run_id, browser, [NO_DUPLICATES])
    assert bugs["Deep 1"][0] == "confirmed"
    assert bugs["Deep 2"][0] == "dismissed" and "rgb(1, 1, 1)" in bugs["Deep 2"][2]
    assert bugs["Deep 1"][1]["verification"]["kind"] == "measure"


def test_measurement_setup_steps_are_replayed(sessions, settings, site_url, browser):
    spec = {
        "kind": "measure",
        "snippet": "return document.querySelector('#total').textContent",
        "result": "1",
        "url": f"{site_url}/deep.html",
        "viewport": "1280x800",
        "setup_steps": [0],
    }
    run_id = store(sessions, site_url, [click_add(site_url)], [{"evidence": deep_evidence(spec)}])
    _, bugs = verify(sessions, settings, run_id, browser, [NO_DUPLICATES])
    assert bugs["Deep 1"][0] == "confirmed"


def test_a_finding_without_a_way_to_verify_it_is_unverified(sessions, settings, site_url, browser):
    run_id = store(sessions, site_url, [], [{"evidence": {"engine": "deep"}}])
    _, bugs = verify(sessions, settings, run_id, browser, [NO_DUPLICATES])
    assert bugs["Deep 1"][0] == "unverified"


def test_deep_runs_are_verified_whatever_the_current_loops_cost_budget(
    sessions, settings, site_url, browser
):
    spec = {
        "kind": "measure",
        "snippet": COLOR,
        "result": "rgb(187, 187, 187)",
        "url": f"{site_url}/deep.html",
        "viewport": "1280x800",
        "setup_steps": [],
    }
    run_id = store(
        sessions,
        site_url,
        [],
        [{"evidence": deep_evidence(spec)}],
        estimated_cost_usd=25.0,
        cost_usd=25.0,
    )
    _, bugs = verify(sessions, settings, run_id, browser, [NO_DUPLICATES])
    assert bugs["Deep 1"][0] == "confirmed"


def test_a_stopped_run_leaves_deep_findings_unverified_not_candidates(
    sessions, settings, site_url, browser
):
    spec = {
        "kind": "measure",
        "snippet": COLOR,
        "result": "x",
        "url": f"{site_url}/deep.html",
        "viewport": "1280x800",
        "setup_steps": [],
    }
    run_id = store(sessions, site_url, [], [{"evidence": deep_evidence(spec)}], stop_requested=True)
    stats, bugs = verify(sessions, settings, run_id, browser, [NO_DUPLICATES])
    assert bugs["Deep 1"][0] == "unverified"
    assert "stopped" in bugs["Deep 1"][1]["verification"]["reason"]
