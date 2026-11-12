# ruff: noqa: E501 -- SQL statements read best on one line each
"""Rules that live in Postgres itself (run 5, K3), tested by calling the database directly.

Each rule is here because the database is the one place every writer passes through: the web
app, the worker, a migration, someone with psql. A rule in app code holds only for that app.
The roles are tested by switching to them (SET ROLE), which drops the superuser's powers.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from worker.db.models import (
    AuditLog,
    BenchmarkResult,
    Bug,
    FindingTriage,
    LoginSetup,
    Run,
    RunStatus,
    Step,
    Workspace,
)


@pytest.fixture
def two(sessions):
    """Workspaces A and B, each with one finished run that has a step and a bug."""
    with sessions() as session:
        a = Workspace(name="A", slug="a", monthly_run_quota=3)
        b = Workspace(name="B", slug="b")
        session.add_all([a, b])
        session.flush()
        for ws in (a, b):
            run = Run(workspace_id=ws.id, target_url="http://shop.test/", mode="interactive",
                      status="done", started_at=datetime.now(UTC), finished_at=datetime.now(UTC))  # fmt: skip
            session.add(run)
            session.flush()
            session.add(Step(run_id=run.id, index=0, action="visit"))
            session.add(
                Bug(run_id=run.id, title="t", severity="low", category="ux", page_url="/",
                    source="agent", status="confirmed")
            )  # fmt: skip
        session.commit()
        return a.id, b.id


def as_role(conn, role: str, workspace: uuid.UUID | None = None, user: uuid.UUID | None = None):
    """Act as `role` until the transaction ends (SET LOCAL: a pooled connection keeps nothing)."""
    conn.execute(text(f"SET LOCAL ROLE {role}"))
    if workspace:
        conn.execute(text("SELECT set_config('app.workspace_id', :w, true)"), {"w": str(workspace)})
    if user:
        conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})


# --- Roles -----------------------------------------------------------------------------------


def test_the_app_roles_exist_and_none_is_a_superuser_or_bypasses_rls(db_engine):
    with db_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT rolname, rolsuper, rolbypassrls, rolcanlogin, rolcreaterole "
                "FROM pg_roles WHERE rolname IN ('ata_owner', 'ata_web', 'ata_worker')"
            )
        ).all()
    assert {r.rolname for r in rows} == {"ata_owner", "ata_web", "ata_worker"}
    for row in rows:
        assert not row.rolsuper and not row.rolbypassrls and not row.rolcreaterole, row
        assert row.rolcanlogin, row


def test_the_owner_role_owns_every_table(db_engine):
    with db_engine.connect() as conn:
        owners = (
            conn.execute(
                text("SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'")
            )
            .scalars()
            .all()
        )
    assert owners == ["ata_owner"]


@pytest.mark.parametrize("role", ["ata_web", "ata_worker"])
def test_an_app_role_without_a_workspace_sees_no_tenant_rows(db_engine, two, role):
    with db_engine.connect() as conn:
        as_role(conn, role)
        for table in ("workspaces", "runs", "steps", "bugs"):
            count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            assert count == 0, f"{role} saw {count} rows of {table}"


@pytest.mark.parametrize("role", ["ata_web", "ata_worker"])
def test_an_app_role_sees_only_its_workspace(db_engine, two, role):
    a, b = two
    with db_engine.connect() as conn:
        as_role(conn, role, workspace=a)
        ids = conn.execute(text("SELECT DISTINCT workspace_id FROM runs")).scalars().all()
        assert ids == [a]
        assert conn.execute(text("SELECT count(*) FROM bugs")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM steps")).scalar() == 1


@pytest.mark.parametrize("role", ["ata_web", "ata_worker"])
def test_an_app_role_cant_change_another_workspace(db_engine, two, role):
    a, b = two
    with db_engine.connect() as conn:
        as_role(conn, role, workspace=a)
        changed = conn.execute(
            text("UPDATE runs SET focus = 'x' WHERE workspace_id = :b"), {"b": b}
        ).rowcount
        assert changed == 0
        with pytest.raises(ProgrammingError):  # WITH CHECK refuses a row for another workspace
            conn.execute(
                text(
                    "INSERT INTO runs (workspace_id, target_url, mode) VALUES (:b, 'x', 'passive')"
                ),
                {"b": b},
            )


@pytest.mark.parametrize("role", ["ata_web", "ata_worker"])
def test_the_audit_log_is_append_only_for_the_app_roles(db_engine, two, role):
    a, _ = two
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO audit_log (workspace_id, action) VALUES (:a, 'x.y')"), {"a": a}
        )
    with db_engine.connect() as conn:
        as_role(conn, role, workspace=a)
        with pytest.raises(ProgrammingError):
            conn.execute(text("DELETE FROM audit_log"))


def test_an_app_role_cant_turn_off_row_level_security(db_engine, two):
    with db_engine.connect() as conn:
        as_role(conn, "ata_web")
        with pytest.raises(ProgrammingError):
            conn.execute(text("ALTER TABLE runs DISABLE ROW LEVEL SECURITY"))


def test_only_the_worker_may_claim_runs(db_engine, two):
    with db_engine.connect() as conn:
        as_role(conn, "ata_web")
        with pytest.raises(ProgrammingError):
            conn.execute(text("SELECT * FROM claim_next_run('w', NULL, false)"))


def test_the_web_role_cant_write_the_leaderboard(db_engine, two):
    with db_engine.connect() as conn:
        as_role(conn, "ata_web")
        with pytest.raises(ProgrammingError):
            conn.execute(text("INSERT INTO benchmark_results (runs_buggy) VALUES (1)"))


# --- claim_next_run ----------------------------------------------------------------------------


def test_claim_next_run_takes_the_oldest_queued_run_and_leases_it(db_engine, sessions, two):
    a, b = two
    with sessions() as session:
        older = Run(workspace_id=b, target_url="http://1", mode="passive",
                    created_at=datetime.now(UTC) - timedelta(minutes=5))  # fmt: skip
        newer = Run(workspace_id=a, target_url="http://2", mode="passive")
        session.add_all([older, newer])
        session.commit()
        older_id = older.id
    with db_engine.begin() as conn:
        as_role(conn, "ata_worker")
        row = conn.execute(text("SELECT * FROM claim_next_run('worker-1', NULL, false)")).one()
    assert (row.id, row.workspace_id) == (older_id, b)
    with sessions() as session:
        claimed = session.get(Run, older_id)
        assert claimed.status == RunStatus.RUNNING and claimed.claimed_by == "worker-1"
        assert claimed.started_at is not None and claimed.heartbeat_at is not None


def test_claim_next_run_honours_only_and_skips_the_benchmark_workspace(db_engine, sessions, two):
    with sessions() as session:
        bench = Workspace(name="Benchmark", slug="benchmark")
        session.add(bench)
        session.flush()
        bench_run = Run(workspace_id=bench.id, target_url="http://b", mode="passive")
        session.add(bench_run)
        session.commit()
        bench_id = bench_run.id
    with db_engine.begin() as conn:
        as_role(conn, "ata_worker")
        assert conn.execute(text("SELECT * FROM claim_next_run('w', NULL, true)")).first() is None
        only = conn.execute(
            text("SELECT * FROM claim_next_run('w', ARRAY[:r]::uuid[], false)"), {"r": bench_id}
        ).one()
    assert only.id == bench_id


def test_claim_next_run_never_hands_one_run_to_two_workers(db_engine, sessions, two):
    a, _ = two
    with sessions() as session:
        session.add_all(
            [Run(workspace_id=a, target_url=f"http://{i}", mode="passive") for i in range(10)]
        )
        session.commit()

    def claim(n: int):
        with db_engine.begin() as conn:
            as_role(conn, "ata_worker")
            row = conn.execute(
                text("SELECT id FROM claim_next_run(:w, NULL, false)"), {"w": f"w{n}"}
            ).first()
            return row.id if row else None

    with ThreadPoolExecutor(8) as pool:
        claimed = [c for c in pool.map(claim, range(16)) if c]
    assert len(claimed) == 10 and len(set(claimed)) == 10


def test_recover_runs_fails_expired_leases(db_engine, sessions, two):
    a, _ = two
    with sessions() as session:
        dead = Run(workspace_id=a, target_url="http://d", mode="passive", status="running",
                   started_at=datetime.now(UTC) - timedelta(hours=1),
                   heartbeat_at=datetime.now(UTC) - timedelta(minutes=10))  # fmt: skip
        alive = Run(workspace_id=a, target_url="http://l", mode="passive", status="running",
                    started_at=datetime.now(UTC) - timedelta(hours=1), heartbeat_at=datetime.now(UTC))  # fmt: skip
        session.add_all([dead, alive])
        session.commit()
        dead_id, alive_id = dead.id, alive.id
    with db_engine.begin() as conn:
        as_role(conn, "ata_worker")
        assert conn.execute(text("SELECT recover_runs(90)")).scalar() == 1
    with sessions() as session:
        assert session.get(Run, dead_id).status == RunStatus.FAILED
        assert "heartbeat" in session.get(Run, dead_id).error
        assert session.get(Run, alive_id).status == RunStatus.RUNNING


# --- consume_quota -------------------------------------------------------------------------------


def test_consume_quota_allows_runs_up_to_the_quota(db_engine, two):
    a, _ = two  # quota 3, one run this month already
    with db_engine.begin() as conn:
        as_role(conn, "ata_web", workspace=a)
        first = conn.execute(text("SELECT * FROM consume_quota(:a)"), {"a": a}).one()
        assert first.allowed and first.used == 1 and first.quota == 3


def test_consume_quota_is_atomic_under_a_burst(db_engine, two):
    a, _ = two  # quota 3, one used: exactly two more may start

    def start(_):
        with db_engine.begin() as conn:
            as_role(conn, "ata_web", workspace=a)
            ok = conn.execute(text("SELECT allowed FROM consume_quota(:a)"), {"a": a}).scalar()
            if ok:
                conn.execute(
                    text(
                        "INSERT INTO runs (workspace_id, target_url, mode) VALUES (:a, 'x', 'passive')"
                    ),
                    {"a": a},
                )
            return ok

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(start, range(8)))
    assert results.count(True) == 2


def test_consume_quota_cant_be_used_on_another_workspace(db_engine, two):
    a, b = two
    with db_engine.connect() as conn:
        as_role(conn, "ata_web", workspace=a)
        with pytest.raises(DBAPIError):
            conn.execute(text("SELECT * FROM consume_quota(:b)"), {"b": b})


# --- retention --------------------------------------------------------------------------------


def test_apply_retention_purges_old_runs_and_keeps_their_findings(db_engine, sessions, two):
    a, b = two
    old = datetime.now(UTC) - timedelta(days=40)
    with sessions() as session:
        for run in session.query(Run).filter(Run.workspace_id == a):
            run.status, run.started_at, run.finished_at = "done", old, old
        for bug in session.query(Bug):
            bug.screenshot = "x.png"
        session.commit()
    with db_engine.begin() as conn:
        as_role(conn, "ata_worker")
        purged = (
            conn.execute(text("SELECT run_id FROM apply_retention(now(), 200)")).scalars().all()
        )
    assert len(purged) == 1
    with sessions() as session:
        run = session.get(Run, purged[0])
        assert run.workspace_id == a and run.purged_at is not None
        assert session.query(Step).filter_by(run_id=run.id).count() == 0
        bug = session.query(Bug).filter_by(run_id=run.id).one()
        assert bug.screenshot is None
        other = session.query(Run).filter(Run.workspace_id == b).one()
        assert other.purged_at is None


# --- triggers -----------------------------------------------------------------------------------


def test_updated_at_is_maintained_by_the_database(db_engine, sessions, two):
    a, _ = two
    with sessions() as session:
        setup = LoginSetup(workspace_id=a, origin="http://shop.test", kind="form")
        session.add(setup)
        session.commit()
        first, setup_id = setup.updated_at, setup.id
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE login_setups SET username = 'u' WHERE id = :i"), {"i": setup_id})
    with sessions() as session:
        assert session.get(LoginSetup, setup_id).updated_at > first


def test_changes_to_audited_tables_are_logged_with_the_actor_and_no_secrets(
    db_engine, sessions, two
):
    a, _ = two
    user = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, email, workspace_id) VALUES (:u, 'x@example.com', :a)"),
            {"u": user, "a": a},
        )
    with db_engine.begin() as conn:
        as_role(conn, "ata_web", workspace=a, user=user)
        conn.execute(
            text(
                "INSERT INTO model_configs (workspace_id, label, provider, model, "
                "api_key_ciphertext) VALUES (:a, 'L', 'claude', 'm', 'v1:SECRET-CIPHERTEXT')"
            ),
            {"a": a},
        )
    with sessions() as session:
        [row] = session.query(AuditLog).filter_by(action="model.added").all()
        assert row.workspace_id == a and row.user_id == user
        assert "SECRET" not in str(row.metadata_)


def test_a_new_run_is_logged_as_started_with_the_request_metadata(db_engine, sessions, two):
    a, _ = two
    with db_engine.begin() as conn:
        as_role(conn, "ata_web", workspace=a)
        conn.execute(text("SELECT set_config('app.audit_metadata', '{\"ip\": \"1.2.3.4\"}', true)"))
        run_id = conn.execute(
            text(
                "INSERT INTO runs (workspace_id, target_url, mode) "
                "VALUES (:a, 'http://shop.test/', 'interactive') RETURNING id"
            ),
            {"a": a},
        ).scalar()
    with sessions() as session:
        row = session.query(AuditLog).filter_by(action="run.started", run_id=run_id).one()
        assert row.target_url == "http://shop.test/" and row.metadata_ == {"ip": "1.2.3.4"}


def test_a_false_positive_triage_follows_the_fingerprint_into_later_runs(db_engine, sessions, two):
    a, _ = two
    with sessions() as session:
        session.add(
            FindingTriage(workspace_id=a, origin="http://shop.test", fingerprint="fp-1",
                          state="false_positive", title="t")
        )  # fmt: skip
        later = Run(workspace_id=a, target_url="http://shop.test/cart", mode="interactive")
        elsewhere = Run(workspace_id=a, target_url="http://other.test/", mode="interactive")
        session.add_all([later, elsewhere])
        session.flush()
        for run in (later, elsewhere):
            session.add(
                Bug(run_id=run.id, title="t", severity="low", category="ux", page_url="/",
                    source="agent", status="confirmed", fingerprint="fp-1")
            )  # fmt: skip
        session.commit()
        later_id, elsewhere_id = later.id, elsewhere.id
    with sessions() as session:
        assert session.query(Bug).filter_by(run_id=later_id).one().suppressed is True
        assert session.query(Bug).filter_by(run_id=elsewhere_id).one().suppressed is False


# --- views ----------------------------------------------------------------------------------------


def test_bug_history_per_target_and_it_respects_tenants(db_engine, sessions, two):
    a, _ = two
    with sessions() as session:
        for bug in session.query(Bug):
            bug.fingerprint = "fp-x"
        session.commit()
    with db_engine.connect() as conn:
        as_role(conn, "ata_web", workspace=a)
        rows = conn.execute(text("SELECT * FROM target_bug_history")).all()
    assert len(rows) == 1
    assert rows[0].origin == "http://shop.test" and rows[0].runs_seen == 1


def test_the_leaderboard_refreshes_when_a_result_is_saved_and_skips_invalid_ones(
    db_engine, sessions
):
    with sessions() as session:
        session.add(BenchmarkResult(provider="ollama", model="m1", git_commit="abc", runs_buggy=3, recall=0.3,
                                    precision=1.0, false_alarms=0.0, avg_cost_usd=0.0, avg_duration_s=1.0, ai_recall=0.1,
                                    details={}))  # fmt: skip
        session.add(BenchmarkResult(provider="fake", model="fake", git_commit="abc", runs_buggy=3, recall=0.3,
                                    precision=1.0, false_alarms=0.0, avg_cost_usd=0.0, avg_duration_s=1.0, ai_recall=0.9,
                                    details={"invalid": "test run"}))  # fmt: skip
        session.commit()
    with db_engine.connect() as conn:
        rows = conn.execute(text("SELECT provider, model FROM model_leaderboard")).all()
    assert [(r.provider, r.model) for r in rows] == [("ollama", "m1")]


# --- constraints -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE runs SET cost_usd = -1",
        "UPDATE runs SET input_tokens = -5",
        "UPDATE runs SET max_steps = 0",
        "UPDATE workspaces SET retention_days = 0",
        "UPDATE workspaces SET monthly_run_quota = -1",
        "UPDATE bugs SET category = ''",
        "INSERT INTO login_setups (workspace_id, origin, kind) SELECT id, 'x', 'magic' FROM workspaces LIMIT 1",
        "INSERT INTO model_configs (workspace_id, label, provider, model) SELECT id, 'l', 'gpt', 'm' FROM workspaces LIMIT 1",
        "INSERT INTO model_configs (workspace_id, label, provider, model, input_price) SELECT id, 'l', 'claude', 'm', -1 FROM workspaces LIMIT 1",
    ],
)
def test_out_of_range_and_unknown_values_are_refused(db_engine, two, sql):
    with db_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(text(sql))
