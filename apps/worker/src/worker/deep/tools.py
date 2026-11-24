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
