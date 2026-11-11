"""Testing apps behind a login (run 4, J2): the worker signs in, the agent never sees how.

The test account's password and username never reach the model, the steps, the logs or a
screenshot; the agent may not log out or delete the account; a session that ends is restored.
"""

import logging
from urllib.parse import urlsplit

import pytest

from worker.agent.loop import AgentConfig, AgentRun
from worker.agent.policy import Budget
from worker.llm import FakeClient, ToolCall
from worker.login import LoginConfig, on_login_page, sign_in
from worker.safety.network import NetworkGuard

PASSWORD = "s3cret-Pass!"
USERNAME = "tester@example.com"


def form_login(site_url, **fields) -> LoginConfig:
    return LoginConfig(
        kind="form",
        origin=site_url,
        login_url=f"{site_url}/signin.html",
        username=USERNAME,
        password=PASSWORD,
        **fields,
    )


def test_form_sign_in_finds_the_fields_itself_and_keeps_the_session(context, site_url):
    result = sign_in(context, form_login(site_url))
    assert result.ok, result.detail
    page = context.new_page()
    page.goto(f"{site_url}/account.html")
    assert page.locator("h1").inner_text() == "Your account"


def test_explicit_selectors_are_used(context, site_url):
    login = form_login(
        site_url,
        username_selector="#email",
        password_selector="#pw",
        submit_selector="button[type=submit]",
        success_selector="#who",
    )
    assert sign_in(context, login).ok


def test_a_wrong_password_fails_with_the_sites_message_and_no_secret(context, site_url):
    login = form_login(site_url)
    login.password = "wrong-Pass-123"
    result = sign_in(context, login)
    assert not result.ok
    assert "Wrong email or password." in result.detail
    assert "wrong-Pass-123" not in result.detail and USERNAME not in result.detail


def test_a_recorded_sign_in_is_loaded_into_the_context(context, site_url):
    state = {
        "cookies": [],
        "origins": [{"origin": site_url, "localStorage": [{"name": "session", "value": "x"}]}],
    }
    login = LoginConfig(kind="storage_state", origin=site_url, storage_state=state)
    assert sign_in(context, login).ok
    page = context.new_page()
    page.goto(f"{site_url}/account.html")
    assert page.locator("h1").inner_text() == "Your account"


def test_signed_out_means_landing_on_the_login_page(context, site_url):
    page = context.new_page()
    page.goto(f"{site_url}/account.html")  # no session: redirected to the sign-in page
    assert on_login_page(page.url, form_login(site_url))
    page.goto(f"{site_url}/form.html")
    assert not on_login_page(page.url, form_login(site_url))


# --- in the agent loop -------------------------------------------------------------------------

LOGOUT, DELETE, EXPIRE = 1, 2, 3  # element ids on account.html


@pytest.fixture
def signed_in_agent(context, site_url, caplog):
    caplog.set_level(logging.DEBUG)
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )

    def make(decisions):
        login = form_login(site_url)
        assert sign_in(context, login).ok
        llm = FakeClient(decisions=decisions)
        config = AgentConfig(
            target_url=f"{site_url}/account.html",
            mode="interactive",
            budget=Budget(max_steps=10, max_seconds=60, max_cost_usd=1.0),
            login=login,
        )
        return AgentRun(
            context.new_page(), llm, guard, config, relogin=lambda: sign_in(context, login)
        ), llm

    return make


def call(name, **args):
    return ToolCall(name, {"reasoning": "test", **args})


def test_the_agent_may_not_log_out_or_delete_the_account(signed_in_agent):
    run, _ = signed_in_agent(
        [
            call("click", element_id=LOGOUT, expect="signed out"),
            call("click", element_id=DELETE, expect="x"),
        ]
    )
    result = run.run()
    assert result.steps[0].blocked and "log out" in result.steps[0].block_reason
    assert result.steps[1].blocked
    assert run.page.locator("h1").inner_text() == "Your account"


def test_a_session_that_ends_is_restored_and_the_model_is_told(signed_in_agent, site_url):
    run, llm = signed_in_agent(
        [
            call("click", element_id=EXPIRE, expect="data refreshed"),
            call("scroll", direction="down"),
        ]
    )
    result = run.run()
    assert run.page.url == f"{site_url}/account.html"
    assert "signed in again" in result.steps[0].result
    assert result.relogins == 1


def test_credentials_never_reach_the_model_steps_or_logs(signed_in_agent, caplog):
    run, llm = signed_in_agent([call("scroll", direction="down"), call("finish", summary="done")])
    result = run.run()
    seen = " ".join(c["observation"] for c in llm.calls if c["method"] == "decide")
    seen += " ".join(f"{s.human} {s.result} {s.args}" for s in result.steps) + caplog.text
    assert PASSWORD not in seen
    assert USERNAME not in seen  # the page shows it; the observation must not
    assert "[test account]" in seen


def test_password_fields_are_masked_in_screenshots(context, site_url):
    page = context.new_page()
    page.goto(f"{site_url}/signin.html")
    page.fill("#pw", "visible-secret")
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )
    config = AgentConfig(
        target_url=f"{site_url}/signin.html",
        mode="interactive",
        budget=Budget(max_steps=1, max_seconds=5, max_cost_usd=1),
    )
    run = AgentRun(page, FakeClient(), guard, config)
    page.fill("#pw", "visible-secret")
    assert run._screenshot() != page.screenshot()


# --- the run: crawl, agent and replays all signed in -------------------------------------------


def test_signed_in_links_to_log_out_are_skipped():
    from worker.login import is_logout_link

    assert is_logout_link("https://app.test/logout")
    assert is_logout_link("https://app.test/auth/sign-out?next=/")
    assert not is_logout_link("https://app.test/account/orders")


def test_every_context_of_a_signed_in_browser_is_signed_in(site_url, browser, tmp_path):
    from worker.config import Settings
    from worker.scan import guarded_browser

    settings = Settings(_env_file=None, dev_mode=True, demo_url=f"{site_url}/")
    login = form_login(site_url)
    with guarded_browser(settings, f"{site_url}/account.html", browser, login=login) as (
        new_context,
        _guard,
    ):
        for _ in range(2):  # a replay's fresh context is signed in too
            context = new_context()
            page = context.new_page()
            page.goto(f"{site_url}/account.html")
            assert page.locator("h1").inner_text() == "Your account"
            context.close()


def test_a_failed_sign_in_stops_the_run_with_a_safe_message(site_url, browser):
    from worker.config import Settings
    from worker.login import SignInFailed
    from worker.scan import guarded_browser

    settings = Settings(_env_file=None, dev_mode=True, demo_url=f"{site_url}/")
    login = form_login(site_url)
    login.password = "wrong-Pass-123"
    with pytest.raises(SignInFailed) as failed:
        with guarded_browser(settings, f"{site_url}/", browser, login=login) as (new_context, _):
            new_context()
    assert "wrong-Pass-123" not in str(failed.value) and USERNAME not in str(failed.value)


def test_a_single_page_app_that_changes_view_a_moment_later_counts_as_signed_in(context, site_url):
    # Run 4: the demo shop navigates in the browser after login (no page load, no request), so
    # right after the click the password field is still there for a few hundred milliseconds.
    login = form_login(site_url)
    login.login_url = f"{site_url}/signin-spa.html"
    assert sign_in(context, login).ok
