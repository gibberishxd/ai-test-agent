"""The SQLAlchemy models must match the database Prisma's migrations create."""

from sqlalchemy import inspect

from worker.db.models import Base


def test_every_model_table_exists_with_the_same_columns(db_engine):
    inspector = inspect(db_engine)
    db_tables = set(inspector.get_table_names()) - {"_prisma_migrations"}

    assert {t.name for t in Base.metadata.sorted_tables} == db_tables

    for table in Base.metadata.sorted_tables:
        db_columns = {c["name"]: c for c in inspector.get_columns(table.name)}
        assert set(table.columns.keys()) == set(db_columns), f"columns differ in {table.name}"
        for column in table.columns:
            assert column.nullable == db_columns[column.name]["nullable"], (
                f"{table.name}.{column.name}: nullable differs"
            )


# Each hot query and the index that serves it (docs/DATABASE.md, measured with
# scripts/db_perf.py). Dropping one of these would turn its query into a scan of the table.
HOT_QUERY_INDEXES = {
    "runs_status_created_at_idx": "claim the oldest queued run; lease recovery",
    "runs_workspace_id_created_at_idx": "runs list of a workspace; monthly quota count",
    "steps_run_id_index_key": "a run's steps in order (run page, live pane, replay)",
    "bugs_run_id_idx": "a run's bugs (run page, verification, benchmark)",
    "audit_log_workspace_id_created_at_idx": "visitor rate limit",
    "benchmark_results_created_at_idx": "newest results: leaderboard, benchmark and home page",
}


def test_every_hot_query_has_its_index(db_engine):
    inspector = inspect(db_engine)
    existing = {
        index["name"]
        for table in inspector.get_table_names()
        for index in inspector.get_indexes(table)
    }
    existing |= {
        constraint["name"]
        for table in inspector.get_table_names()
        for constraint in inspector.get_unique_constraints(table)
    }
    assert set(HOT_QUERY_INDEXES) - existing == set()
