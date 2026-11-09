"""Loading one page in a real browser with Playwright.

`visit_page` is the real implementation of the crawler's `visit` function. Each URL gets a fresh
tab (page) in a shared context: shared cookies and login, but no leftover events or state from
the previous page.
"""

from playwright.sync_api import BrowserContext, Page
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from worker.report import PageResult

NAVIGATION_TIMEOUT_MS = 15_000
NETWORK_IDLE_TIMEOUT_MS = 5_000


def visit_page(context: BrowserContext, url: str) -> tuple[PageResult, list[str]]:
    """Open `url` in a new tab; return what we found there and the absolute URLs it links to."""
    page = context.new_page()
    try:
        try:
            response = page.goto(url, timeout=NAVIGATION_TIMEOUT_MS)
        except PlaywrightError as error:
            # DNS failure, connection refused, timeout: there is no page to inspect.
            return PageResult(url=url, status=None, error=_first_line(error)), []

        _wait_until_quiet(page)
        result = PageResult(
            url=url,
            status=response.status if response else None,
            title=page.title() or None,
        )
        return result, _links_on(page)
    finally:
        page.close()


def _wait_until_quiet(page: Page) -> None:
    """Give JavaScript apps time to render (React adds links after the "load" event).

    "networkidle" means no requests for 500 ms. Some pages never go quiet (polling, live
    updates), so a timeout here is expected and not an error: we carry on with what rendered.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass


def _links_on(page: Page) -> list[str]:
    """Every <a href> on the page. The browser's a.href property is already an absolute URL."""
    return page.eval_on_selector_all("a[href]", "anchors => anchors.map(a => a.href)")


def _first_line(error: Exception) -> str:
    """Playwright errors include a multi-line call log; the first line is the useful part."""
    return str(error).splitlines()[0]
