"""Rules checked by the worker before and between agent actions. The model can't skip them.

- Safe mode (rule 6.3, always on): a deny list for final, destructive or outward-facing actions.
- Test data: real-looking card numbers are only allowed on our demo shop.
- Budgets (rule 6.5 / brief 5.2): steps, wall-clock time, cost, and loop detection.
"""

import json
import re
import time
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

from worker.safety.actions import ElementInfo

OWN = r"(?:my\s+|your\s+|the\s+)?"  # "place order", "place my order", "place your order"


@dataclass(frozen=True)
class DenyRule:
    category: str
    phrase: str  # shown in the block reason
    pattern: re.Pattern


def _rule(category: str, phrase: str, pattern: str) -> DenyRule:
    return DenyRule(category, phrase, re.compile(pattern, flags=re.IGNORECASE))


# Actions safe mode refuses: they commit to something or can't be undone. Whole words only, so
# "pay" doesn't match "repay". Checked before every click, on every field that can name what a
# control does. The only exception is our own demo shops, where nothing is real.
DENY_RULES = [
    _rule("payment", "pay", r"\bpay(?:\s+now)?\b"),
    _rule("payment", "purchase", r"\bpurchase\b"),
    _rule("payment", "buy", r"\bbuy\b"),
    _rule("payment", "place order", rf"\bplace\s+{OWN}order\b"),
    _rule("payment", "complete purchase", rf"\bcomplete\s+{OWN}(?:purchase|order|payment)\b"),
    _rule("payment", "submit order", rf"\bsubmit\s+{OWN}(?:order|payment)\b"),
    _rule("commitment", "confirm", r"\bconfirm\b"),
    _rule("subscription", "subscribe", r"\bsubscribe\b"),
    _rule("subscription", "unsubscribe", r"\bunsubscribe\b"),
    _rule(
        "subscription",
        "cancel subscription",
        rf"\bcancel\s+{OWN}(?:subscription|plan|membership|account|order)\b",
    ),
    _rule("destructive", "delete", r"\bdelete\b"),
    _rule("destructive", "remove", r"\bremove\b"),
    _rule("destructive", "deactivate", r"\bdeactivate\b"),
    _rule("destructive", "close account", rf"\bclose\s+{OWN}account\b"),
    _rule("account", "change password", rf"\bchange\s+{OWN}password\b"),
    _rule("account", "change email", rf"\bchange\s+{OWN}e-?mail\b"),
    _rule("outbound", "send", r"\bsend\b"),
    _rule("outbound", "transfer", r"\btransfer\b"),
]

# When the worker signed in with the workspace's test account (run 4, J2), the agent must keep
# that session and that account: these apply on every target, our demo shops included.
SIGNED_IN_RULES = [
    _rule("session", "log out", r"\b(?:log|sign)\s*-?\s*(?:out|off)\b"),
    _rule("account", "delete account", rf"\b(?:delete|remove|close|deactivate)\s+{OWN}account\b"),
    _rule("account", "change password", rf"\b(?:change|reset|update)\s+{OWN}password\b"),
]

# Clicking into a field only focuses it, and its text is what the user typed, not an action.
TYPING_ROLES = {"textbox", "searchbox", "combobox", "slider", "spinbutton"}
CARD_NUMBER = re.compile(r"^\d{13,19}$")


def url_words(url: str | None) -> str:
    """The path and query of a URL as plain words: "/billing/cancelSubscription" →
    "billing cancel Subscription". The host is left out: it names the site, not the action."""
    if not url:
        return ""
    parts = urlsplit(url)
    text = unquote(f"{parts.path} {parts.query}")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)  # camelCase → camel Case
    return re.sub(r"[^A-Za-z0-9]+", " ", text).strip()


def deny_reason(element: ElementInfo, is_demo_target: bool, signed_in: bool = False) -> str | None:
    """None if clicking `element` is allowed, otherwise why safe mode refuses it.

    `signed_in`: the worker signed in with a saved test account, so the session and account
    rules apply too, on every target."""
    if element.role in TYPING_ROLES:
        return None
    rules = (SIGNED_IN_RULES if signed_in else []) + ([] if is_demo_target else DENY_RULES)
    fields = {
        "text": element.name,
        "aria-label": element.aria_label,
        "value": element.value,
        "link": url_words(element.href),
        "form action": url_words(element.form_action),
    }
    for label, value in fields.items():
        if not value:
            continue
        for rule in rules:
            if rule.pattern.search(value):
                return f"safe mode ({rule.category}): the element's {label} says '{rule.phrase}'"
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
