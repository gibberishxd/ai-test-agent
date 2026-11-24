"""The tools deep mode's model can call on the browser, as JSON schemas (the process tools that
save the map and plan and report bugs are the harness's: deep/harness.py).

Unlike the current loop's tools (one per step, `reasoning` on each, element numbers from a fixed
observation), these are general: the model asks for a snapshot or a screenshot when it wants
one, measures with JavaScript, and reads evidence since a mark. Everything still runs through
the worker's safety rules (deep/toolbox.py).
"""

from worker.llm.base import ToolSpec

REF = {
    "type": "integer",
    "description": "The [ref] of an element in your latest snapshot.",
}
SELECTOR = {
    "type": "string",
    "description": "A CSS selector for exactly one element, when no ref fits (use refs first).",
}
OFFSET = {"type": "integer", "minimum": 0, "description": "Character offset to read from."}
SINCE = {
    "type": "integer",
    "minimum": 0,
    "description": "A mark from an earlier tool result: only what happened after it. 0 = all.",
}


def _tool(name: str, description: str, required: tuple[str, ...] = (), **properties) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        },
    )


BROWSER_TOOLS = [
    # --- acting ---
    _tool(
        "navigate",
        "Load a URL on the site under test (a full page load: in-memory state may be lost).",
        ("url",),
        url={"type": "string", "description": "Absolute URL or a path like /cart."},
    ),
    _tool("click", "Click an element.", (), ref=REF, selector=SELECTOR),
    _tool(
        "type",
        "Replace the text in a field.",
        ("text",),
        ref=REF,
        selector=SELECTOR,
        text={"type": "string"},
    ),
    _tool(
        "select",
        "Choose an option in a dropdown by its visible label.",
        ("option",),
        ref=REF,
        selector=SELECTOR,
        option={"type": "string"},
    ),
    _tool(
        "press_key",
        "Press a key (Enter, Tab, Escape, ArrowDown, Shift+Tab...), on an element if given, "
        "else on whatever has focus.",
        ("key",),
        key={"type": "string"},
        ref=REF,
        selector=SELECTOR,
    ),
    _tool("hover", "Move the mouse over an element.", (), ref=REF, selector=SELECTOR),
    _tool(
        "scroll",
        "Scroll the page.",
        ("direction",),
        direction={"type": "string", "enum": ["up", "down"]},
        pixels={"type": "integer", "minimum": 1, "maximum": 5000},
    ),
    _tool(
        "set_viewport",
        "Resize the browser window to any width × height (for example 390×844, 768×1024, "
        "1440×900).",
        ("width", "height"),
        width={"type": "integer"},
        height={"type": "integer"},
    ),
    _tool("go_back", "Go back to the previous page."),
    # --- seeing ---
    _tool(
        "screenshot",
        "See the page as a picture (the visible part, or the whole page).",
        full_page={"type": "boolean"},
    ),
    _tool(
        "snapshot",
        "The page's accessibility tree, and its interactive elements with [ref] numbers to act "
        "on. Take a new one after the page changes: refs are only valid for the latest one.",
    ),
    _tool("visible_text", "The text a user can see on the page.", offset=OFFSET),
    # --- measuring ---
    _tool(
        "evaluate_js",
        "Run JavaScript in the page to MEASURE (computed styles, sizes, positions, contrast, "
        "focus, DOM state). The snippet is a function body; `return` a JSON value; `await` "
        "works. It must not change the page: requests that send data are blocked, and you are "
        "told if it changed the DOM. Use the browser tools to interact.",
        ("snippet",),
        snippet={"type": "string"},
    ),
    _tool(
        "page_source",
        "The HTML the server sent for this page (before scripts changed it), and the scripts "
        "it loaded.",
        offset=OFFSET,
    ),
    _tool(
        "read_script",
        "The source of a script this page loaded (see page_source for the list).",
        ("url",),
        url={"type": "string"},
        offset=OFFSET,
    ),
    # --- evidence ---
    _tool("console", "Console errors and warnings, and uncaught exceptions.", since=SINCE),
    _tool(
        "network",
        "Requests the page made: method, URL, status, type, time; failed ones too.",
        since=SINCE,
    ),
    # --- our deterministic checks ---
    _tool("run_axe", "Run the axe-core accessibility checks (WCAG A/AA) on the page as it is now."),
    _tool(
        "check_layout",
        "Measure the layout at the current viewport: horizontal overflow, elements sticking "
        "out, small tap targets and small text.",
    ),
    _tool("check_meta", "Check the page's metadata: Open Graph, twitter:card, canonical, icons."),
    _tool(
        "keyboard_probe",
        "Click a control that opens a dialog, menu or disclosure, then test the open thing "
        "with the keyboard (focus, Tab, Escape, ARIA state).",
        (),
        ref=REF,
        selector=SELECTOR,
    ),
]

BROWSER_TOOL_NAMES = {tool.name for tool in BROWSER_TOOLS}


# --- the process tools: the harness runs these (deep/harness.py) --------------------------------

STEPS = {"type": "array", "items": {"type": "integer"}}
VERIFY = {
    "type": "object",
    "description": "How to check this bug in a fresh browser. kind=replay: `steps`, the step "
    "numbers of the browser actions that reproduce it from the start page. kind=measure: a "
    "`snippet` that returns the wrong value, and `setup_steps` that reach the state to measure. "
    "kind=check: `check` (run_axe, check_layout, check_meta) and the `rule` it reports, with "
    "`setup_steps`; or check=keyboard_probe with the probe's `step` and the failed check as "
    "`rule`.",
    "properties": {
        "kind": {"type": "string", "enum": ["replay", "measure", "check"]},
        "steps": STEPS,
        "snippet": {"type": "string"},
        "setup_steps": STEPS,
        "check": {
            "type": "string",
            "enum": ["run_axe", "check_layout", "check_meta", "keyboard_probe"],
        },
        "rule": {"type": "string"},
        "step": {"type": "integer"},
    },
    "required": ["kind"],
}

PROCESS_TOOLS = [
    _tool(
        "save_map",
        "Record your map of the app: its pages, its flows, and what it is for.",
        ("pages", "flows", "summary"),
        pages={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"url": {"type": "string"}, "purpose": {"type": "string"}},
                "required": ["url", "purpose"],
            },
        },
        flows={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
                "required": ["name", "description"],
            },
        },
        summary={"type": "string"},
    ),
    _tool(
        "save_plan",
        "Record your test plan: concrete items, each in a checklist area; mark an area not "
        "applicable only with a reason.",
        ("items",),
        items={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "area": {"type": "string"},
                    "description": {"type": "string"},
                    "viewport": {"type": "string", "description": "For layout items: WxH."},
                },
                "required": ["id", "area", "description"],
            },
        },
        not_applicable={
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"area": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["area", "reason"],
            },
        },
    ),
    _tool(
        "tick",
        "Mark a plan item as done, skipped or blocked, with a short note.",
        ("item_id", "status", "note"),
        item_id={"type": "string"},
        status={"type": "string", "enum": ["done", "skipped", "blocked"]},
        note={"type": "string"},
    ),
    _tool(
        "flag_candidate",
        "Note something that looks wrong, before you try to disprove it. Returns its id.",
        ("title", "observation"),
        title={"type": "string"},
        observation={"type": "string", "description": "What you saw, with concrete values."},
    ),
    _tool(
        "drop_candidate",
        "Close a candidate that turned out not to be a bug, saying why.",
        ("candidate_id", "reason"),
        candidate_id={"type": "string"},
        reason={"type": "string"},
    ),
    _tool(
        "report_bug",
        "Report a candidate as a bug, after re-checking it. One bug per report.",
        (
            "candidate_id",
            "title",
            "severity",
            "category",
            "expected",
            "actual",
            "self_review",
            "verify",
        ),
        candidate_id={"type": "string"},
        title={"type": "string", "description": "Short and specific, like a ticket title."},
        severity={"type": "string", "enum": ["critical", "high", "medium", "low"]},
        category={
            "type": "string",
            "enum": [
                "functional",
                "validation",
                "ux",
                "visual",
                "layout",
                "accessibility",
                "content",
                "performance",
                "security",
                "seo",
                "other",
            ],
        },
        expected={"type": "string"},
        actual={"type": "string", "description": "What happened, with concrete values."},
        steps_to_reproduce={"type": "array", "items": {"type": "string"}},
        self_review={
            "type": "string",
            "description": "How you tried to disprove it, and why it is still a bug.",
        },
        verify=VERIFY,
    ),
    _tool(
        "finish",
        "End the run: every plan item ticked, every candidate resolved, screenshots seen at "
        "every viewport.",
        ("summary",),
        summary={"type": "string"},
    ),
]

PROCESS_TOOL_NAMES = {tool.name for tool in PROCESS_TOOLS}
ALL_TOOLS = BROWSER_TOOLS + PROCESS_TOOLS
