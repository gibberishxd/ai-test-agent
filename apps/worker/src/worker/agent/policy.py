"""Rules checked by the worker before and between agent actions. The model can't skip them.

- Safe mode (rule 6.3, always on): a deny list for destructive or outward-facing actions.
- Test data: real-looking card numbers are only allowed on our demo shop.
- Budgets (rule 6.5 / brief 5.2): steps, wall-clock time, cost, and loop detection.
"""

import json
import re
import time
from dataclasses import dataclass, field

from worker.safety.actions import ElementInfo

# Checked against an element's text, link URL and form action before every click or submit.
DENY_PATTERNS = [
    r"\bpay\b",
    r"\bpurchase\b",
    r"\bdelete\b",
    r"\bremove (my )?account\b",
    r"\bunsubscribe\b",
    r"\bchange (your |my )?password\b",
    r"\bchange (your |my )?e-?mail\b",
    r"\bsend\b",
    r"\btransfer\b",
]
BUY_PATTERN = r"\bbuy\b"  # allowed only on our demo shop
CARD_NUMBER = re.compile(r"^\d{13,19}$")


def deny_reason(element: ElementInfo, allow_buy: bool) -> str | None:
    """None if clicking `element` is allowed, otherwise why safe mode refuses it."""
    patterns = DENY_PATTERNS if allow_buy else [*DENY_PATTERNS, BUY_PATTERN]
    fields = {"text": element.name, "link": element.href, "form action": element.form_action}
    for label, value in fields.items():
        if not value:
            continue
        for pattern in patterns:
            if re.search(pattern, value, flags=re.IGNORECASE):
                word = pattern.replace(r"\b", "").replace("(my )?", "").replace("(your |my )?", "")
                return f"safe mode: element {label} matches '{word}'"
    return None


def card_number_reason(text: str, is_demo_target: bool) -> str | None:
    """Payment card numbers may only be typed on the demo shop (the 4242… test card)."""
    digits = re.sub(r"[\s-]", "", text)
    if CARD_NUMBER.match(digits) and not is_demo_target:
        return "test data: card numbers can only be entered on the demo shop"
    return None


@dataclass
class Budget:
    """Hard limits for one run, enforced by the worker."""

    max_steps: int
    max_seconds: float
    max_cost_usd: float
    max_repeats: int = 3  # the same action this often in a row, changing nothing, is a loop
    started: float = field(default_factory=time.monotonic)
    steps: int = 0
    cost_usd: float = 0.0
    _last_action: str = ""
    _same: int = 0  # how many times in a row the last action was chosen
    _idle: int = 0  # how many of the latest of those changed nothing on the page

    def exhausted(self) -> str | None:
        """Why the run must stop now, or None."""
        if self.steps >= self.max_steps:
            return f"step budget reached ({self.max_steps} steps)"
        if time.monotonic() - self.started >= self.max_seconds:
            return f"time budget reached ({self.max_seconds:.0f} s)"
        if self.cost_usd >= self.max_cost_usd:
            return f"cost budget reached (${self.max_cost_usd:.2f})"
        return None

    @property
    def max_same(self) -> int:
        """The same action this often in a row is a loop even if the page changes each time."""
        return self.max_repeats * 2

    def repeating(self) -> bool:
        """True when repeating the last action once more would end the run."""
        return self._idle == self.max_repeats - 1 or self._same == self.max_same - 1

    def record(self, action: str, args: dict, cost_usd: float, changed: bool = False) -> str | None:
        """Count one step; return a reason to stop if the agent is stuck in a loop.

        `changed`: did the action change the page? Repeating an action that works (clicking
        "+" three times) is testing, so only repeats without effect count, up to `max_repeats`.
        `max_same` catches the other loop: "Add to cart" forever, changing the page every time.
        """
        self.steps += 1
        self.cost_usd += cost_usd
        key = action + json.dumps(
            {k: v for k, v in args.items() if k != "reasoning"}, sort_keys=True
        )
        if key != self._last_action:
            self._last_action, self._same, self._idle = key, 0, 0
        self._same += 1
        self._idle = 0 if changed else self._idle + 1
        if self._idle >= self.max_repeats:
            return (
                f"loop detected: the same action repeated {self.max_repeats} times "
                "without changing the page"
            )
        if self._same >= self.max_same:
            return f"loop detected: the same action repeated {self.max_same} times in a row"
        return None
