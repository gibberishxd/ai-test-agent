"""Breadth-first crawl of a site's same-origin pages.

The crawl logic doesn't know about browsers: it takes a `visit` function that loads one URL and
returns (what was found on it, the links on it). The real `visit` uses Playwright; tests pass a
fake one. This is dependency injection, and it lets the loop-prevention logic be tested fast.
"""

from collections import deque
from collections.abc import Callable

from worker.report import PageResult
from worker.urls import is_same_origin, normalize

VisitFn = Callable[[str], tuple[PageResult, list[str]]]


def crawl(start_url: str, visit: VisitFn, max_pages: int = 50) -> list[PageResult]:
    """Visit `start_url` and every same-origin page reachable from it, each one once.

    Breadth-first: pages close to the start are visited first, so if `max_pages` cuts the
    crawl short, we've covered the most reachable pages rather than one deep path.
    """
    start = normalize(start_url)
    queue: deque[tuple[str, str | None]] = deque([(start, None)])  # (url, found_on)
    seen = {start}  # added when queued, not when visited, so nothing is queued twice
    pages: list[PageResult] = []

    while queue and len(pages) < max_pages:
        url, found_on = queue.popleft()
        page, links = visit(url)
        page.found_on = found_on
        pages.append(page)

        for link in links:
            if not is_same_origin(link, start):
                continue
            link = normalize(link)
            if link not in seen:
                seen.add(link)
                queue.append((link, url))

    return pages
