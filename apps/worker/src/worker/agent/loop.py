"""The agent loop: observe → decide → check → act → log, until finish or a budget runs out.

The model only chooses; the worker checks every choice against the safety rules before running
it, enforces the budgets, and records everything. Callbacks (`on_step`, `on_bug`,
`should_stop`) connect the loop to the database without the loop knowing about it.
"""

import json
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from os.path import commonprefix
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from worker.agent.expect import (
    EXPECT_ACTIONS,
    RESOLVING_ACTIONS,
    Candidate,
    Effect,
    mismatches,
)
from worker.agent.observe import Element, Memory, PageState, build_observation, read_page
from worker.agent.policy import Budget, card_number_reason, deny_reason
from worker.agent.prompt import SYSTEM_PROMPT
from worker.agent.tools import TOOL_NAMES, TOOLS
from worker.browser import VIEWPORTS, listen, viewport_label, wait_until_quiet
from worker.llm import LLMClient, ModelTimeout, ToolCall, Usage
from worker.login import LoginConfig, SignInResult, on_login_page
from worker.report import BugReport, ConsoleError, FailedRequest, PageResult
from worker.safety.actions import check_mode
from worker.safety.network import NetworkGuard
from worker.safety.secrets import redact
from worker.urls import is_same_site

ACTION_TIMEOUT_MS = 5000
NAVIGATION_TIMEOUT_MS = 15_000
SETTLE_MS = 2000
SCROLL_PX = 700
ELEMENT_ACTIONS = {"click", "double_click", "type", "select"}
CLICK_ACTIONS = {"click", "double_click"}
MAX_NOTES = 20
MAX_NOTE_CHARS = 200
OFF_SITE = "safe mode: this leads to another site ({host}); testing stays on the target site"


@dataclass
class AgentConfig:
    target_url: str
    mode: str  # "passive" or "interactive"
    budget: Budget
    focus: str | None = None
    is_demo_target: bool = False
    # Set when the worker signed in with the workspace's test account (run 4, J2).
    login: LoginConfig | None = None


@dataclass
class StepRecord:
    index: int  # 1-based; the model refers to steps as #index
    action: str
    args: dict
    reasoning: str | None
    url: str
    human: str  # "Click button "Add to cart"": used for repro steps
    result: str
    events: list[str]
    usage: Usage
    screenshot: str | None = None
    blocked: bool = False
    block_reason: str | None = None
    # Role and name of the element acted on, so replay can find it again in a fresh browser.
    element: dict | None = None
    # For the live browser pane: where the target was on the screenshot, and the screen size.
    box: dict | None = None
    viewport: dict | None = None
    changed: bool = False  # did the action change the page? (loop detection only counts no)


@dataclass
class AgentResult:
    steps: list[StepRecord] = field(default_factory=list)
    bugs: list[BugReport] = field(default_factory=list)
    stop_reason: str = ""
    summary: str | None = None
    # Console errors and failed requests seen during the session, per URL (become findings).
    pages: dict[str, PageResult] = field(default_factory=dict)
    # Expected-vs-actual mismatches the model closed as not a bug ({step, reason, flags}), and
    # the steps of mismatches it ignored until they expired.
    dismissed: list[dict] = field(default_factory=list)
    ignored: list[int] = field(default_factory=list)
    relogins: int = 0  # times the session ended and the worker signed in again


class ModelCallFailed(Exception):
    """The model didn't answer a decision (after the client's own timeout and retries)."""


class AgentRun:
    def __init__(
        self,
        page: Page,
        llm: LLMClient,
        guard: NetworkGuard,
        config: AgentConfig,
        save_screenshot: Callable[[bytes, str], str] | None = None,
        on_step: Callable[[StepRecord], None] | None = None,
        on_bug: Callable[[BugReport], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        relogin: Callable[[], SignInResult] | None = None,
    ):
        self.page = page
        self.relogin = relogin
        self.llm = llm
        self.guard = guard
        self.config = config
        self.save_screenshot = save_screenshot
        self.on_step = on_step or (lambda step: None)
        self.on_bug = on_bug or (lambda bug: None)
        self.should_stop = should_stop or (lambda: False)
        self.result = AgentResult()
        self.memory = Memory()
        self.token = secrets.token_hex(3)  # makes test data unique per run
        self._console: list[ConsoleError] = []
        self._failed: list[FailedRequest] = []
        self._want_screenshot = True
        self._seen_urls: set[str] = set()
        self._last_site_url = config.target_url  # where to return to if a step leaves the site
        self._viewport = "desktop"
        self._pending: list[Candidate] = []  # mismatches the model hasn't resolved yet
        page.set_viewport_size(VIEWPORTS[self._viewport])
        listen(page, self._console, self._failed)

    # --- the loop ---------------------------------------------------------------------------

    def run(self) -> AgentResult:
        budget = self.config.budget
        try:
            self.page.goto(self.config.target_url, timeout=NAVIGATION_TIMEOUT_MS)
        except PlaywrightError as error:
            self.result.stop_reason = f"could not open the target: {_first_line(error)}"
            return self.result
        if self._off_site(self.page.url):
            host = urlsplit(self.page.url).hostname
            self.result.stop_reason = f"the target redirects to another site ({host})"
            return self.result

        while True:
            reason = budget.exhausted() or ("stopped by user" if self.should_stop() else None)
            if reason:
                self.result.stop_reason = reason
                break
            try:
                step = self._step()
            except ModelCallFailed as error:
                # Keep the steps and reports so far: they get verified like any other run's.
                self.result.stop_reason = f"the model call failed: {error}"
                break
            loop_reason = budget.record(
                step.action, step.args, step.usage.cost_usd, changed=step.changed
            )
            if step.action == "finish" and not step.blocked:
                self.result.stop_reason = "finished"
                self.result.summary = step.args.get("summary")
                break
            if loop_reason:
                self.result.stop_reason = loop_reason
                break
        return self.result

    def _step(self) -> StepRecord:
        """One turn: look at the page, let the model choose, check and run it, record it."""
        state, events, image, screenshot = self._observe()

        def observation(trimmed: bool = False) -> str:
            return self._scrub(
                build_observation(
                    state,
                    self._task(),
                    self._budget_line(),
                    events,
                    self.memory,
                    viewport_label(self._viewport),
                    checks=self._open_mismatches(),
                    trimmed=trimmed,
                )
            )

        try:
            decision = self.llm.decide(SYSTEM_PROMPT, observation(), TOOLS, image)
        except ModelTimeout:
            # A long observation is what makes a local model slow: one more try, shorter.
            decision = self._decide(observation(trimmed=True), None)
        except Exception as error:  # connection refused, provider error...
            raise ModelCallFailed(f"{type(error).__name__}: {_first_line(error)}") from error
        index = len(self.result.steps) + 1
        outcome = self._act(decision.tool_call, state, index)
        outcome = self._restore_session(decision.tool_call, state, outcome)
        outcome = self._scrub_outcome(outcome)
        events = [self._scrub(e) for e in events]
        step = StepRecord(
            index=index,
            url=state.url,
            events=events,
            usage=decision.usage,
            screenshot=self._save(screenshot, index),
            viewport=VIEWPORTS[self._viewport],
            **outcome,
        )
        self.result.steps.append(step)
        self.memory.steps.append(f"#{step.index} {step.human} → {step.result}")
        self.on_step(step)
        return step

    def _decide(self, observation: str, image: bytes | None):
        try:
            return self.llm.decide(SYSTEM_PROMPT, observation, TOOLS, image)
        except Exception as error:
            raise ModelCallFailed(f"{type(error).__name__}: {_first_line(error)}") from error

    def _observe(self) -> tuple[PageState, list[str], bytes | None, bytes | None]:
        """The page as the model will see it: state, new events, the image for the model (if
        due) and the step's screenshot. The step's screenshot is taken now, before the action,
        so it shows what the agent looked at when it chose, with the target where it was."""
        wait_until_quiet(self.page, SETTLE_MS)
        late_exit = self._return_to_site()  # a delayed redirect since the last step
        state = read_page(self.page)
        if is_same_site(state.url, self.config.target_url):
            self._last_site_url = state.url
        events = self._drain_events(state.url)
        if late_exit:
            events.append(f"the page went to another site and was brought back ({late_exit})")
        try:
            screenshot = self._screenshot()
        except PlaywrightError:
            screenshot = None
        image = None
        if self._want_screenshot or state.url not in self._seen_urls:
            image = screenshot
        self._seen_urls.add(state.url)
        self._want_screenshot = False
        return state, events, image, screenshot

    def _act(self, call: ToolCall | None, state: PageState, index: int) -> dict:
        """Check the model's choice and run it. Returns the StepRecord fields that describe it."""
        if call is None or call.name not in TOOL_NAMES:
            return {
                "action": "none",
                "args": {},
                "reasoning": None,
                "human": "No action",
                "result": "error: no valid tool call; call exactly one tool",
            }
        args = dict(call.args)
        element = self._element(state, args)
        outcome = {
            "action": call.name,
            "args": args,
            "reasoning": redact(str(args.get("reasoning") or ""))[:300] or None,
            "human": describe(call.name, args, element),
            "element": element.target() if element else None,
            "box": element.box if element else None,
        }
        unresolved = self._unresolved_gate(call.name)
        if unresolved:
            return {
                **outcome,
                "result": f"BLOCKED: {unresolved}",
                "blocked": True,
                "block_reason": unresolved,
            }
        blocked = self._check(call.name, args, element)
        if blocked:
            return {
                **outcome,
                "result": f"BLOCKED: {blocked}",
                "blocked": True,
                "block_reason": blocked,
            }
        before = self._snapshot() if call.name in EXPECT_ACTIONS else None
        result, changed = self._execute(call.name, args, element, state, index)
        if call.name == "report_bug" and result == "bug recorded" and self._pending:
            result += f" (resolves the mismatch from #{self._pending.pop(0).step})"
        if before is not None and not result.startswith("error"):
            result = self._compare(args, before, result, index)
        left = self._return_to_site()
        if left:
            # Marked blocked so replay doesn't repeat a step that leaves the site.
            result = f"BLOCKED: {left}; you are back on {self.page.url}"
            return {**outcome, "result": result, "blocked": True, "block_reason": left}
        return {**outcome, "result": result, "changed": changed}

    # --- safety checks (before acting) -------------------------------------------------------

    def _element(self, state: PageState, args: dict) -> Element | None:
        element_id = element_number(args.get("element_id"))
        return next((e for e in state.elements if e.id == element_id), None)

    def _check(self, action: str, args: dict, element: Element | None) -> str | None:
        info = element.info() if element else None
        reason = check_mode(self.config.mode, action, info)
        if reason:
            return reason
        if action in CLICK_ACTIONS and info:
            if info.href and self._off_site(info.href):
                return OFF_SITE.format(host=urlsplit(info.href).hostname)
            return deny_reason(
                info,
                is_demo_target=self.config.is_demo_target,
                signed_in=self.config.login is not None,
            )
        if action == "type":
            return card_number_reason(str(args.get("text", "")), self.config.is_demo_target)
        if action == "navigate":
            return self.guard.check_navigation(urljoin(self.page.url, str(args.get("url", ""))))
        return None

    def _off_site(self, url: str) -> bool:
        """Is `url` a web page on another site than the target? (about:blank etc. are not.)"""
        is_web = urlsplit(url).scheme.lower() in ("http", "https")
        return is_web and not is_same_site(url, self.config.target_url)

    def _return_to_site(self) -> str | None:
        """If the page is on another site, go back to the last page on the target.

        A link shows where it leads, so it's refused before the click. A button, a form or a
        script doesn't, so this check runs after every action: the agent must never act on a
        site the workspace hasn't verified. Returns why it went back, or None if it didn't.
        """
        if not self._off_site(self.page.url):
            return None
        reason = OFF_SITE.format(host=urlsplit(self.page.url).hostname)
        try:
            self.page.goto(self._last_site_url, timeout=NAVIGATION_TIMEOUT_MS)
            wait_until_quiet(self.page, SETTLE_MS)
        except PlaywrightError:
            self.page.goto("about:blank")  # can't get back: at least don't stay over there
        return reason

    # --- acting ------------------------------------------------------------------------------

    def _execute(
        self, action: str, args: dict, element: Element | None, state: PageState, index: int
    ) -> tuple[str, bool]:
        """Run one allowed action. Returns what to tell the model, and whether the page changed
        (its URL, its text or its scroll position)."""
        if action in ELEMENT_ACTIONS and element is None:
            return f"error: there is no element [{args.get('element_id')}] on this page", False
        before = self.page.url
        before_text = self._page_text()
        before_scroll = self._scroll_position()
        try:
            if action == "click":
                self.page.locator(element.locator).click(timeout=ACTION_TIMEOUT_MS)
            elif action == "double_click":
                self.page.locator(element.locator).dblclick(timeout=ACTION_TIMEOUT_MS)
            elif action == "reload":
                self.page.reload(timeout=NAVIGATION_TIMEOUT_MS)
            elif action == "set_viewport":
                return self._set_viewport(str(args.get("size", "")))
            elif action == "note":
                return self._note(str(args.get("text", ""))), False
            elif action == "dismiss":
                return self._dismiss(args), False
            elif action == "type":
                self.page.locator(element.locator).fill(
                    str(args.get("text", "")), timeout=ACTION_TIMEOUT_MS
                )
            elif action == "select":
                self._select(element, str(args.get("option", "")))
            elif action == "navigate":
                url = urljoin(self.page.url, str(args.get("url", "")))
                self.page.goto(url, timeout=NAVIGATION_TIMEOUT_MS)
            elif action == "go_back":
                self.page.go_back(timeout=NAVIGATION_TIMEOUT_MS)
            elif action == "scroll":
                down = args.get("direction") != "up"
                # scrollBy has moved the page by the time it returns; a mouse wheel event is
                # applied a little later, so "did it scroll?" could be read too early.
                self.page.evaluate("y => window.scrollBy(0, y)", SCROLL_PX if down else -SCROLL_PX)
            elif action == "take_screenshot":
                self._want_screenshot = True
                return "ok: a screenshot is attached to the next observation", False
            elif action == "report_bug":
                return self._report_bug(args, state, index), False
            elif action == "finish":
                return "finished", False
        except PlaywrightError as error:
            return f"error: {_first_line(error)}", False
        wait_until_quiet(self.page, SETTLE_MS)
        if self.page.url != before:
            self._want_screenshot = True
            return f"ok, now on {self.page.url}", True
        after_text = self._page_text()
        new_lines = text_changes(before_text, after_text)
        if action == "reload":
            # What a refresh keeps or loses is the point of reloading, so always say which.
            seen = f"new on the page: {new_lines}" if new_lines else "it looks the same as before"
            return f"ok, the page was reloaded; {seen}", after_text != before_text
        if action in (*CLICK_ACTIONS, "go_back") and after_text == before_text:
            return "ok, but nothing on the page changed", False
        changed = after_text != before_text or self._scroll_position() != before_scroll
        return (f"ok; new on the page: {new_lines}" if new_lines else "ok"), changed

    def _set_viewport(self, size: str) -> tuple[str, bool]:
        if size not in VIEWPORTS:
            return f"error: size must be one of {', '.join(VIEWPORTS)}", False
        if size == self._viewport:
            return f"ok, the viewport already is {viewport_label(size)}", False
        self.page.set_viewport_size(VIEWPORTS[size])
        self._viewport = size
        self._want_screenshot = True
        wait_until_quiet(self.page, SETTLE_MS)
        return f"ok, the viewport is now {viewport_label(size)}", True

    def _note(self, text: str) -> str:
        text = redact(text.strip())[:MAX_NOTE_CHARS]
        if not text:
            return "error: the note is empty"
        if len(self.memory.notes) >= MAX_NOTES:
            return f"error: the notepad is full ({MAX_NOTES} notes)"
        self.memory.notes.append(text)
        # A weak model used notes for problems it then never reported (run 3, MISS_ANALYSIS).
        return (
            "noted (notes are only for you and are never reported; if this describes a "
            "problem you saw, report it now with report_bug)"
        )

    # --- signed-in runs (J2) ---------------------------------------------------------------------

    def _screenshot(self) -> bytes:
        """Every screenshot hides password fields, whatever they contain."""
        return self.page.screenshot(mask=[self.page.locator("input[type=password]")])

    def _scrub(self, text: str) -> str:
        login = self.config.login
        return login.scrub(text) if login and text else text

    def _scrub_outcome(self, outcome: dict) -> dict:
        if not self.config.login:
            return outcome
        clean = dict(outcome)
        for key in ("human", "result", "reasoning", "block_reason"):
            if isinstance(clean.get(key), str):
                clean[key] = self._scrub(clean[key])
        clean["args"] = json.loads(self._scrub(json.dumps(clean.get("args") or {})))
        return clean

    def _restore_session(self, call: ToolCall | None, state: PageState, outcome: dict) -> dict:
        """If the action ended on the login page without the agent going there, the session
        ended (a timeout, a server restart): sign in again and go back where the agent was."""
        login = self.config.login
        if not (login and self.relogin) or self.result.relogins >= MAX_RELOGINS:
            return outcome
        if on_login_page(state.url, login) or not on_login_page(self.page.url, login):
            return outcome
        if call and self._targets_login_page(call, state, login):
            return outcome
        self.result.relogins += 1
        signed_in = self.relogin()
        if signed_in.ok:
            try:
                self.page.goto(state.url, timeout=NAVIGATION_TIMEOUT_MS)
                wait_until_quiet(self.page, SETTLE_MS)
            except PlaywrightError:
                pass
            note = "the session had ended; the worker signed in again and went back"
        else:
            note = f"the session had ended and signing in again failed ({signed_in.detail})"
        return {**outcome, "result": f"{outcome.get('result', '')} | {note}"}

    def _targets_login_page(self, call: ToolCall, state: PageState, login: LoginConfig) -> bool:
        """Did the agent itself go to the login page (a link or a URL)? Then it isn't a drop."""
        if call.name == "navigate":
            target = urljoin(self.page.url, str(call.args.get("url", "")))
            return on_login_page(target, login)
        element = self._element(state, call.args)
        href = element.info().href if element else None
        return bool(href) and on_login_page(urljoin(state.url, href), login)

    # --- expected vs. actual (J1) ---------------------------------------------------------------

    def _snapshot(self) -> dict:
        """What the page looks like before an action whose result will be checked."""
        return {
            "url": self.page.url,
            "text": self._page_text(),
            "fields": self._field_values(),
            "console": len(self._console),
            "failed": len(self._failed),
            "viewport": self._viewport,
        }

    def _compare(self, args: dict, before: dict, result: str, index: int) -> str:
        """Record what the action changed, compare it with the model's expectation, and open a
        candidate when they don't match. Returns the result line, with the mismatch if any."""
        text, fields = self._page_text(), self._field_values()
        old_lines, new_lines = _lines(before["text"]), _lines(text)
        effect = Effect(
            url_before=before["url"],
            url_after=self.page.url,
            added=[line for line in new_lines if line not in set(old_lines)],
            removed=[line for line in old_lines if line not in set(new_lines)],
            fields=[
                f"{name}: {before['fields'].get(name, '')} → {value}"
                for name, value in fields.items()
                if before["fields"].get(name) != value
            ],
            viewport=(
                f"{before['viewport']} → {self._viewport}"
                if before["viewport"] != self._viewport
                else None
            ),
            events=[f"{e.kind} error: {e.text[:100]}" for e in self._console[before["console"] :]]
            + [
                f"network: {r.method} {r.url} → {r.status or r.failure}"
                for r in self._failed[before["failed"] :]
            ],
        )
        expected = redact(str(args.get("expect") or "")).strip()[:200]
        flags = mismatches(expected, effect, text, fields)
        args["check"] = {"expected": expected, "happened": effect.describe(), "flags": flags}
        if not flags:
            return result
        self._pending.append(Candidate(index, expected, effect.describe(), flags))
        return (
            f"{result} | MISMATCH with what you expected ({'; '.join(flags)}): report it with "
            "report_bug, or dismiss it with a reason"
        )

    def _field_values(self) -> dict[str, str]:
        try:
            pairs = self.page.evaluate(FIELD_VALUES_JS)
        except PlaywrightError:
            return {}
        return {str(name)[:60]: redact(str(value))[:100] for name, value in pairs}

    def _unresolved_gate(self, action: str) -> str | None:
        """While a mismatch is open, other actions are refused once; then it expires as ignored,
        so a model that won't resolve it can't stall the run."""
        if not self._pending or action in RESOLVING_ACTIONS:
            return None
        candidate = self._pending[0]
        if not candidate.blocked_once:
            candidate.blocked_once = True
            return (
                f"resolve the mismatch from #{candidate.step} first: report_bug if it is a bug, "
                "or dismiss it with a reason"
            )
        self._pending.pop(0)
        self.result.ignored.append(candidate.step)
        return None

    def _dismiss(self, args: dict) -> str:
        if not self._pending:
            return "error: there is no unresolved mismatch to dismiss"
        reason = redact(str(args.get("reason") or "")).strip()[:300]
        if not reason:
            return "error: say why this is not a bug (reason)"
        step = element_number(args.get("step_id"))
        candidate = next((c for c in self._pending if c.step == step), self._pending[0])
        self._pending.remove(candidate)
        self.result.dismissed.append(
            {"step": candidate.step, "reason": reason, "flags": candidate.flags}
        )
        return f"dismissed the mismatch from #{candidate.step}"

    def _open_mismatches(self) -> str:
        if not self._pending:
            return ""
        return (
            "UNRESOLVED MISMATCH (resolve it before anything else: report_bug if it is a bug, "
            "or dismiss with a reason)\n" + "\n".join(c.describe() for c in self._pending)
        )

    def _scroll_position(self) -> float:
        try:
            return self.page.evaluate("() => window.scrollY")
        except PlaywrightError:
            return 0

    def _page_text(self) -> str:
        try:
            return self.page.evaluate("() => document.body ? document.body.innerText : ''")
        except PlaywrightError:
            return ""

    def _select(self, element: Element, option: str) -> None:
        locator = self.page.locator(element.locator)
        try:
            locator.select_option(label=option, timeout=ACTION_TIMEOUT_MS)
        except PlaywrightError:
            locator.select_option(value=option, timeout=ACTION_TIMEOUT_MS)

    def _report_bug(self, args: dict, state: PageState, index: int) -> str:
        args = {k: self._scrub(v) if isinstance(v, str) else v for k, v in args.items()}
        title = redact(str(args.get("title") or "Untitled bug"))[:200]
        if title in self.memory.bugs:
            return "error: this bug was already reported"
        step_ids = [i for i in args.get("step_ids") or [] if isinstance(i, int) and 0 < i < index]
        steps = {s.index: s for s in self.result.steps}
        repro = [f"Open {self.config.target_url}"]
        repro += [steps[i].human for i in step_ids if i in steps and not steps[i].blocked]
        severity = str(args.get("severity", "medium"))
        bug = BugReport(
            title=title,
            severity=severity if severity in ("critical", "high", "medium", "low") else "medium",
            category=str(args.get("category") or "functional"),
            page_url=state.url,
            expected=redact(str(args.get("expected") or "")) or None,
            actual=redact(str(args.get("actual") or "")) or None,
            repro_steps=repro,
            # The step where the bug was reported: replay repeats every action up to here.
            evidence={"observed": redact(str(args.get("evidence") or "")), "reported_at": index},
            reasoning=redact(str(args.get("reasoning") or "")) or None,
            step_indexes=step_ids,
            source="agent",
            status="candidate",
        )
        self.result.bugs.append(bug)
        self.memory.bugs.append(title)
        self.on_bug(bug)
        return "bug recorded"

    # --- helpers -----------------------------------------------------------------------------

    def _task(self) -> str:
        lines = [f"TASK: Test {self.config.target_url} like a manual QA tester."]
        if self.config.focus:
            lines.append(f"FOCUS: {self.config.focus}")
        lines.append(
            f"TEST DATA for sign-up and other forms: email test+{self.token}@example.com, "
            f"name Test User, password Test-{self.token}!"
        )
        lines.append(
            "LOGIN: to log in, use an account the site itself offers for testing (for example "
            "demo credentials shown on the login page). A made-up account failing to log in "
            "is expected, not a bug."
        )
        if self.config.is_demo_target:
            lines.append("TEST CARD (demo shop only): 4242 4242 4242 4242")
        if self.config.mode == "passive":
            lines.append("MODE: passive. You may only click links, navigate, scroll and report.")
        return "\n".join(lines)

    def _budget_line(self) -> str:
        b = self.config.budget
        line = (
            f"STEP {b.steps + 1} of at most {b.max_steps}. "
            f"Cost so far ${b.cost_usd:.3f} of ${b.max_cost_usd:.2f}."
        )
        if b.repeating():
            line += (
                "\nWARNING: you keep repeating the same action. Repeating it once more ends "
                "the run: do something different."
            )
        untried = untried_techniques(self.result.steps)
        if untried:
            line += "\nCHARTER TECHNIQUES NOT TRIED YET in this run (use each where it fits):"
            line += "".join(f"\n- {text}" for _, text in untried)
        return line

    def _drain_events(self, url: str) -> list[str]:
        """New console errors and failed requests since the last step, as short lines."""
        events = [f"{e.kind} error: {e.text[:200]}" for e in self._console]
        events += [f"network: {r.method} {r.url} → {r.status or r.failure}" for r in self._failed]
        if self._console or self._failed:
            page = self.result.pages.setdefault(url, PageResult(url=url, status=200))
            page.console_errors += self._console
            page.failed_requests += self._failed
        self._console.clear()
        self._failed.clear()
        return events

    def _save(self, png: bytes | None, index: int) -> str | None:
        if not self.save_screenshot or png is None:
            return None
        return self.save_screenshot(png, f"step-{index:03d}")


NUMBER = re.compile(r"\d[\d.,]*")


def text_changes(before: str, after: str, limit: int = 600) -> str:
    """What an action changed on the page, shortened, the most telling part first.

    1. Values that changed, with the old value: "Subtotal: $12.00 → $24.00".
    2. New lines that contain a number ("Discount: -$1.20").
    3. Other new lines ("Added to your cart.").
    Small models can't tell "it worked" from "ok"; this is the signal a human tester gets by
    looking at the screen, and numbers are where most functional bugs show.
    """
    old = [line.strip() for line in before.splitlines() if line.strip()]
    new = [line.strip() for line in after.splitlines() if line.strip()]
    added = [line for line in dict.fromkeys(new) if line not in set(old)]
    # Lines that disappeared, by shape: "Subtotal: $#" for "Subtotal: $12.00".
    gone: dict[str, list[str]] = {}
    for line in dict.fromkeys(old):
        if line not in set(new) and NUMBER.search(line):
            gone.setdefault(NUMBER.sub("#", line), []).append(line)

    changed, numbers, words = [], [], []
    for line in added:
        previous = gone.get(NUMBER.sub("#", line)) if NUMBER.search(line) else None
        if previous:
            old_line = previous.pop(0)
            changed.append(f"{old_line} → {_changed_part(old_line, line)}")
        elif NUMBER.search(line):
            numbers.append(line)
        else:
            words.append(line)
    text = " | ".join([*changed, *numbers, *words])
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _changed_part(old: str, new: str) -> str:
    """The part of `new` that differs from `old`, from the start of the word it begins in:
    ("Subtotal: $12.00", "Subtotal: $24.00") → "$24.00"."""
    shared = len(commonprefix([old, new]))
    return new[new.rfind(" ", 0, shared) + 1 :]


def describe(action: str, args: dict, element: Element | None) -> str:
    """A step in plain words, as it would appear in a bug's repro steps."""
    target = (
        f'{element.role} "{element.name}"' if element else f"element [{args.get('element_id')}]"
    )
    if action == "click":
        return f"Click {target}"
    if action == "double_click":
        return f"Double-click {target}"
    if action == "reload":
        return "Reload the page"
    if action == "set_viewport":
        return f"Switch to the {args.get('size', '')} viewport"
    if action == "note":
        return f'Note: "{args.get("text", "")}"'
    if action == "type":
        return f'Type "{args.get("text", "")}" into {target}'
    if action == "select":
        return f'Select "{args.get("option", "")}" in {target}'
    if action == "navigate":
        return f"Go to {args.get('url', '')}"
    if action == "go_back":
        return "Go back"
    if action == "scroll":
        return f"Scroll {args.get('direction', 'down')}"
    if action == "take_screenshot":
        return "Take a screenshot"
    if action == "report_bug":
        return f"Report bug: {args.get('title', '')}"
    if action == "finish":
        return "Finish"
    if action == "dismiss":
        return f"Dismiss the mismatch from #{args.get('step_id', '')}"
    return action


MAX_RELOGINS = 3


# Field values by label, for expected-vs-actual. Passwords and hidden fields are never read.
FIELD_VALUES_JS = """() => Array.from(document.querySelectorAll('input, select, textarea'))
  .filter(e => e.type !== 'password' && e.type !== 'hidden')
  .map(e => [
    (e.labels && e.labels[0] && e.labels[0].innerText.trim()) || e.getAttribute('aria-label')
      || e.name || e.id || e.type,
    (e.type === 'checkbox' || e.type === 'radio') ? String(e.checked) : e.value,
  ])"""


def _lines(text: str) -> list[str]:
    return list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))


# Charter techniques a model can visibly try with one tool call, and the reminder shown until it
# has. Run 3: a 12B model used double_click, reload and the mobile viewport 0 times in 11 runs,
# so the bugs only those reveal were never triggered. Generic: no site, page or bug in here.
TECHNIQUES = [
    (
        "unusual_value",
        "type an unusual value in a field: 0 or 2+ in a quantity, a very long text, special "
        "characters, an empty required field, a malformed email",
    ),
    (
        "double_click",
        "double_click a button that submits or applies something: nothing may happen twice",
    ),
    ("reload", "reload after saving or logging out: the change (or the logout) must stick"),
    ("mobile", "set_viewport mobile on a key page and look for text or elements out of their box"),
]
SPECIAL = re.compile(r"[<>&'\"%;{}]")


def untried_techniques(steps) -> list[tuple[str, str]]:
    """The TECHNIQUES not yet used in `steps` (blocked steps don't count), in charter order."""
    tried = set()
    for step in steps:
        if step.blocked:
            continue
        args = step.args or {}
        if step.action in ("double_click", "reload"):
            tried.add(step.action)
        elif step.action == "set_viewport" and args.get("size") == "mobile":
            tried.add("mobile")
        elif step.action == "type" and _unusual(str(args.get("text", "")), step.element or {}):
            tried.add("unusual_value")
    return [(key, text) for key, text in TECHNIQUES if key not in tried]


def _unusual(text: str, element: dict) -> bool:
    """A value a tester types on purpose to probe a field, rather than ordinary data."""
    value = text.strip()
    if value == "" or len(value) > 50 or SPECIAL.search(value):
        return True
    if re.fullmatch(r"-?\d+(\.\d+)?", value):
        return value != "1"  # 1 is the ordinary quantity; 0, 2+, negatives and fractions probe
    is_email_field = "mail" in str(element.get("name", "")).lower()
    return is_email_field and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value)


def element_number(value) -> int | None:
    """The element id the model meant: models write 7, 7.0, "7", "[7]" or [7] for the same thing."""
    if isinstance(value, bool):
        return None
    if isinstance(value, list) and len(value) == 1:
        return element_number(value[0])
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        digits = value.strip().strip("[]").strip()
        return int(digits) if digits.isdigit() else None
    return None


def _first_line(error: Exception) -> str:
    return str(error).splitlines()[0]
