"""Operator commands (run 5, K4), run by hand on the admin connection.

`worker make-admin <email>`: the user may see usage across workspaces (/admin/usage).
`worker set-plan <workspace slug> <plan>`: put a workspace on a plan (no billing is connected:
ROADMAP.md says what a payment provider would add).
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from worker.db.models import Plan, User, Workspace


def make_platform_admin(session: Session, email: str) -> bool:
    user = session.scalars(select(User).where(func.lower(User.email) == email.lower())).first()
    if user is None:
        return False
    user.is_platform_admin = True
    session.commit()
    return True


def set_plan(session: Session, slug: str, plan_id: str) -> bool:
    workspace = session.scalars(select(Workspace).where(Workspace.slug == slug)).first()
    if workspace is None or session.get(Plan, plan_id) is None:
        return False
    workspace.plan_id = plan_id
    session.commit()
    return True
