"""The agent loop: observe → decide → check → act → log, until finish or a budget runs out.

The model only chooses; the worker checks every choice against the safety rules before running
it, enforces the budgets, and records everything. Callbacks (`on_step`, `on_bug`,
`should_stop`) connect the loop to the database without the loop knowing about it.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from worker.agent.observe import Element, Memory, PageState, build_observation, read_page
from worker.agent.policy import Budget, card_number_reason, deny_reason
from worker.agent.prompt import SYSTEM_PROMPT
from worker.agent.tools import TOOL_NAMES, TOOLS
from worker.browser import listen, wait_until_quiet
from worker.llm import LLMClient, Usage
from worker.report import BugReport, ConsoleError, FailedRequest, PageResult
from worker.safety.actions import check_mode
from worker.safety.network import NetworkGuard
from worker.safety.secrets import redact

ACTION_TIMEOUT_MS = 5000
NAVIGATION_TIMEOUT_MS = 15_000
SETTLE_MS = 2000
SCROLL_PX = 700
ELEMENT_ACTIONS = {"click", "type", "select"}


@dataclass
class AgentConfig:
    target_url: str
    mode: str  # "passive" or "interactive"
    budget: Budget
    focus: str | None = None
    is_demo_target: bool = False


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


@dataclass
class AgentResult:
    steps: list[StepRecord] = field(default_factory=list)
    bugs: list[BugReport] = field(default_factory=list)
    stop_reason: str = ""
    summary: str | None = None
    # Console errors and failed requests seen during the session, per URL (become findings).
    pages: dict[str, PageResult] = field(default_factory=dict)


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
    ):
        self.page = page
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
        listen(page, self._console, self._failed)

    # --- the loop ---------------------------------------------------------------------------

    def run(self) -> AgentResult:
        budget = self.config.budget
        try:
            self.page.goto(self.config.target_url, timeout=NAVIGATION_TIMEOUT_MS)
        except PlaywrightError as error:
            self.result.stop_reason = f"could not open the target: {_first_line(error)}"
            return self.result

        while True:
            reason = budget.exhausted() or ("stopped by user" if self.should_stop() else None)
            if reason:
                self.result.stop_reason = reason
                break
            step = self._step()
            loop_reason = budget.record(step.action, step.args, step.usage.cost_usd)
            if step.action == "finish" and not step.blocked:
                self.result.stop_reason = "finished"
                self.result.summary = step.args.get("summary")
                break
            if loop_reason:
                self.result.stop_reason = loop_reason
                break
        return self.result

    def _step(self) -> StepRecord:
        wait_until_quiet(self.page, SETTLE_MS)
        state = read_page(self.page)
        events = self._drain_events(state.url)
        image = None
        if self._want_screenshot or state.url not in self._seen_urls:
            image = self.page.screenshot()
        self._seen_urls.add(state.url)
        self._want_screenshot = False

        observation = build_observation(
            state, self._task(), self._budget_line(), events, self.memory
        )
        decision = self.llm.decide(SYSTEM_PROMPT, observation, TOOLS, image)
        index = len(self.result.steps) + 1
        call = decision.tool_call

        if call is None or call.name not in TOOL_NAMES:
            step = StepRecord(
                index,
                "none",
                {},
                None,
                state.url,
                "No action",
                "error: no valid tool call; call exactly one tool",
                events,
                decision.usage,
            )
        else:
            args = dict(call.args)
            reasoning = redact(str(args.get("reasoning") or ""))[:300] or None
            element = self._element(state, args)
            human = describe(call.name, args, element)
            blocked = self._check(call.name, args, element)
            if blocked:
                step = StepRecord(
                    index,
                    call.name,
                    args,
                    reasoning,
                    state.url,
                    human,
                    f"BLOCKED: {blocked}",
                    events,
                    decision.usage,
                    blocked=True,
                    block_reason=blocked,
                )
            else:
                result = self._execute(call.name, args, element, state, index)
                step = StepRecord(
                    index,
                    call.name,
                    args,
                    reasoning,
                    state.url,
                    human,
                    result,
                    events,
                    decision.usage,
                )

        if call is not None and call.name in TOOL_NAMES:
            target = self._element(state, dict(call.args))
            if target is not None:
                step.element = {"role": target.role, "name": target.name}
        step.screenshot = self._thumbnail(index)
        self.result.steps.append(step)
        self.memory.steps.append(f"#{step.index} {step.human} → {step.result}")
        self.on_step(step)
        return step

    # --- safety checks (before acting) -------------------------------------------------------

    def _element(self, state: PageState, args: dict) -> Element | None:
        element_id = args.get("element_id")
        return next((e for e in state.elements if e.id == element_id), None)

    def _check(self, action: str, args: dict, element: Element | None) -> str | None:
        info = element.info() if element else None
        reason = check_mode(self.config.mode, action, info)
        if reason:
            return reason
        if action == "click" and info:
            return deny_reason(info, allow_buy=self.config.is_demo_target)
        if action == "type":
            return card_number_reason(str(args.get("text", "")), self.config.is_demo_target)
        if action == "navigate":
            return self.guard.check_navigation(urljoin(self.page.url, str(args.get("url", ""))))
        return None

    # --- acting ------------------------------------------------------------------------------

    def _execute(
        self, action: str, args: dict, element: Element | None, state: PageState, index: int
    ) -> str:
        if action in ELEMENT_ACTIONS and element is None:
            return f"error: there is no element [{args.get('element_id')}] on this page"
        before = self.page.url
        before_text = self._page_text()
        try:
            if action == "click":
                self.page.locator(element.locator).click(timeout=ACTION_TIMEOUT_MS)
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
                self.page.mouse.wheel(0, SCROLL_PX if down else -SCROLL_PX)
            elif action == "take_screenshot":
                self._want_screenshot = True
                return "ok: a screenshot is attached to the next observation"
            elif action == "report_bug":
                return self._report_bug(args, state, index)
            elif action == "finish":
                return "finished"
        except PlaywrightError as error:
            return f"error: {_first_line(error)}"
        wait_until_quiet(self.page, SETTLE_MS)
        if self.page.url != before:
            self._want_screenshot = True
            return f"ok, now on {self.page.url}"
        after_text = self._page_text()
        if action in ("click", "go_back") and after_text == before_text:
            return "ok, but nothing on the page changed"
        new_lines = text_changes(before_text, after_text)
        return f"ok; new on the page: {new_lines}" if new_lines else "ok"

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
                "\nWARNING: your last two actions were identical. Repeating it once more ends "
                "the run: do something different."
            )
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

    def _thumbnail(self, index: int) -> str | None:
        if not self.save_screenshot:
            return None
        try:
            png = self.page.screenshot()
        except PlaywrightError:
            return None
        return self.save_screenshot(png, f"step-{index:03d}")


def text_changes(before: str, after: str, limit: int = 160) -> str:
    """Lines that appeared after an action ("Added to your cart.", "Cart (2)"), shortened.

    Small models can't tell "it worked" from "ok"; seeing what changed is the signal a human
    tester gets by looking at the screen.
    """
    seen = {line.strip() for line in before.splitlines()}
    added = [
        line.strip() for line in after.splitlines() if line.strip() and line.strip() not in seen
    ]
    text = " | ".join(dict.fromkeys(added))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def describe(action: str, args: dict, element: Element | None) -> str:
    """A step in plain words, as it would appear in a bug's repro steps."""
    target = (
        f'{element.role} "{element.name}"' if element else f"element [{args.get('element_id')}]"
    )
    if action == "click":
        return f"Click {target}"
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
    return action


def _first_line(error: Exception) -> str:
    return str(error).splitlines()[0]
