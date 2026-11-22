"""Loading one page in a real browser and running the deterministic checks on it.

`visit_page` is the real implementation of the crawler's `visit` function. Each URL gets a fresh
tab (page) in a shared context: shared cookies and login, but no leftover events or state from
the previous page. While the page loads, event listeners collect console errors, uncaught
exceptions, failed requests and 4xx/5xx responses; after it settles we run axe-core and take a
full-page screenshot.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from playwright.sync_api import BrowserContext, ConsoleMessage, Page, Response
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Request as PlaywrightRequest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from worker.layout import check_layout
from worker.meta import check_meta
from worker.report import A11yViolation, ConsoleError, FailedRequest, PageResult
from worker.safety.secrets import redact

NAVIGATION_TIMEOUT_MS = 15_000
# The two screens the worker tests on: a laptop, and a common phone size.
VIEWPORTS = {
    "desktop": {"width": 1280, "height": 800},
    "mobile": {"width": 375, "height": 812},
}


# A run's own screen size, "WIDTHxHEIGHT" (e.g. "390x844"): within what real screens have.
_SIZE = re.compile(r"(\d+)x(\d+)")
MIN_SIDE, MAX_SIDE = 200, 4000


def parse_viewport(text: str) -> dict[str, int]:
    """Parse "390x844" into {"width": 390, "height": 844}; ValueError for anything else."""
    match = _SIZE.fullmatch(text.strip().lower())
    if not match:
        raise ValueError(f"viewport must look like 390x844, got {text!r}")
    width, height = int(match[1]), int(match[2])
    if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
        raise ValueError(f"viewport sides must be {MIN_SIDE}–{MAX_SIDE} px, got {text!r}")
    return {"width": width, "height": height}


def viewport_size(name: str) -> dict[str, int]:
    """A named viewport ("desktop", "mobile") or a run's own size ("390x844")."""
    return VIEWPORTS[name] if name in VIEWPORTS else parse_viewport(name)


def viewport_label(name: str) -> str:
    size = viewport_size(name)
    text = f"{size['width']}×{size['height']}"
    return f"{name} ({text})" if name in VIEWPORTS else text


NETWORK_IDLE_TIMEOUT_MS = 5_000
AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"

# WCAG A/AA rules, plus axe's "best-practice" rules (landmarks, skip links, one main heading):
# D14 left those out as advice; D105 adds them, still one finding per rule.
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]

# Failures that aren't the site's fault: navigation cancelled the request, or our guard did.
IGNORED_FAILURES = {"net::ERR_ABORTED", "net::ERR_BLOCKED_BY_CLIENT"}

SOFT_404 = re.compile(r"\b(404|page not found|not found)\b", re.IGNORECASE)


@dataclass
class VisitOptions:
    save_screenshot: Callable[[bytes, str], str] | None = None  # (png, url) -> storage ref
    # Same, for a second screenshot at phone width (layout bugs only show there).
    save_mobile_screenshot: Callable[[bytes, str], str] | None = None
    run_axe: bool = True
    check_layout: bool = True
    check_meta: bool = True
    # og:image and /favicon.ico results (url → problem or None), shared by a scan's pages.
    image_cache: dict = field(default_factory=dict)


@cache
def axe_source() -> str:
    return AXE_PATH.read_text(encoding="utf-8")


def visit_page(
    context: BrowserContext, url: str, options: VisitOptions | None = None
) -> tuple[PageResult, list[str]]:
    """Open `url` in a new tab, run every check; return the result and the links on the page."""
    options = options or VisitOptions()
    page = context.new_page()
    console: list[ConsoleError] = []
    failed: list[FailedRequest] = []
    warnings: list[ConsoleError] = []
    listen(page, console, failed, warnings)
    try:
        started = time.monotonic()
        try:
            response = page.goto(url, timeout=NAVIGATION_TIMEOUT_MS)
        except PlaywrightError as error:
            # DNS failure, connection refused, blocked, timeout: there is no page to inspect.
            return PageResult(url=url, status=None, error=_first_line(error)), []
        load_ms = int((time.monotonic() - started) * 1000)

        wait_until_quiet(page)
        result = PageResult(
            url=url,
            status=response.status if response else None,
            title=page.title() or None,
            load_ms=load_ms,
            console_errors=console,
            console_warnings=warnings,
            failed_requests=[f for f in failed if f.url != response.url] if response else failed,
            soft_404=_looks_like_not_found(page),
        )
        if options.run_axe:
            result.a11y_violations = run_axe(page)
        if options.check_layout:
            result.layout = check_layout(page)  # at the run's own size, before the phone shot
        if options.check_meta and result.status is not None and result.status < 400:
            result.meta = check_meta(page, options.image_cache)  # not on an error page
        if options.save_screenshot:
            result.screenshot = options.save_screenshot(page.screenshot(full_page=True), url)
        if options.save_mobile_screenshot:
            page.set_viewport_size(VIEWPORTS["mobile"])
            wait_until_quiet(page, 1000)
            png = page.screenshot(full_page=True)
            result.mobile_screenshot = options.save_mobile_screenshot(png, url)
        return result, _links_on(page)
    finally:
        page.close()


def listen(
    page: Page,
    console: list[ConsoleError],
    failed: list[FailedRequest],
    warnings: list[ConsoleError] | None = None,
) -> None:
    """Collect the page's console errors, uncaught exceptions and failed requests, and (with
    `warnings`) its console warnings, each distinct text once."""

    def on_console(message: ConsoleMessage) -> None:
        loc = message.location
        where = f"{loc.get('url')}:{loc.get('lineNumber')}" if loc and loc.get("url") else None
        if message.type == "warning" and warnings is not None:
            if from_extension(loc, message.text) or len(warnings) >= MAX_WARNINGS:
                return
            text = redact(message.text)
            if all(w.text != text for w in warnings):
                warnings.append(ConsoleError(kind="warning", text=text, location=where))
            return
        if message.type != "error" or message.text.startswith("Failed to load resource"):
            return  # Chrome's echo of a failed request: already captured as a FailedRequest
        console.append(ConsoleError(kind="console", text=redact(message.text), location=where))

    def on_page_error(error: PlaywrightError) -> None:
        console.append(
            ConsoleError(kind="pageerror", text=redact(f"{error.name}: {error.message}"))
        )

    def on_request_failed(request: PlaywrightRequest) -> None:
        if request.failure in IGNORED_FAILURES:
            return
        failed.append(_failed(request, status=None, failure=request.failure))

    def on_response(response: Response) -> None:
        if response.status >= 400:
            failed.append(_failed(response.request, status=response.status, failure=None))

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)


EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")
MAX_WARNINGS = 50  # distinct warnings kept per page


def from_extension(location: dict | None, text: str) -> bool:
    """Does a console message come from a browser extension rather than the site?"""
    url = (location or {}).get("url") or ""
    return url.startswith(EXTENSION_SCHEMES) or any(s in text for s in EXTENSION_SCHEMES)


# Runs one of our own scripts with the page's console muted, so whatever it logs (axe-core is
# third-party code) isn't counted as the site's. The page's own messages during that moment
# are muted too; scripts run for well under a second.
# Wraps one of our own scripts so the page's console is muted while it runs, and whatever it
# logs (axe-core is third-party code) isn't counted as the site's. The page's own messages in
# that moment are muted too; scripts run for well under a second. Built as a string, not with
# eval() in the page: a site's Content Security Policy may forbid eval.
QUIET_JS = """async (arg) => {
  const levels = ['log', 'info', 'debug', 'warn', 'error'];
  const saved = levels.map((level) => console[level]);
  levels.forEach((level) => { console[level] = () => {}; });
  try {
    return await (/*SCRIPT*/)(arg);
  } finally {
    levels.forEach((level, i) => { console[level] = saved[i]; });
  }
}"""


def evaluate_quietly(page: Page, script: str, arg=None):
    """page.evaluate(script, arg) with the console muted while it runs (see QUIET_JS)."""
    return page.evaluate(QUIET_JS.replace("/*SCRIPT*/", script), arg)


def _failed(request: PlaywrightRequest, status: int | None, failure: str | None) -> FailedRequest:
    return FailedRequest(
        url=redact(request.url),
        method=request.method,
        resource_type=request.resource_type,
        status=status,
        failure=failure,
    )


def run_axe(page: Page) -> list[A11yViolation]:
    """Inject axe-core and return WCAG A/AA violations.

    page.evaluate runs through the browser's debugging protocol, so the site's Content Security
    Policy can't block it (a <script> tag injection could be blocked).
    """
    evaluate_quietly(page, "() => {" + axe_source() + "\n}")
    violations = evaluate_quietly(
        page,
        """async (tags) => {
            const results = await axe.run(document, {
                runOnly: { type: "tag", values: tags },
                resultTypes: ["violations"],
            });
            return results.violations.map(v => ({
                rule_id: v.id,
                impact: v.impact,
                help: v.help,
                help_url: v.helpUrl,
                targets: v.nodes.map(n => n.target.join(" ")),
            }));
        }""",
        AXE_TAGS,
    )
    return [A11yViolation(**v) for v in violations]


def wait_until_quiet(page: Page, timeout_ms: int = NETWORK_IDLE_TIMEOUT_MS) -> None:
    """Give JavaScript apps time to render (React adds links after the "load" event).

    "networkidle" means no requests for 500 ms. Some pages never go quiet (polling, live
    updates), so a timeout here is expected and not an error: we carry on with what rendered.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass


def _looks_like_not_found(page: Page) -> bool:
    """A single-page app answers 200 for every path and draws "not found" with JavaScript."""
    heading = page.locator("h1").first
    text = heading.inner_text(timeout=1000) if heading.count() else ""
    return bool(SOFT_404.search(text))


def _links_on(page: Page) -> list[str]:
    """Every <a href> on the page. The browser's a.href property is already an absolute URL."""
    return page.eval_on_selector_all("a[href]", "anchors => anchors.map(a => a.href)")


def _first_line(error: Exception) -> str:
    """Playwright errors include a multi-line call log; the first line is the useful part."""
    return str(error).splitlines()[0]
