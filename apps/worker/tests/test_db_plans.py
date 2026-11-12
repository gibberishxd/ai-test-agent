# ruff: noqa: E501 -- SQL statements read best on one line each
"""Plans and usage (run 5, K4), enforced and recorded by Postgres itself.

A workspace is on a plan (runs per month, steps per run, allowed model providers, seats,
retention). consume_quota enforces it when a run starts; a trigger records a usage event when a
run finishes, with the explorer's and the reviewer's tokens and cost apart.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from worker.db.models import Run, UsageEvent, User, Workspace


def as_role(conn, role, workspace=None, user=None):
    conn.execute(text(f"SET LOCAL ROLE {role}"))
    if workspace:
        conn.execute(text("SELECT set_config('app.workspace_id', :w, true)"), {"w": str(workspace)})
    if user:
        conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})


@pytest.fixture
def free(sessions):
    with sessions() as session:
        ws = Workspace(name="Free", slug="free-ws")  # new workspaces start on the free plan
        session.add(ws)
        session.commit()
        return ws.id


def test_the_plans_exist_with_their_limits(db_engine):
    with db_engine.connect() as conn:
        plans = {r.id: r for r in conn.execute(text("SELECT * FROM plans")).all()}
    assert set(plans) == {"free", "team", "business"}
    assert plans["free"].runs_per_month == 30 and plans["free"].max_steps_per_run == 40
    assert plans["free"].allowed_providers == ["ollama"] and plans["team"].allowed_providers == []
    assert (plans["free"].seats, plans["free"].retention_days) == (3, 7)


def test_a_new_workspace_is_on_the_free_plan(sessions, free):
    with sessions() as session:
        assert session.get(Workspace, free).plan_id == "free"


def test_consume_quota_uses_the_plans_runs_and_steps(db_engine, free):
    with db_engine.begin() as conn:
        as_role(conn, "ata_web", workspace=free)
        row = conn.execute(text("SELECT * FROM consume_quota(:w, 'ollama')"), {"w": free}).one()
    assert row.allowed and row.quota == 30 and row.max_steps == 40 and row.reason is None


def test_consume_quota_refuses_a_model_the_plan_doesnt_include(db_engine, free):
    with db_engine.begin() as conn:
        as_role(conn, "ata_web", workspace=free)
        row = conn.execute(text("SELECT * FROM consume_quota(:w, 'claude')"), {"w": free}).one()
    assert not row.allowed and "plan" in row.reason.lower()


def test_consume_quota_counts_against_the_lower_of_plan_and_workspace_quota(
    db_engine, sessions, free
):
    with sessions() as session:
        ws = session.get(Workspace, free)
        ws.monthly_run_quota = 1  # a custom limit lower than the plan's
        session.add(Run(workspace_id=free, target_url="http://x", mode="passive"))
        session.commit()
    with db_engine.begin() as conn:
        as_role(conn, "ata_web", workspace=free)
        row = conn.execute(text("SELECT * FROM consume_quota(:w, NULL)"), {"w": free}).one()
    assert not row.allowed and (row.used, row.quota) == (1, 1)


def test_a_finished_run_records_one_usage_event_with_explorer_and_reviewer_apart(sessions, free):
    with sessions() as session:
        run = Run(workspace_id=free, target_url="http://x", mode="interactive", status="running",
                  started_at=datetime.now(UTC), provider="ollama", model="gemma4:12b",
                  input_tokens=1200, output_tokens=200, cost_usd=0.05,
                  reviewer_provider="claude", reviewer_model="claude-sonnet-5-5",
                  reviewer_input_tokens=200, reviewer_output_tokens=50, reviewer_cost_usd=0.04)  # fmt: skip
        session.add(run)
        session.commit()
        run.status, run.finished_at = "done", datetime.now(UTC)
        session.commit()
        run.summary = {"x": 1}  # a later update doesn't record it twice
        session.commit()
        [event] = session.query(UsageEvent).all()
    assert (event.workspace_id, event.run_id) == (free, run.id)
    assert (event.explorer_model, event.explorer_input_tokens, event.explorer_output_tokens) == (
        "gemma4:12b",
        1000,
        150,
    )
    assert event.explorer_cost_usd == pytest.approx(0.01)
    assert (event.reviewer_model, event.reviewer_input_tokens, event.reviewer_cost_usd) == (
        "claude-sonnet-5-5",
        200,
        pytest.approx(0.04),
    )


def test_usage_events_are_tenant_data(db_engine, sessions, free):
    with sessions() as session:
        other = Workspace(name="O", slug="o")
        session.add(other)
        session.flush()
        for ws in (free, other.id):
            r = Run(
                workspace_id=ws,
                target_url="http://x",
                mode="passive",
                status="running",
                started_at=datetime.now(UTC),
            )
            session.add(r)
            session.flush()
            r.status, r.finished_at = "done", datetime.now(UTC)
        session.commit()
    with db_engine.connect() as conn:
        as_role(conn, "ata_web", workspace=free)
        assert conn.execute(text("SELECT count(*) FROM usage_events")).scalar() == 1
        with pytest.raises(DBAPIError):
            conn.execute(text("DELETE FROM usage_events"))  # billing records are append-only


def test_seats_limit_invitations(db_engine, sessions, free):
    """Free has 3 seats: a 4th member can't join."""
    with sessions() as session:
        for n in range(3):
            session.add(
                User(
                    email=f"m{n}@example.com",
                    workspace_id=free,
                    role="owner" if n == 0 else "member",
                )
            )
        outsider_ws = Workspace(name="Out", slug="out")
        session.add(outsider_ws)
        session.flush()
        outsider = User(email="new@example.com", workspace_id=outsider_ws.id, role="owner")
        session.add(outsider)
        session.commit()
        outsider_id = outsider.id
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO invitations (workspace_id, token_hash, role, expires_at) VALUES (:w, 'h1', 'member', now() + interval '1 day')"
            ),
            {"w": free},
        )
    with db_engine.connect() as conn:
        as_role(conn, "ata_web")
        with pytest.raises(DBAPIError, match="seats"):
            conn.execute(text("SELECT * FROM accept_invitation('h1', :u)"), {"u": outsider_id})


def test_retention_never_exceeds_the_plan(db_engine, sessions, free):
    old = datetime.now(UTC) - timedelta(
        days=8
    )  # older than free's 7 days, newer than the workspace's 30
    with sessions() as session:
        run = Run(
            workspace_id=free,
            target_url="http://x",
            mode="passive",
            status="done",
            started_at=old,
            finished_at=old,
        )
        session.add(run)
        session.commit()
        run_id = run.id
    with db_engine.begin() as conn:
        as_role(conn, "ata_worker")
        purged = (
            conn.execute(text("SELECT run_id FROM apply_retention(now(), 200)")).scalars().all()
        )
    assert purged == [run_id]


def test_only_a_platform_admin_sees_usage_across_workspaces(db_engine, sessions, free):
    with sessions() as session:
        admin = User(
            email="ops@example.com", workspace_id=free, role="owner", is_platform_admin=True
        )
        member = User(email="m@example.com", workspace_id=free, role="member")
        session.add_all([admin, member])
        session.commit()
        admin_id, member_id = admin.id, member.id
    with db_engine.connect() as conn:
        as_role(conn, "ata_web", user=member_id)
        with pytest.raises(DBAPIError, match="platform admin"):
            conn.execute(text("SELECT * FROM platform_usage(date_trunc('month', now()))"))
    with db_engine.connect() as conn:
        as_role(conn, "ata_web", user=admin_id)
        rows = conn.execute(text("SELECT * FROM platform_usage(date_trunc('month', now()))")).all()
    assert {r.slug for r in rows} >= {"free-ws"}
    assert uuid.UUID(str(rows[0].workspace_id))
