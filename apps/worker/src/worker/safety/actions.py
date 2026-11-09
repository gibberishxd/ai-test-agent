"""Safety rule 6.2: in passive mode the worker only looks; it never types, selects or submits.

Checked by the worker before executing any action, whatever the model asked for.
"""

from dataclasses import dataclass

from worker.db.models import RunMode

# Actions that can't change anything on the target site.
READ_ONLY_ACTIONS = {"navigate", "go_back", "scroll", "take_screenshot", "report_bug", "finish"}


@dataclass(frozen=True)
class ElementInfo:
    """What the worker knows about an element before acting on it."""

    role: str
    name: str = ""
    tag: str = ""
    href: str | None = None
    input_type: str | None = None  # e.g. "submit" for <input type=submit>
    form_action: str | None = None  # the action URL of the enclosing form, if any

    @property
    def is_plain_link(self) -> bool:
        return self.role == "link" and bool(self.href) and self.input_type != "submit"


def check_mode(mode: str, action: str, element: ElementInfo | None = None) -> str | None:
    """None if `action` is allowed in `mode`, otherwise the reason it's blocked."""
    if mode == RunMode.INTERACTIVE:
        return None
    if action in READ_ONLY_ACTIONS:
        return None
    if action == "click" and element is not None and element.is_plain_link:
        return None
    what = f"click on {element.role} '{element.name}'" if action == "click" and element else action
    return f"passive mode: {what} is not allowed (only links can be clicked)"
