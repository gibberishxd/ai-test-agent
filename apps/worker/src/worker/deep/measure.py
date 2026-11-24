"""Verifying deep mode's measurement and check findings in a fresh page.

A deep-mode report found with JavaScript or one of our checks carries the measurement itself:
the snippet (or the check and its rule), the setup steps that reach the state it was measured
in, the URL, the viewport, and what the harness measured when the report was made. To verify
it, a fresh page at the same viewport repeats the setup steps (the same replay as interaction
bugs), runs the same measurement, and compares:

- the same result → confirmed;
- a different result → dismissed, saying both values;
- the setup can't be repeated, or the measurement fails now → unverified: nothing could check
  it either way, so it is kept apart from verified findings, never mixed in.

"The same" allows only rounding (numbers to one decimal) and key order; anything else differs.
"""

import json
from dataclasses import dataclass

from playwright.sync_api import BrowserContext
from playwright.sync_api import Error as PlaywrightError

from worker.browser import wait_until_quiet
from worker.deep.harness import rule_detail
from worker.deep.toolbox import NAVIGATION_TIMEOUT_MS, SETTLE_MS, Toolbox, ToolboxConfig
from worker.keyboard_probe import opened_by, probe, snapshot
from worker.safety.network import NetworkGuard
from worker.verify import ReplayError, ReplayStep, failure_of, find_target, replay, size_or_desktop

MAX_SHOWN = 200  # characters of a value shown in a reason


@dataclass
class MeasureVerdict:
    status: str  # "confirmed", "dismissed" or "unverified"
    reason: str
    result: object = None  # what the fresh page measured


def verify_measurement(
    context: BrowserContext,
    guard: NetworkGuard,
    spec: dict,
    setup: list[ReplayStep],
    target_url: str,
) -> MeasureVerdict:
    """Repeat a measurement or check finding in a new page of `context`."""
    page = context.new_page()
    try:
        page.set_viewport_size(size_or_desktop(str(spec.get("viewport") or "desktop")))
        toolbox = Toolbox(page, guard, ToolboxConfig(target_url=target_url))
        toolbox.attach()
        try:
            if setup:
                replay(page, target_url, setup)
            else:
                page.goto(str(spec.get("url") or target_url), timeout=NAVIGATION_TIMEOUT_MS)
                wait_until_quiet(page, SETTLE_MS)
        except ReplayError as error:
            failure = failure_of(error)
            return MeasureVerdict(
                "unverified",
                f"the setup couldn't be repeated: step {failure['step']} ({failure['action']}): "
                f"{failure['detail']}",
            )
        except PlaywrightError as error:
            return MeasureVerdict("unverified", f"the page couldn't be opened: {_line(error)}")
        if spec.get("kind") == "measure":
            return _remeasure(toolbox, spec)
        if spec.get("check") == "keyboard_probe":
            return _reprobe(page, spec)
        return _recheck(toolbox, spec)
    finally:
        page.close()


def _remeasure(toolbox: Toolbox, spec: dict) -> MeasureVerdict:
    result = toolbox.call("evaluate_js", {"snippet": str(spec.get("snippet") or "")})
    data = result.data or {}
    if result.is_error or data.get("error"):
        return MeasureVerdict(
            "unverified", f"the snippet failed now: {data.get('error') or result.text}"
        )
    now, then = data.get("value"), spec.get("result")
    if same_result(now, then):
        return MeasureVerdict("confirmed", f"re-measured in a fresh browser: {_show(now)}", now)
    return MeasureVerdict(
        "dismissed",
        f"re-measured {_show(now)} in a fresh browser; the report had {_show(then)}",
        now,
    )


def _recheck(toolbox: Toolbox, spec: dict) -> MeasureVerdict:
    check, rule = str(spec.get("check")), str(spec.get("rule"))
    result = toolbox.call(check, {})
    if result.is_error:
        return MeasureVerdict(
            "unverified", f"{check} couldn't run now: {result.text.splitlines()[0]}"
        )
    found = rule_detail(check, rule, result.data or {})
    if found is None:
        return MeasureVerdict("dismissed", f"{check} doesn't report {rule} in a fresh browser")
    if check == "run_axe":
        before = set((spec.get("result") or {}).get("targets") or [])
        now = set(found.get("targets") or [])
        if before and not before & now:
            elsewhere = ", ".join(sorted(now))[:MAX_SHOWN]
            return MeasureVerdict(
                "dismissed", f"{rule} is reported now, but on other elements ({elsewhere})", found
            )
    return MeasureVerdict("confirmed", f"{check} reports {rule} again in a fresh browser", found)


def _reprobe(page, spec: dict) -> MeasureVerdict:
    rule = str(spec.get("rule"))
    element = spec.get("element") or {}
    try:
        target = find_target(page, element)
        snapshot(page)
        handle = target.element_handle()
        target.click()
        wait_until_quiet(page, SETTLE_MS)
    except (ReplayError, PlaywrightError) as error:
        return MeasureVerdict("unverified", f"the control couldn't be opened again: {_line(error)}")
    kind = opened_by(page, handle)
    if kind is None:
        return MeasureVerdict("dismissed", "the control opened nothing in a fresh browser")
    failures = probe(page, kind, handle)
    failed = next((f for f in failures if f.get("check") == rule), None)
    if failed is None:
        return MeasureVerdict("dismissed", f"the {kind} passes the {rule} check in a fresh browser")
    return MeasureVerdict("confirmed", f"the {kind} fails the {rule} check again", failed)


def same_result(a, b) -> bool:
    """Equal after rounding numbers to one decimal and ignoring key order."""
    return _canonical(a) == _canonical(b)


def _canonical(value) -> str:
    def round_all(v):
        if isinstance(v, bool) or v is None or isinstance(v, str):
            return v
        if isinstance(v, int | float):
            return round(float(v), 1)
        if isinstance(v, list):
            return [round_all(x) for x in v]
        if isinstance(v, dict):
            return {str(k): round_all(x) for k, x in v.items()}
        return str(v)

    return json.dumps(round_all(value), sort_keys=True)


def _show(value) -> str:
    return json.dumps(value)[:MAX_SHOWN]


def _line(error: Exception) -> str:
    text = str(error).strip()
    return (text.splitlines()[0] if text else type(error).__name__)[:300]
