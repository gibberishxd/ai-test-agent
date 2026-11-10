"""The passive scan: crawl the target through the safety proxy and run every check.

Passive means look-only (rule 6.2): the browser loads pages and follows links, and nothing else.
"""

import itertools
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime

from playwright.sync_api import Browser, BrowserContext, sync_playwright

from worker.browser import VIEWPORTS, VisitOptions, visit_page
from worker.config import Settings
from worker.crawler import crawl
from worker.findings import findings_from_pages
from worker.report import BrokenLink, PageResult, Report
from worker.safety.network import BlockedError, NetworkGuard, dev_allowed_local
from worker.safety.proxy import GuardProxy
from worker.storage import Storage
from worker.urls import is_same_origin

VIEWPORT = VIEWPORTS["desktop"]


def make_guard(settings: Settings, target_url: str) -> NetworkGuard:
    """In dev mode our own demo shops on localhost are allowed; everything else must be public."""
    allowed = dev_allowed_local(settings.demo_urls()) if settings.dev_mode else set()
    return NetworkGuard(allowed_local=allowed, target_url=target_url)


@contextmanager
def guarded_context(
    settings: Settings, target_url: str, browser: Browser | None = None
) -> Iterator[tuple[BrowserContext, NetworkGuard]]:
    """A browser context whose traffic goes through the safety proxy (rule 6.1).

    Pass `browser` to reuse one (tests); otherwise a browser is launched and closed here.
    """
    guard = make_guard(settings, target_url)
    reason = guard.check(target_url)
    if reason:
        raise BlockedError(f"target not allowed: {reason}")
    with GuardProxy(guard) as proxy, ExitStack() as stack:
        if browser is None:
            playwright = stack.enter_context(sync_playwright())
            browser = playwright.chromium.launch()
            stack.callback(browser.close)
        context = browser.new_context(proxy=proxy.playwright_config, viewport=VIEWPORT)
        stack.callback(context.close)
        yield context, guard


def passive_scan(
    target_url: str,
    settings: Settings,
    storage: Storage,
    key_prefix: str,
    on_page: Callable[[PageResult], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    browser: Browser | None = None,
) -> Report:
    """Crawl and check `target_url`: look only, follow links, run every deterministic check."""
    started = datetime.now(UTC)
    counter = itertools.count(1)

    number = 0

    def save(png: bytes, url: str) -> str:
        nonlocal number
        number = next(counter)
        return storage.save(f"{key_prefix}/page-{number:03d}.png", png)

    def save_mobile(png: bytes, url: str) -> str:
        return storage.save(f"{key_prefix}/page-{number:03d}-mobile.png", png)

    with guarded_context(settings, target_url, browser) as (context, guard):
        options = VisitOptions(save_screenshot=save, save_mobile_screenshot=save_mobile)

        def visit(url: str) -> tuple[PageResult, list[str]]:
            blocked_before = len(guard.blocked)
            page, links = visit_page(context, url, options)
            page.blocked_requests = [b.url for b in guard.blocked[blocked_before:]]
            return page, links

        pages = crawl(
            target_url,
            visit,
            max_pages=settings.max_pages,
            max_depth=settings.max_depth,
            on_page=on_page,
            should_stop=should_stop,
        )

    return Report(
        target=target_url,
        started_at=started,
        finished_at=datetime.now(UTC),
        pages=pages,
        broken_links=_broken_links(pages),
        bugs=findings_from_pages(pages),
    )


def is_demo_target(settings: Settings, target_url: str) -> bool:
    """Is the target one of our demo shops? (Interactive mode and the test card are OK there.)"""
    return any(is_same_origin(target_url, url) for url in settings.demo_urls())


def _broken_links(pages: list[PageResult]) -> list[BrokenLink]:
    links: dict[str, BrokenLink] = {}
    for page in pages:
        broken = page.error or page.soft_404 or (page.status is not None and page.status >= 400)
        if page.found_on and broken:
            link = links.setdefault(
                page.url, BrokenLink(url=page.url, status=page.status, found_on=[])
            )
            link.found_on.append(page.found_on)
    return list(links.values())
