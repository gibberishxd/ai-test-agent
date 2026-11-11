"""Expected vs. actual: the check that turns "I acted" into "did it do the right thing?".

Before a state-changing action the model writes one line of what it expects (`expect`). After
it, the worker records what actually changed (`Effect`) and compares the two without another
model call (`mismatches`):

- the model expected a change, but nothing on the page changed;
- a value it predicted (an amount, a number, quoted text, a path) is nowhere on the page, in the
  fields or in the URL.

A mismatch becomes a candidate bug that the model must report or dismiss with a reason. The
comparison is deliberately simple and generic: it knows nothing about any site, and when it is
wrong the model dismisses the candidate in one step.
"""

import re
from dataclasses import dataclass, field

# Actions whose result can be right or wrong. Typing changes only the field typed into, scrolling
# and navigating change what is shown, not the site's state, so they don't need an expectation.
EXPECT_ACTIONS = {"click", "double_click", "select", "reload", "set_viewport"}
# While a candidate is open, only these actions are allowed (they resolve it or don't act).
RESOLVING_ACTIONS = {"report_bug", "dismiss", "finish", "note", "take_screenshot"}

MAX_DESCRIPTION = 400
MAX_LINES = 4

DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")
QUOTED = re.compile(r"'([^']{3,80})'|\"([^\"]{3,80})\"|“([^”]{3,80})”")
PATH = re.compile(r"(?<![\w/.])(/[a-z0-9][\w\-/]*)", re.IGNORECASE)
NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")
NEGATED = re.compile(r"\b(not|no|never|instead of|isn'?t|shouldn'?t|without|rather than)\s+$")
NO_CHANGE = re.compile(
    r"\b(nothing|unchanged|no (visible )?change|stays?\b|remains?\b|same as before|the same|"
    r"(does not|doesn'?t|not) change)",
    re.IGNORECASE,
)


@dataclass
class Effect:
    """What an action changed: URL, text lines, field values, console and network events."""

    url_before: str
    url_after: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)  # "Quantity: 0 → 1"
    events: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.url_after != self.url_before or self.added or self.removed or self.fields)

    def describe(self) -> str:
        if not self.changed and not self.events:
            return "nothing on the page changed"
        parts = []
        if self.url_after != self.url_before:
            parts.append(f"now on {self.url_after}")
        if self.added:
            parts.append("new: " + " | ".join(self.added[:MAX_LINES]))
        if self.removed:
            parts.append("gone: " + " | ".join(self.removed[:MAX_LINES]))
        if self.fields:
            parts.append("fields: " + " | ".join(self.fields[:MAX_LINES]))
        if self.events:
            parts.append("; ".join(self.events[:2]))
        text = "; ".join(parts)
        return text if len(text) <= MAX_DESCRIPTION else text[: MAX_DESCRIPTION - 1] + "…"


def expected_values(expectation: str) -> list[str]:
    """The concrete values the model predicted, in order: quoted text, paths, amounts, numbers.

    Values right after a negation ("not $12") aren't expected. Dates are skipped: a site shows
    them in its own format, so a missing "2027-02-01" says nothing.
    """
    found: list[tuple[int, str]] = []
    taken = [False] * len(expectation)

    def keep(start: int, end: int, value: str) -> None:
        if any(taken[start:end]):
            return
        for i in range(start, end):
            taken[i] = True
        if not NEGATED.search(expectation[:start]):
            found.append((start, value))

    for match in DATE.finditer(expectation):
        for i in range(match.start(), match.end()):
            taken[i] = True
    for match in QUOTED.finditer(expectation):
        value = next(group for group in match.groups() if group)
        keep(match.start(), match.end(), value)
    for match in PATH.finditer(expectation):
        keep(match.start(1), match.end(1), match.group(1))
    for match in NUMBER.finditer(expectation):
        keep(match.start(), match.end(), match.group().rstrip(","))
    return [value for _, value in sorted(found)]


def mismatches(
    expectation: str, effect: Effect, page_text: str, field_values: dict[str, str]
) -> list[str]:
    """Why what happened doesn't look like what the model expected (empty: no mismatch)."""
    expectation = (expectation or "").strip()
    if not expectation:
        return []
    if NO_CHANGE.search(expectation):
        return []  # the model expected nothing to change: whatever it sees, it judges itself
    if not effect.changed:
        return ["you expected a change, but nothing on the page changed"]
    haystack = " ".join([page_text, effect.url_after, *field_values.values()])
    return [
        f"{value} is not on the page"
        for value in expected_values(expectation)
        if not _present(value, haystack)
    ]


def _present(value: str, haystack: str) -> bool:
    if NUMBER.fullmatch(value):
        wanted = _number(value)
        return any(_number(found) == wanted for found in NUMBER.findall(haystack))
    return value.lower() in haystack.lower()


def _number(text: str) -> float | None:
    try:
        return float(text.strip("$%").replace(",", ""))
    except ValueError:
        return None


@dataclass
class Candidate:
    """A mismatch the model has to resolve: report it, or dismiss it with a reason."""

    step: int
    expected: str
    happened: str
    flags: list[str]
    blocked_once: bool = False

    def describe(self) -> str:
        return (
            f"- #{self.step}: you expected: {self.expected} | happened: {self.happened} | "
            f"why: {'; '.join(self.flags)}"
        )
