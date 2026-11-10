"""The system prompt: generic QA guidance, in step with the tools, identical on every step."""

import json

from worker.agent.prompt import SYSTEM_PROMPT
from worker.agent.tools import TOOLS
from worker.config import REPO_ROOT


def test_prompt_mentions_every_tool_by_name():
    missing = [tool.name for tool in TOOLS if tool.name not in SYSTEM_PROMPT]
    assert missing == []


def test_prompt_covers_the_test_charter():
    for technique in (
        "boundary",
        "invalid",
        "next to the right field",
        "arithmetic",
        "double_click",
        "reload",
        "mobile",
        "did nothing",
        "note",
    ):
        assert technique in SYSTEM_PROMPT.lower(), technique


def test_prompt_and_tools_know_nothing_about_the_demo_apps():
    # The agent must work on any site: nothing from our own test apps may leak into it.
    text = (SYSTEM_PROMPT + json.dumps([t.description for t in TOOLS])).lower()
    planted = []
    for app in ("demo", "demo2"):
        path = REPO_ROOT / "apps" / app / "bugs.json"
        if path.exists():
            planted += json.loads(path.read_text(encoding="utf-8"))["bugs"]
    assert planted, "bugs.json not found"
    # Names, codes and addresses from our apps. (Generic bad values such as "NaN" are fine:
    # every tester looks for those.)
    specifics = {"save10", "wool socks", "desk lamp", "ceramic mug", "localhost", "5173", "5175"}
    specifics |= {bug["title"].lower() for bug in planted}
    assert [s for s in specifics if s in text] == []
