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
