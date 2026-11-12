"""Operator commands (run 5, K4): make someone a platform admin, put a workspace on a plan.
They run on the admin connection by hand; the web app can do neither."""

from worker.admin import make_platform_admin, set_plan
from worker.db.models import User, Workspace


def test_make_platform_admin_by_email(sessions, workspace):
    with sessions() as session:
        session.add(User(email="ops@example.com", workspace_id=workspace.id))
        session.commit()
        assert make_platform_admin(session, "OPS@example.com") is True
        assert session.query(User).filter_by(email="ops@example.com").one().is_platform_admin
        assert make_platform_admin(session, "nobody@example.com") is False


def test_set_plan_by_workspace_slug(sessions, workspace):
    with sessions() as session:
        assert set_plan(session, "test", "team") is True
        assert session.get(Workspace, workspace.id).plan_id == "team"
        assert set_plan(session, "test", "platinum") is False  # no such plan
        assert set_plan(session, "missing", "team") is False
