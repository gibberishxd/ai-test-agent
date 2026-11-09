from worker.contracts import SCHEMA_PATH, render


def test_committed_schema_is_up_to_date():
    # If this fails, a report model changed: run `uv run python -m worker.contracts`, then
    # update the TypeScript types in apps/web/lib/contracts to match.
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render()
