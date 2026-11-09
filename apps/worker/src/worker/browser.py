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
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from playwright.sync_api import BrowserContext, ConsoleMessage, Page, Response
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Request as PlaywrightRequest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from worker.report import A11yViolation, ConsoleError, FailedRequest, PageResult
from worker.safety.secrets import redact

NAVIGATION_TIMEOUT_MS = 15_000
NETWORK_IDLE_TIMEOUT_MS = 5_000
AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"

# WCAG A/AA rules only. axe's "best-practice" rules are advice, not failures, and would make
# the false-alarm count depend on taste.
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

# Failures that aren't the site's fault: navigation cancelled the request, or our guard did.
IGNORED_FAILURES = {"net::ERR_ABORTED", "net::ERR_BLOCKED_BY_CLIENT"}

SOFT_404 = re.compile(r"\b(404|page not found|not found)\b", re.IGNORECASE)


@dataclass
class VisitOptions:
    save_screenshot: Callable[[bytes, str], str] | None = None  # (png, url) -> storage ref
    run_axe: bool = True


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
    _listen(page, console, failed)
    try:
        started = time.monotonic()
        try:
            response = page.goto(url, timeout=NAVIGATION_TIMEOUT_MS)
        except PlaywrightError as error:
            # DNS failure, connection refused, blocked, timeout: there is no page to inspect.
            return PageResult(url=url, status=None, error=_first_line(error)), []
        load_ms = int((time.monotonic() - started) * 1000)

        _wait_until_quiet(page)
        result = PageResult(
            url=url,
            status=response.status if response else None,
            title=page.title() or None,
            load_ms=load_ms,
            console_errors=console,
            failed_requests=[f for f in failed if f.url != response.url] if response else failed,
            soft_404=_looks_like_not_found(page),
        )
        if options.run_axe:
            result.a11y_violations = run_axe(page)
        if options.save_screenshot:
            result.screenshot = options.save_screenshot(page.screenshot(full_page=True), url)
        return result, _links_on(page)
    finally:
        page.close()


def _listen(page: Page, console: list[ConsoleError], failed: list[FailedRequest]) -> None:
    def on_console(message: ConsoleMessage) -> None:
        if message.type != "error" or message.text.startswith("Failed to load resource"):
            return  # Chrome's echo of a failed request: already captured as a FailedRequest
        loc = message.location
        where = f"{loc.get('url')}:{loc.get('lineNumber')}" if loc and loc.get("url") else None
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
    page.evaluate("() => {" + axe_source() + "\n}")
    violations = page.evaluate(
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


def _wait_until_quiet(page: Page) -> None:
    """Give JavaScript apps time to render (React adds links after the "load" event).

    "networkidle" means no requests for 500 ms. Some pages never go quiet (polling, live
    updates), so a timeout here is expected and not an error: we carry on with what rendered.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
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
