"""A whole interactive run behind a login (run 4, J2): queue → sign in → crawl, agent, replay.

The run, its steps, its bugs and every model call are checked for the test account's password
and username: they must appear nowhere.
"""

import base64
import json
import os
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from worker.config import Settings
from worker.db.models import Bug, LoginSetup, Run, RunStatus, Step
from worker.execute import make_execute
from worker.llm import FakeClient, ToolCall
from worker.runner import process_next
from worker.storage import LocalStorage

PASSWORD = "s3cret-Pass!"
USERNAME = "tester@example.com"
KEY = os.urandom(32)


def encrypt(plain: str, workspace_id: str) -> str:
    """What the web app stores (lib/secret-box.ts): "v1:" + base64(nonce ‖ ciphertext ‖ tag)."""
    nonce = os.urandom(12)
    body = AESGCM(KEY).encrypt(nonce, plain.encode(), workspace_id.encode())
    return "v1:" + base64.b64encode(nonce + body).decode()


@pytest.fixture
def settings(site_url, tmp_path):
    return Settings(
        _env_file=None,
        demo_url=site_url,
        clean_demo_url=site_url,
        dev_mode=True,
        data_dir=str(tmp_path),
        model_keys_secret=base64.b64encode(KEY).decode(),
        max_steps=6,
    )


def queue_signed_in_run(sessions, workspace, site_url, password=PASSWORD) -> Run:
    with sessions() as session:
        session.add(
            LoginSetup(
                workspace_id=workspace.id,
                origin=site_url,
                kind="form",
                login_url=f"{site_url}/signin.html",
                username=USERNAME,
                password_ciphertext=encrypt(password, str(workspace.id)),
            )
        )
        run = Run(
            workspace_id=workspace.id, target_url=f"{site_url}/account.html", mode="interactive"
        )
        session.add(run)
        session.commit()
        return run


def everything_stored(session, run_id) -> str:
    run = session.get(Run, run_id)
    steps = session.query(Step).filter_by(run_id=run_id).all()
    bugs = session.query(Bug).filter_by(run_id=run_id).all()
    rows = (
        [run.summary, run.error]
        + [[s.action, s.args, s.reasoning, s.url, s.events, s.block_reason] for s in steps]
        + [[b.title, b.expected, b.actual, b.evidence, b.repro_steps] for b in bugs]
    )
    return json.dumps(rows, default=str)


def test_a_signed_in_run_tests_the_account_area_and_stores_no_credentials(
    sessions, workspace, settings, site_url, tmp_path, browser
):
    run = queue_signed_in_run(sessions, workspace, site_url)
    llm = FakeClient(
        decisions=[
            ToolCall("scroll", {"reasoning": "look", "direction": "down"}),
            ToolCall(
                "report_bug",
                {
                    "reasoning": "seen",
                    "title": "Account page shows the email in plain text",
                    "severity": "low",
                    "category": "ux",
                    "expected": "masked",
                    "actual": "Signed in as tester@example.com",
                    "step_ids": [1],
                    "evidence": "Signed in as tester@example.com",
                },
            ),
            ToolCall("finish", {"reasoning": "done", "summary": "done"}),
        ],
        default_text='{"duplicates": [], "reproduced": true, "reason": "shown"}',
    )
    process_next(sessions, llm, make_execute(settings, LocalStorage(tmp_path), browser))

    with sessions() as session:
        stored = session.get(Run, run.id)
        assert stored.status == RunStatus.DONE, stored.error
        agent_steps = session.query(Step).filter_by(run_id=run.id, action="scroll").all()
        assert agent_steps and all(s.url.endswith("/account.html") for s in agent_steps)
        visits = session.query(Step).filter_by(run_id=run.id, action="visit").all()
        assert visits[0].url.endswith("/account.html")  # the crawl was signed in too
        report = session.query(Bug).filter_by(run_id=run.id, source="agent").one()
        assert report.status == "confirmed"  # the replay's fresh context was signed in
        stored_text = everything_stored(session, run.id)
    model_saw = json.dumps(llm.calls, default=str)
    for secret in (PASSWORD, USERNAME):
        assert secret not in stored_text
        assert secret not in model_saw
    replay = next(c for c in llm.calls if c["method"] == "review_screenshot")
    assert "account.html" in replay["prompt"]


def test_a_wrong_password_fails_the_run_with_a_safe_reason(
    sessions, workspace, settings, site_url, tmp_path, browser
):
    run = queue_signed_in_run(sessions, workspace, site_url, password="wrong-Pass-123")
    process_next(sessions, FakeClient(), make_execute(settings, LocalStorage(tmp_path), browser))
    with sessions() as session:
        stored = session.get(Run, run.id)
        assert stored.status == RunStatus.FAILED
        assert "sign-in failed" in stored.error and "Wrong email or password." in stored.error
        assert "wrong-Pass-123" not in stored.error and USERNAME not in stored.error


# --- "Test sign-in" (the web app asks, the worker signs in once) -------------------------------


def request_check(sessions, workspace, site_url, password=PASSWORD):
    with sessions() as session:
        setup = LoginSetup(
            workspace_id=workspace.id,
            origin=site_url,
            kind="form",
            login_url=f"{site_url}/signin.html",
            username=USERNAME,
            password_ciphertext=encrypt(password, str(workspace.id)),
            check_requested_at=datetime.now(UTC),
        )
        session.add(setup)
        session.commit()
        return setup.id


def test_test_sign_in_stores_ok_or_the_safe_reason(
    sessions, workspace, settings, site_url, browser
):
    from worker.login_checks import process_login_check

    good = request_check(sessions, workspace, site_url)
    assert process_login_check(sessions, settings, browser) is True
    with sessions() as session:
        row = session.get(LoginSetup, good)
        assert row.check_requested_at is None and row.last_check["ok"] is True
        session.delete(row)
        session.commit()

    bad = request_check(sessions, workspace, site_url, password="wrong-Pass-123")
    assert process_login_check(sessions, settings, browser) is True
    with sessions() as session:
        check = session.get(LoginSetup, bad).last_check
    assert check["ok"] is False and "Wrong email or password." in check["detail"]
    assert "wrong-Pass-123" not in json.dumps(check) and USERNAME not in json.dumps(check)
    assert process_login_check(sessions, settings, browser) is False  # nothing left to do


def test_sign_in_setups_only_work_on_the_demo_shops_and_verified_domains(
    sessions, workspace, site_url, tmp_path, browser
):
    # A worker that submits credentials to any site a workspace names would be an abuse tool.
    from worker.login_checks import process_login_check

    not_demo = Settings(
        _env_file=None,
        demo_url="http://localhost:5999/",
        clean_demo_url="http://localhost:5998/",
        dev_mode=True,
        data_dir=str(tmp_path),
        model_keys_secret=base64.b64encode(KEY).decode(),
    )
    setup_id = request_check(sessions, workspace, site_url)
    process_login_check(sessions, not_demo, browser)
    with sessions() as session:
        check = session.get(LoginSetup, setup_id).last_check
    assert check["ok"] is False and "verify" in check["detail"]
