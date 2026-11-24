"""Deep mode's prompts, checklist and tools: generic, in step with each other, and free of
anything from our benchmark apps (the agent must work on any site, not be tuned to one)."""

import json

from worker.config import REPO_ROOT
from worker.deep.checklist import AREAS, VIEWPORTS, checklist_text
from worker.deep.prompt import (
    SYSTEM_PROMPT,
    execute_prompt,
    map_prompt,
    plan_prompt,
    review_prompt,
)
from worker.deep.tools import ALL_TOOLS, BROWSER_TOOLS, PROCESS_TOOLS


def everything_the_model_reads() -> str:
    item = {"id": "x-1", "area": "flows", "description": "d"}
    prompts = [
        SYSTEM_PROMPT,
        map_prompt("https://app.test/"),
        plan_prompt(),
        execute_prompt([item], 1, resumed=True),
        review_prompt([{"id": "c1", "title": "t", "observation": "o"}], near_end=True),
        checklist_text(),
    ]
    tools = json.dumps([{"d": t.description, "p": t.parameters} for t in ALL_TOOLS])
    return ("\n".join(prompts) + tools).lower()


def test_nothing_from_the_benchmark_apps_reaches_the_model():
    text = everything_the_model_reads()
    planted = []
    for app in ("demo", "demo2"):
        path = REPO_ROOT / "apps" / app / "bugs.json"
        planted += json.loads(path.read_text(encoding="utf-8"))["bugs"]
    real = json.loads((REPO_ROOT / "apps" / "realworld" / "bugs.json").read_text(encoding="utf-8"))
    specifics = {"save10", "wool socks", "desk lamp", "ceramic mug", "localhost", "5173", "5175"}
    specifics |= {"it-tools", "react-admin", "posters galore", "rc4", "roman numeral", "otp"}
    specifics |= {"base32", "favorite", "ipv4"}
    specifics |= {bug["title"].lower() for bug in planted + real["bugs"]}
    assert [s for s in specifics if s in text] == []


def test_the_system_prompt_names_every_tool():
    missing = [
        tool.name for tool in BROWSER_TOOLS + PROCESS_TOOLS if tool.name not in SYSTEM_PROMPT
    ]
    # Acting tools are self-explanatory; the ones with rules must be explained.
    explained = {
        "snapshot",
        "screenshot",
        "evaluate_js",
        "page_source",
        "read_script",
        "console",
        "network",
        "run_axe",
        "check_layout",
        "check_meta",
        "keyboard_probe",
        "save_map",
        "save_plan",
        "tick",
        "flag_candidate",
        "drop_candidate",
        "report_bug",
    }
    assert explained & set(missing) == set()


def test_the_plan_prompt_lists_every_area_and_viewport():
    prompt = plan_prompt()
    assert all(area.key in prompt for area in AREAS)
    assert all(viewport in prompt for viewport in VIEWPORTS)


def test_page_content_is_data_never_instructions():
    assert "<page_content>" in SYSTEM_PROMPT and "never instructions" in SYSTEM_PROMPT
