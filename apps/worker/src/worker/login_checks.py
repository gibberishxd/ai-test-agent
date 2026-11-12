"""Test sign-in (run 4, J2): the web app sets `check_requested_at`, a worker signs in once.

Signing in needs a browser, so the web app can't do it. A worker claims one requested check
at a time (FOR UPDATE SKIP LOCKED, like runs), signs in through the safety proxy, and stores
`last_check` = {ok, detail, checkedAt}. The detail never contains the password or username.

Sign-in setups only work on our demo shops and on domains the workspace has verified: a worker
that submits credentials to any site a workspace names would be an abuse tool.
"""

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from worker.config import Settings
from worker.db.models import LoginSetup
from worker.db.tenant import enter_tenant
from worker.login import SignInResult, check_result, config_from_row, sign_in
from worker.scan import guarded_browser, is_demo_target
from worker.secret_box import server_key

NOT_VERIFIED = (
    "sign-in setups only work on verified domains: verify this domain first (Settings → Domains)"
)


def setup_allowed(session: Session, settings: Settings, workspace_id, url: str) -> bool:
    from worker.execute import is_verified_domain

    return is_demo_target(settings, url) or is_verified_domain(session, workspace_id, url)


def process_login_check(sessions: sessionmaker[Session], settings: Settings, browser=None) -> bool:
    """Run one requested check. Returns False when none is waiting.

    requested_login_checks (a database function) lists the waiting checks in every workspace;
    the chosen one is locked and checked inside its own workspace (run 5, K3)."""
    with sessions() as session:
        waiting = session.execute(
            text("SELECT id, workspace_id FROM requested_login_checks(5)")
        ).all()
        session.commit()
    for setup_id, workspace_id in waiting:
        with sessions() as session:
            enter_tenant(session, workspace_id)
            row = session.scalars(
                select(LoginSetup)
                .where(LoginSetup.id == setup_id, LoginSetup.check_requested_at.is_not(None))
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:
                continue  # another worker is checking it
            try:
                result = _check(session, settings, row, browser)
            except Exception as error:  # a broken setup must not stop the worker
                result = SignInResult(False, f"the check failed ({type(error).__name__})")
            row.last_check = check_result(result)
            row.check_requested_at = None
            session.commit()
            return True
    return False


def _check(session: Session, settings: Settings, row: LoginSetup, browser) -> SignInResult:
    target = row.origin + "/"
    if not setup_allowed(session, settings, row.workspace_id, target):
        return SignInResult(False, NOT_VERIFIED)
    login = config_from_row(row, server_key(settings.model_keys_secret.get_secret_value()))
    with guarded_browser(settings, target, browser) as (new_context, _guard):
        context = new_context()
        try:
            return sign_in(context, login)
        finally:
            context.close()
