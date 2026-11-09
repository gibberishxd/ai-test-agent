"""The JSON shapes the web app reads, exported as JSON Schema.

`uv run python -m worker.contracts` writes apps/web/lib/contracts/schema.json. The web app keeps
TypeScript types for the same shapes, and tests on both sides compare against this file, so a
change on one side that isn't made on the other fails a test instead of breaking the UI.
"""

import json
from pathlib import Path

from pydantic import TypeAdapter

from worker.config import REPO_ROOT
from worker.report import BugReport, Report

SCHEMA_PATH = REPO_ROOT / "apps" / "web" / "lib" / "contracts" / "schema.json"


def build_schema() -> dict:
    return {
        "BugReport": TypeAdapter(BugReport).json_schema(),
        "Report": TypeAdapter(Report).json_schema(),
    }


def render() -> str:
    return json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"


def write(path: Path = SCHEMA_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    write()
    print(f"wrote {SCHEMA_PATH}")
