"""Replaying several reports of one run: each replay starts clean, and failures say why.

Run be495c9f lost two correct reports in replay. These tests replay two or more reports in a
row, where the first replay leaves state behind (a cart in localStorage, a phone viewport), and
check that the next one doesn't inherit it and that a failed replay is stored with its reason.
"""

import json

import pytest

from worker.config import Settings
from worker.db.models import Bug, Run, Step
from worker.execute import verify_and_dedupe
from worker.llm import FakeClient

REPRODUCED = json.dumps({"reproduced": True, "reason": "seen"})
NO_DUPLICATES = json.dumps({"duplicates": []})


@pytest.fixture
def settings(site_url, tmp_path):
    return Settings(
        _env_file=None,
        demo_url=site_url,
        clean_demo_url=site_url,
        dev_mode=True,
        data_dir=str(tmp_path),
    )


def element(role: str, name: str) -> dict:
    return {"role": role, "name": name, "nth": 0, "count": 1}


def add_socks_to_cart(url: str, quantity: str) -> list[dict]:
    """The agent's recorded steps: open the item, type a quantity, add it to the cart."""
    return [
        {"action": "click", "url": url, "args": {"element": element("link", "Wool Socks")}},
        {
            "action": "type",
            "url": f"{url}?item",
            "args": {"text": quantity, "element": element("spinbutton", "Quantity")},
        },
        {
            "action": "click",
            "url": f"{url}?item",
            "args": {"element": element("button", "Add to cart")},
        },
    ]


def store_run(sessions, workspace, url: str, flows: list[list[dict]]) -> Run:
    """A finished agent part of a run: each flow's steps, then a report_bug, one bug per flow."""
    with sessions() as session:
        run = Run(workspace_id=workspace.id, target_url=url, mode="interactive")
        session.add(run)
        session.flush()
        index = 0
        for number, flow in enumerate(flows, start=1):
            first = index
            for step in flow:
                session.add(Step(run_id=run.id, index=index, **step))
                index += 1
            session.add(Step(run_id=run.id, index=index, action="report_bug", url=url))
            session.add(
                Bug(
                    run_id=run.id,
                    title=f"Report {number}",
                    severity="medium",
                    category="functional",
                    page_url=url,
                    source="agent",
                    status="candidate",
                    evidence={"reported_at": index, "replay_from": first},
                )
            )
            index += 1
            session.flush()
        run.step_count = index
        session.commit()
        return run


def verify(sessions, run_id, llm, settings, browser) -> list[Bug]:
    with sessions() as session:
        run = session.get(Run, run_id)
        verify_and_dedupe(session, run, llm, settings, browser)
        return session.query(Bug).filter_by(run_id=run_id).order_by(Bug.title).all()


def test_a_replay_does_not_inherit_the_cart_of_the_replay_before_it(
    sessions, workspace, settings, site_url, browser
):
    url = f"{site_url}/spa.html"
    run = store_run(
        sessions, workspace, url, [add_socks_to_cart(url, "3"), add_socks_to_cart(url, "3")]
    )
    llm = FakeClient(texts=[NO_DUPLICATES, REPRODUCED, REPRODUCED])

    bugs = verify(sessions, run.id, llm, settings, browser)

    checks = [c["prompt"] for c in llm.calls if c["method"] == "review_screenshot"]
    assert len(checks) == 2
    # The second replay must see only its own cart, as the agent did when it reported the bug.
    assert "Cart (3)" in checks[1] and "Cart (6)" not in checks[1]
    assert [b.status for b in bugs] == ["confirmed", "confirmed"]


def test_a_replay_does_not_inherit_the_phone_viewport_of_the_replay_before_it(
    sessions, workspace, settings, site_url, browser
):
    url = f"{site_url}/spa.html"
    phone = [{"action": "set_viewport", "url": url, "args": {"size": "mobile"}}]
    run = store_run(sessions, workspace, url, [phone, add_socks_to_cart(url, "1")])
    llm = FakeClient(texts=[NO_DUPLICATES, REPRODUCED, REPRODUCED])

    verify(sessions, run.id, llm, settings, browser)

    checks = [c["prompt"] for c in llm.calls if c["method"] == "review_screenshot"]
    assert "Screen: 1280×800 px" in checks[1]


def test_a_failed_replay_stores_a_specific_reason_on_the_bug(
    sessions, workspace, settings, site_url, browser
):
    url = f"{site_url}/spa.html"
    gone = [
        {
            "action": "click",
            "url": url,
            "args": {"element": element("button", "Button that is not there")},
        }
    ]
    run = store_run(sessions, workspace, url, [add_socks_to_cart(url, "2"), gone])
    llm = FakeClient(texts=[NO_DUPLICATES, REPRODUCED])

    first, second = verify(sessions, run.id, llm, settings, browser)

    assert first.status == "confirmed"
    assert second.status == "dismissed"
    assert second.dismiss_reason.startswith("could not replay: ")
    failure = second.evidence["replay_failure"]
    assert failure["kind"] == "element_not_found"
    assert failure["step"] == 1 and failure["action"] == "click"
    assert "Button that is not there" in failure["detail"]


def test_reverify_replays_a_stored_run_without_changing_it(
    sessions, workspace, settings, site_url, browser
):
    # Re-checking an old run after a replay fix: the stored verdicts stay as they were recorded,
    # the new outcome is only returned. Without a judge, nothing calls a model.
    from worker.reverify import reverify_run

    url = f"{site_url}/spa.html"
    gone = [{"action": "click", "url": url, "args": {"element": element("button", "Gone")}}]
    run = store_run(sessions, workspace, url, [add_socks_to_cart(url, "2"), gone])

    with sessions() as session:
        outcomes = reverify_run(session, run.id, settings, browser=browser)
        stored = session.query(Bug).filter_by(run_id=run.id).all()

    assert [(o["title"], o["replayed"]) for o in outcomes] == [
        ("Report 1", True),
        ("Report 2", False),
    ]
    assert outcomes[1]["failure"]["kind"] == "element_not_found"
    assert outcomes[0]["reproduced"] is None  # no judge: replay only
    assert all(b.status == "candidate" for b in stored)


def test_reverify_with_a_judge_returns_its_verdict(
    sessions, workspace, settings, site_url, browser
):
    from worker.reverify import reverify_run

    url = f"{site_url}/spa.html"
    run = store_run(sessions, workspace, url, [add_socks_to_cart(url, "2")])
    judge = FakeClient(texts=[REPRODUCED])

    with sessions() as session:
        [outcome] = reverify_run(session, run.id, settings, browser=browser, judge=judge)

    assert outcome["replayed"] is True and outcome["reproduced"] is True
    assert "Cart (2)" in judge.calls[0]["prompt"]
