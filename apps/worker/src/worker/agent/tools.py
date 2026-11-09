"""The tools the model can call. Exactly one per step.

Every tool takes `reasoning`: one sentence on why, shown in the run timeline. All parameters are
required (strict tool schemas need that), so optional values are passed as empty strings.
"""

from worker.llm import ToolSpec

REASONING = {"type": "string", "description": "One short sentence: why this action, now."}
ELEMENT_ID = {"type": "integer", "description": "The [id] of an element in the observation."}


def _tool(name: str, description: str, **properties) -> ToolSpec:
    props = {**properties, "reasoning": REASONING}
    return ToolSpec(
        name=name,
        description=description,
        parameters={"type": "object", "properties": props, "required": list(props)},
    )


TOOLS = [
    _tool("click", "Click an element (link, button, checkbox...).", element_id=ELEMENT_ID),
    _tool(
        "type",
        "Replace the text in an input field.",
        element_id=ELEMENT_ID,
        text={"type": "string", "description": "The text to put in the field."},
    ),
    _tool(
        "select",
        "Choose an option in a dropdown.",
        element_id=ELEMENT_ID,
        option={"type": "string", "description": "The option's visible label."},
    ),
    _tool(
        "navigate",
        "Load a URL on the site under test (a full page load: in-memory state such as a cart "
        "may be lost, so prefer clicking links).",
        url={"type": "string", "description": "Absolute URL or a path like /cart."},
    ),
    _tool("go_back", "Go back to the previous page."),
    _tool("scroll", "Scroll the page.", direction={"type": "string", "enum": ["up", "down"]}),
    _tool("take_screenshot", "Get a screenshot of the current page with the next observation."),
    _tool(
        "report_bug",
        "Report a bug you have observed. Only report what you actually saw happen.",
        title={"type": "string", "description": "Short and specific, like a bug ticket title."},
        severity={"type": "string", "enum": ["critical", "high", "medium", "low"]},
        category={
            "type": "string",
            "enum": ["functional", "validation", "ux", "visual", "layout", "security", "other"],
        },
        expected={"type": "string", "description": "What should have happened."},
        actual={"type": "string", "description": "What actually happened."},
        step_ids={
            "type": "array",
            "items": {"type": "integer"},
            "description": "The #step numbers that reproduce the bug, in order.",
        },
        evidence={"type": "string", "description": "What you saw: values, messages, errors."},
    ),
    _tool(
        "finish",
        "End the run when the important flows are covered or nothing useful is left to try.",
        summary={"type": "string", "description": "What you tested and what you found."},
    ),
]

TOOL_NAMES = {tool.name for tool in TOOLS}
