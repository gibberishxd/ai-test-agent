"""Signing in to the app under test before the agent starts (run 4, J2).

A workspace saves a login setup per target (web: lib/login-setups.ts): a login form with a TEST
account, or a recorded sign-in (Playwright storage state). The worker applies it to a browser
context deterministically, so the agent starts signed in and never sees how:

- the password and username never go into the prompt, steps, logs or reports (`scrub`);
- password fields are masked in every screenshot (agent/loop.py);
- logging out, changing the password and deleting the account are denied (agent/policy.py);
- if a session ends mid-run, the worker signs in again (agent/loop.py).

The same sign-in is applied to the crawl, the agent's browser and every replay's fresh context.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext, Page
from playwright.sync_api import Error as PlaywrightError
from sqlalchemy import select
from sqlalchemy.orm import Session

from worker.browser import wait_until_quiet
from worker.db.models import LoginSetup
from worker.secret_box import decrypt_secret

log = logging.getLogger(__name__)

TIMEOUT_MS = 15_000
JUDGE_MS = 5000  # how long a sign-in may take to show its result
POLL_MS = 100
SETTLE_MS = 2000
ACCOUNT_MASK = "[test account]"
SECRET_MASK = "[secret]"

# Without selectors, the first visible match of each list is used.
USERNAME_FIELDS = [
    "input[autocomplete=username]",
    "input[type=email]",
    "input[name*=user i]",
    "input[name*=email i]",
    "input[name*=login i]",
    "input[id*=user i]",
    "input[id*=email i]",
    "input[type=text]",
]
PASSWORD_FIELDS = ["input[type=password]"]
SUBMIT_BUTTONS = ["button[type=submit]", "input[type=submit]", "form button"]
MESSAGE_SELECTOR = "[role=alert], .error, .field-error, [aria-live]"


@dataclass
class LoginConfig:
    kind: str  # "form" or "storage_state"
    origin: str
    login_url: str | None = None
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    username_selector: str | None = None
    password_selector: str | None = None
    submit_selector: str | None = None
    success_selector: str | None = None
    storage_state: dict | None = field(default=None, repr=False)

    def secrets(self) -> list[str]:
        """Exact values to scrub from anything the model, the database or a log sees."""
        return [value for value in (self.password, self.username) if value and len(value) >= 3]

    def scrub(self, text: str) -> str:
        if self.password:
            text = text.replace(self.password, SECRET_MASK)
        if self.username and len(self.username) >= 3:
            text = re.sub(re.escape(self.username), ACCOUNT_MASK, text, flags=re.IGNORECASE)
        return text


class SignInFailed(Exception):
    """The run can't start signed in. The message is safe to show (no secret in it)."""


@dataclass
class SignInResult:
    ok: bool
    detail: str  # never contains the password or the username


def load_login(session: Session, workspace_id, target_url: str, key: bytes) -> LoginConfig | None:
    """The workspace's login setup for the target's origin, decrypted, or None."""
    parts = urlsplit(target_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    row = session.scalars(
        select(LoginSetup).where(
            LoginSetup.workspace_id == workspace_id, LoginSetup.origin == origin
        )
    ).first()
    return config_from_row(row, key) if row else None


def config_from_row(row: LoginSetup, key: bytes) -> LoginConfig:
    workspace = str(row.workspace_id)
    password = (
        decrypt_secret(row.password_ciphertext, workspace, key) if row.password_ciphertext else None
    )
    state = (
        json.loads(decrypt_secret(row.storage_state_ciphertext, workspace, key))
        if row.storage_state_ciphertext
        else None
    )
    return LoginConfig(
        kind=row.kind,
        origin=row.origin,
        login_url=row.login_url,
        username=row.username,
        password=password,
        username_selector=row.username_selector,
        password_selector=row.password_selector,
        submit_selector=row.submit_selector,
        success_selector=row.success_selector,
        storage_state=state,
    )


def login_for_run(session: Session, settings, run) -> LoginConfig | None:
    """The run's login setup (by its target's origin), decrypted; None if it has none.

    Raises SignInFailed when the target is neither a demo shop nor a verified domain."""
    from worker.login_checks import NOT_VERIFIED, setup_allowed
    from worker.secret_box import server_key

    parts = urlsplit(run.target_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    row = session.scalars(
        select(LoginSetup).where(
            LoginSetup.workspace_id == run.workspace_id, LoginSetup.origin == origin
        )
    ).first()
    if row is None:
        return None
    if not setup_allowed(session, settings, run.workspace_id, run.target_url):
        raise SignInFailed(NOT_VERIFIED)
    return config_from_row(row, server_key(settings.model_keys_secret.get_secret_value()))


def sign_in(context: BrowserContext, login: LoginConfig) -> SignInResult:
    """Sign `context` in. Cookies and local storage it gets are shared by its pages."""
    try:
        if login.kind == "storage_state":
            return _load_state(context, login)
        return _fill_form(context, login)
    except PlaywrightError as error:
        detail = login.scrub(str(error).splitlines()[0])[:200]
        return SignInResult(False, f"the browser failed while signing in: {detail}")


def is_logout_link(url: str) -> bool:
    """A link a signed-in crawl must not follow: it would end the run's own session."""
    from worker.agent.policy import SIGNED_IN_RULES, url_words

    words = url_words(url)
    return any(rule.pattern.search(words) for rule in SIGNED_IN_RULES[:1])


def on_login_page(url: str, login: LoginConfig) -> bool:
    """`url` is the login page: where an app sends a visitor whose session has ended."""
    if not login.login_url:
        return False
    return _path(url) == _path(login.login_url)


def _path(url: str) -> str:
    return urlsplit(url).path.rstrip("/") or "/"


def _first_visible(page: Page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector)
        for i in range(locator.count()):
            if locator.nth(i).is_visible():
                return locator.nth(i)
    return None


def _fill_form(context: BrowserContext, login: LoginConfig) -> SignInResult:
    if not (login.login_url and login.username and login.password):
        return SignInResult(False, "the setup needs a login page, a username and a password")
    page = context.new_page()
    try:
        page.goto(login.login_url, timeout=TIMEOUT_MS)
        wait_until_quiet(page, SETTLE_MS)
        user = _first_visible(
            page, [login.username_selector] if login.username_selector else USERNAME_FIELDS
        )
        password = _first_visible(
            page, [login.password_selector] if login.password_selector else PASSWORD_FIELDS
        )
        if user is None or password is None:
            missing = "username" if user is None else "password"
            return SignInResult(
                False, f"no {missing} field found on the login page; set a selector"
            )
        user.fill(login.username, timeout=TIMEOUT_MS)
        password.fill(login.password, timeout=TIMEOUT_MS)
        submit = _first_visible(
            page, [login.submit_selector] if login.submit_selector else SUBMIT_BUTTONS
        )
        if submit is not None:
            submit.click(timeout=TIMEOUT_MS)
        else:
            password.press("Enter")
        wait_until_quiet(page, SETTLE_MS)
        return _judge(page, login)
    finally:
        page.close()


def _judge(page: Page, login: LoginConfig) -> SignInResult:
    """Did it work? A success selector is proof; otherwise the password field must be gone.

    Polled for up to JUDGE_MS: a single-page app changes its view a moment after the click,
    without a page load or a request that "network idle" could wait for."""
    deadline = time.monotonic() + JUDGE_MS / 1000
    while True:
        if login.success_selector:
            if page.locator(login.success_selector).first.is_visible():
                return SignInResult(True, f"signed in: {login.success_selector} is shown")
        elif _first_visible(page, PASSWORD_FIELDS) is None:
            return SignInResult(True, f"signed in: now on {_path(page.url)}")
        if time.monotonic() > deadline:
            break
        page.wait_for_timeout(POLL_MS)
    what = (
        f"{login.success_selector} isn't shown"
        if login.success_selector
        else "still on the sign-in page"
    )
    return SignInResult(False, _failure(page, login, what))


def _failure(page: Page, login: LoginConfig, what: str) -> str:
    messages = [
        text.strip() for text in page.locator(MESSAGE_SELECTOR).all_inner_texts() if text.strip()
    ]
    said = f"; the site said: {' '.join(messages)[:200]}" if messages else ""
    return login.scrub(f"sign-in failed: {what}{said}")


def _load_state(context: BrowserContext, login: LoginConfig) -> SignInResult:
    state = login.storage_state or {}
    cookies = state.get("cookies") or []
    if cookies:
        context.add_cookies(cookies)
    origins = state.get("origins") or []
    for entry in origins:
        items = entry.get("localStorage") or []
        # Local storage belongs to an origin: write it whenever a page of that origin loads.
        context.add_init_script(
            script=(
                "(([origin, items]) => { if (location.origin !== origin) return;"
                " for (const [k, v] of items) { if (localStorage.getItem(k) === null)"
                " localStorage.setItem(k, v); } })"
                f"({json.dumps([entry.get('origin'), [[i['name'], i['value']] for i in items]])})"
            )
        )
    count = len(cookies) + sum(len(e.get("localStorage") or []) for e in origins)
    if count == 0:
        return SignInResult(False, "the recorded sign-in has no cookies or local storage")
    return SignInResult(True, f"recorded sign-in loaded ({count} values)")


def check_result(result: SignInResult) -> dict:
    """What "Test sign-in" stores: ok, a safe detail, and when."""
    return {"ok": result.ok, "detail": result.detail, "checkedAt": datetime.now(UTC).isoformat()}
