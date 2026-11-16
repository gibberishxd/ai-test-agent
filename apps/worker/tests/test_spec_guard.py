"""Run 7, M3: the holdout specs must state requirements, never copy a planted bug.

The owner writes apps/demo2/specs.md as a QA engineer would, from the app's intended behaviour.
A spec line that closely matches a planted bug's title or description (word overlap, see
specs.too_close) would hand the agent the answer, so it fails here. The template, which only
names pages and features, is checked too.
"""

import json
from pathlib import Path

import pytest

from worker.config import REPO_ROOT
from worker.specs import too_close

SPEC_FILES = [
    REPO_ROOT / "apps" / "demo2" / "specs.md",
    REPO_ROOT / "docs" / "specs" / "TEMPLATE.md",
]


def planted_texts() -> list[str]:
    texts = []
    for app in ("demo", "demo2"):
        for bug in json.loads((REPO_ROOT / "apps" / app / "bugs.json").read_text())["bugs"]:
            texts += [bug["title"], bug["description"], bug.get("how_to_detect", "")]
    return [t for t in texts if t]


@pytest.mark.parametrize("path", SPEC_FILES, ids=lambda p: p.name)
def test_no_spec_line_copies_a_planted_bug(path: Path):
    if not path.exists():
        pytest.skip(f"{path.relative_to(REPO_ROOT)} isn't written yet")
    planted = planted_texts()
    copied = [line for line in path.read_text().splitlines() if too_close(line, planted)]
    assert copied == [], "these spec lines read like planted bugs; state the requirement instead"


def test_the_guard_catches_a_copied_bug():
    [bug] = [
        b
        for b in json.loads((REPO_ROOT / "apps/demo2/bugs.json").read_text())["bugs"]
        if b["id"] == 3
    ]
    assert too_close(f"- {bug['title']}", planted_texts())
