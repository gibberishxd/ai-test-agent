"""Query plans of the hot queries on realistic volume, in a throwaway database.

    cd apps/worker && uv run python scripts/db_perf.py            # timings table
    cd apps/worker && uv run python scripts/db_perf.py --plans    # plus every full plan

Creates `agent_perf` next to the app's database (dropped and rebuilt each time; the app's own
data is never touched), applies the real Prisma migrations, seeds 10k runs (40% in one big
workspace), 500k steps (a run's live timeline: 50 per run), 50k bugs, 10k audit rows and 2k
benchmark results, runs ANALYZE, then EXPLAIN (ANALYZE, BUFFERS) on each query the app runs
often. Each query runs 7 times; the median execution time is reported. docs/DATABASE.md
records the results and which indexes they led to.
"""

import statistics
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from worker.config import Settings

PERF_DB = "agent_perf"
MIGRATIONS = Path(__file__).resolve().parents[2] / "web" / "prisma" / "migrations"
REPEAT = 7

SEED = """
INSERT INTO workspaces (name, slug)
SELECT 'Workspace ' || n, 'ws-' || n FROM generate_series(1, 50) AS n;

-- 10k runs over three weeks, newest first. 40% belong to ws-1 (the big customer). A few are
-- queued or running, the rest finished, as in a real queue.
INSERT INTO runs (workspace_id, target_url, mode, status, created_at, started_at, finished_at,
                  heartbeat_at, step_count)
SELECT CASE WHEN i % 10 < 4 THEN (SELECT id FROM workspaces WHERE slug = 'ws-1')
            ELSE (SELECT id FROM workspaces WHERE slug = 'ws-' || (2 + i % 49)) END,
       'https://shop-' || (i % 300) || '.example.com/',
       CASE WHEN i % 3 = 0 THEN 'interactive'::run_mode ELSE 'passive'::run_mode END,
       CASE WHEN i < 20 THEN 'queued'::run_status
            WHEN i < 25 THEN 'running'::run_status
            WHEN i % 17 = 0 THEN 'failed'::run_status
            ELSE 'done'::run_status END,
       now() - i * interval '3 minutes',
       CASE WHEN i >= 20 THEN now() - i * interval '3 minutes' + interval '5 seconds' END,
       CASE WHEN i >= 25 THEN now() - i * interval '3 minutes' + interval '8 minutes' END,
       CASE WHEN i BETWEEN 20 AND 24 THEN now() - interval '5 seconds' END,
       50
FROM generate_series(0, 9999) AS i;

-- 50 steps per run: what the live page and the live pane poll.
INSERT INTO steps (run_id, index, action, args, url, screenshot, events, created_at)
SELECT r.id, s,
       (ARRAY['visit','click','type','navigate','scroll','report_bug'])[1 + s % 6],
       jsonb_build_object('element', jsonb_build_object('role', 'button', 'name', 'Add to cart',
                          'css', '#root > main > ul > li:nth-of-type(3) > button'),
                          'result', 'ok; new on the page: Cart (0) → (1)',
                          'box', jsonb_build_object('x', 10, 'y', 20, 'width', 80, 'height', 30)),
       r.target_url || 'page/' || s,
       r.id || '/agent-' || lpad(s::text, 3, '0') || '.png',
       '[{"type": "console", "text": "TypeError: Cannot read properties of undefined"}]',
       r.created_at + s * interval '5 seconds'
FROM runs r CROSS JOIN generate_series(0, 49) AS s;

INSERT INTO bugs (run_id, title, severity, category, page_url, source, status, evidence,
                  created_at)
SELECT r.id, 'Bug ' || b || ' on ' || r.target_url,
       (ARRAY['critical','high','medium','low'])[1 + b % 4]::severity, 'functional',
       r.target_url, (CASE WHEN b < 2 THEN 'deterministic' ELSE 'agent' END)::bug_source,
       (CASE WHEN b = 4 THEN 'dismissed' ELSE 'confirmed' END)::bug_status,
       '{"replay": "the total is wrong"}', r.created_at + b * interval '1 minute'
FROM runs r CROSS JOIN generate_series(0, 4) AS b;

INSERT INTO audit_log (workspace_id, action, metadata, created_at)
SELECT workspace_id, 'run.started', jsonb_build_object('ip', '10.0.' || (i % 250) || '.1'),
       created_at
FROM (SELECT workspace_id, created_at, row_number() OVER () AS i FROM runs) AS r;

INSERT INTO benchmark_results (provider, model, git_commit, runs_buggy, recall, precision,
                               false_alarms, avg_cost_usd, avg_duration_s, details, created_at)
SELECT (ARRAY['ollama','claude','openai-compat'])[1 + i % 3], 'model-' || (i % 20), 'abc1234',
       3, 0.4, 1.0, 0.0, 0.0, 500,
       jsonb_build_object('decisions', (SELECT jsonb_agg(jsonb_build_object('report', 'r' || d,
                          'matched', d, 'reason', repeat('x', 80))) FROM generate_series(1, 20) d)),
       now() - i * interval '1 hour'
FROM generate_series(1, 2000) AS i;

ANALYZE;
"""

# Filled in with literal ids before measuring, as the app passes them (bound parameters).
BIG = "'{big}'"
A_RUN = "'{run}'"

QUERIES = {
    "claim the next run (worker, every second per worker)": """
        SELECT * FROM runs WHERE status = 'queued' ORDER BY created_at LIMIT 1
        FOR UPDATE SKIP LOCKED""",
    "run page: the run (web, every 1.5 s while open)": f"""
        SELECT * FROM runs WHERE id = {A_RUN} AND workspace_id = {BIG}""",
    "run page / live pane: its steps": f"""
        SELECT * FROM steps WHERE run_id = {A_RUN} ORDER BY index""",
    "run page: its bugs": f"""
        SELECT * FROM bugs WHERE run_id = {A_RUN} ORDER BY created_at""",
    "runs list of a workspace (newest 50)": f"""
        SELECT * FROM runs WHERE workspace_id = {BIG} ORDER BY created_at DESC LIMIT 50""",
    "quota: runs this month (start run)": f"""
        SELECT count(*) FROM runs
        WHERE workspace_id = {BIG} AND created_at >= date_trunc('month', now())""",
    "visitor limit: runs from this IP in the last hour": f"""
        SELECT count(*) FROM audit_log
        WHERE workspace_id = {BIG} AND action = 'run.started'
          AND created_at >= now() - interval '1 hour' AND metadata #>> '{{ip}}' = '10.0.7.1'""",
    "lease recovery: running runs with an expired lease": """
        SELECT id FROM runs WHERE status = 'running'
          AND coalesce(heartbeat_at, started_at) < now() - interval '60 seconds'""",
    "leaderboard / benchmark page (newest 200 results)": """
        SELECT * FROM benchmark_results ORDER BY created_at DESC LIMIT 200""",
    "home page: newest benchmark result": """
        SELECT * FROM benchmark_results ORDER BY created_at DESC LIMIT 1""",
}


def build(admin_url) -> None:
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {PERF_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {PERF_DB}"))
    admin.dispose()


# Run 4, J5: the queries a member's page runs, measured as the owner and as app_tenant (RLS on).
RLS_QUERIES = [
    "run page: the run (web, every 1.5 s while open)",
    "run page / live pane: its steps",
    "run page: its bugs",
    "runs list of a workspace (newest 50)",
]


def measure(conn, sql: str, tenant: str | None = None) -> tuple[float, str]:
    """Median execution time (ms) over REPEAT runs, and the plan of the last one.

    `tenant`: run as app_tenant with app.workspace_id set, i.e. with row-level security."""
    times, plan = [], ""
    for _ in range(REPEAT):
        if tenant:
            conn.execute(text("SELECT set_config('app.workspace_id', :w, true)"), {"w": tenant})
            conn.execute(text("SET LOCAL ROLE app_tenant"))
        rows = conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}")).scalars().all()
        plan = "\n".join(rows)
        times.append(float(rows[-1].split(":")[1].split("ms")[0]))
        conn.rollback()  # FOR UPDATE takes locks: release them between repeats
    return statistics.median(times), plan


def top_node(plan: str) -> str:
    """The first plan line that reads a table or index (what the query really does)."""
    for line in plan.splitlines():
        stripped = line.strip().lstrip("->").strip()
        if " on " in stripped or stripped.startswith(("Seq Scan", "Index", "Bitmap")):
            return stripped.split("  (")[0]
    return plan.splitlines()[0].split("  (")[0]


def main() -> None:
    show_plans = "--plans" in sys.argv  # --rls: also measure with row-level security
    admin_url = Settings().sqlalchemy_url()
    build(admin_url)
    engine = create_engine(make_url(admin_url).set(database=PERF_DB))
    with engine.begin() as conn:
        for sql_file in sorted(MIGRATIONS.glob("*/migration.sql")):
            conn.exec_driver_sql(sql_file.read_text().replace("%", "%%"))  # % is a placeholder
        conn.exec_driver_sql(SEED.replace("%", "%%"))  # % is a placeholder for the driver
    with engine.connect() as conn:
        counts = {
            t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar()
            for t in ("runs", "steps", "bugs", "audit_log", "benchmark_results")
        }
        print("seeded:", ", ".join(f"{t} {n:,}" for t, n in counts.items()))
        print()
        print("| Query | Median ms | Plan |")
        print("|---|---|---|")
        big = conn.execute(text("SELECT id FROM workspaces WHERE slug = 'ws-1'")).scalar()
        run = conn.execute(
            text("SELECT id FROM runs WHERE workspace_id = :w ORDER BY created_at DESC LIMIT 1"),
            {"w": big},
        ).scalar()
        plans = {}
        for name, sql in QUERIES.items():
            ms, plan = measure(conn, sql.replace("{big}", str(big)).replace("{run}", str(run)))
            plans[name] = plan
            print(f"| {name} | {ms:.3f} | {top_node(plan)} |")
    if "--rls" in sys.argv:
        with engine.connect() as conn:
            print()
            print("| Query (row-level security) | Owner ms | app_tenant ms | Plan with RLS |")
            print("|---|---|---|---|")
            for name in RLS_QUERIES:
                sql = QUERIES[name].replace("{big}", str(big)).replace("{run}", str(run))
                plain, _ = measure(conn, sql)
                rls, rls_plan = measure(conn, sql, tenant=str(big))
                plans[name + " (RLS)"] = rls_plan
                print(f"| {name} | {plain:.3f} | {rls:.3f} | {top_node(rls_plan)} |")
    if show_plans:
        for name, plan in plans.items():
            print(f"\n== {name}\n{plan}")
    engine.dispose()


if __name__ == "__main__":
    main()
