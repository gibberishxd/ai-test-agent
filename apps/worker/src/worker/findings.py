"""Turn what the checks saw on each page into bug reports.

Raw results are per page; bugs are per *problem*. The same console error, failing API call or
accessibility rule often shows on several pages (a broken header is on every page), so findings
are grouped by what's wrong, and the evidence lists every page it was seen on.

Deterministic findings come with hard evidence, so they're "confirmed" from the start.
Severity follows the rubric in the product brief (5.4).
"""

from collections import defaultdict
from urllib.parse import urlsplit

from worker.report import BugReport, PageResult

SLOW_PAGE_MS = 3000

# Resource types whose failure breaks a feature (data didn't load), vs. a missing asset.
DATA_REQUESTS = {"document", "fetch", "xhr"}


def findings_from_pages(pages: list[PageResult]) -> list[BugReport]:
    broken = _broken_links(pages)
    broken_urls = {bug.evidence["link"] for bug in broken}
    return (
        _console_errors(pages)
        + _failed_requests(pages, skip_urls=broken_urls)
        + broken
        + _accessibility(pages)
        + _slow_pages(pages)
    )


def _deterministic(**fields) -> BugReport:
    return BugReport(source="deterministic", status="confirmed", **fields)


def _console_errors(pages: list[PageResult]) -> list[BugReport]:
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for page in pages:
        for error in page.console_errors:
            groups[(error.kind, error.text)].append(page.url)
    bugs = []
    for (kind, text), urls in groups.items():
        uncaught = kind == "pageerror"
        bugs.append(
            _deterministic(
                title=f"{'Uncaught exception' if uncaught else 'Console error'}: {_short(text)}",
                severity="high" if uncaught else "medium",
                category="console-error",
                page_url=urls[0],
                expected="The page runs without JavaScript errors.",
                actual=f"{'Uncaught exception' if uncaught else 'console.error'}: {text}",
                repro_steps=[f"Open {urls[0]}", "Open the browser's developer console"],
                evidence={"console_errors": [{"kind": kind, "text": text}], "pages": _unique(urls)},
            )
        )
    return bugs


def _failed_requests(pages: list[PageResult], skip_urls: set[str]) -> list[BugReport]:
    groups: dict[tuple[str, int | None, str | None], list] = defaultdict(list)
    for page in pages:
        for request in page.failed_requests:
            if request.url in skip_urls:
                continue  # already reported as a broken link
            groups[(request.url, request.status, request.failure)].append((page.url, request))
    bugs = []
    for (url, status, failure), seen in groups.items():
        request = seen[0][1]
        urls = _unique(page_url for page_url, _ in seen)
        problem = f"HTTP {status}" if status else (failure or "request failed")
        breaks_data = request.resource_type in DATA_REQUESTS
        server_error = status is not None and status >= 500
        bugs.append(
            _deterministic(
                title=f"{request.method} {_path(url)} fails with {problem}",
                severity="high" if breaks_data or server_error else "medium",
                category="network",
                page_url=urls[0],
                expected=f"The {request.resource_type} request succeeds.",
                actual=f"{request.method} {url} returned {problem}.",
                repro_steps=[
                    f"Open {urls[0]}",
                    "Open the developer tools' Network tab",
                    f"Find {url}",
                ],
                evidence={"failed_requests": [request.model_dump()], "pages": urls},
            )
        )
    return bugs


def _broken_links(pages: list[PageResult]) -> list[BugReport]:
    linked_from: dict[str, list[str]] = defaultdict(list)
    for page in pages:
        if page.found_on and (_is_error(page.status) or page.error or page.soft_404):
            linked_from[page.url].append(page.found_on)
    by_url = {page.url: page for page in pages}
    bugs = []
    for url, sources in linked_from.items():
        page = by_url[url]
        if _is_error(page.status):  # a real HTTP error is the stronger evidence
            problem = f"returns HTTP {page.status}"
        elif page.soft_404:
            problem = "shows a 'not found' page"
        else:
            problem = f"can't be loaded ({page.error})"
        bugs.append(
            _deterministic(
                title=f"Broken link: {_path(url)} {problem}",
                severity="low",
                category="broken-link",
                page_url=sources[0],
                expected="Links lead to a working page.",
                actual=f"The link to {url} {problem}.",
                repro_steps=[f"Open {sources[0]}", f"Click the link to {_path(url)}"],
                evidence={"link": url, "status": page.status, "pages": _unique(sources)},
            )
        )
    return bugs


def _accessibility(pages: list[PageResult]) -> list[BugReport]:
    groups: dict[str, list] = defaultdict(list)
    for page in pages:
        for violation in page.a11y_violations:
            groups[violation.rule_id].append((page.url, violation))
    bugs = []
    for rule_id, seen in groups.items():
        violation = seen[0][1]
        urls = _unique(url for url, _ in seen)
        targets = _unique(t for _, v in seen for t in v.targets)
        bugs.append(
            _deterministic(
                title=f"Accessibility: {violation.help}",
                severity="medium",
                category="accessibility",
                page_url=urls[0],
                expected=violation.help + ".",
                actual=f"{len(targets)} element(s) fail rule '{rule_id}': {', '.join(targets[:5])}",
                repro_steps=[
                    f"Open {urls[0]}",
                    f"Run an axe accessibility scan (rule '{rule_id}')",
                ],
                evidence={
                    "a11y": [{**violation.model_dump(), "targets": targets}],
                    "pages": urls,
                },
            )
        )
    return bugs


def _slow_pages(pages: list[PageResult]) -> list[BugReport]:
    return [
        _deterministic(
            title=f"Slow page: {_path(page.url)} took {page.load_ms / 1000:.1f} s to load",
            severity="low",
            category="performance",
            page_url=page.url,
            expected=f"The page loads in under {SLOW_PAGE_MS / 1000:.0f} s.",
            actual=f"The load event fired after {page.load_ms} ms.",
            repro_steps=[f"Open {page.url}"],
            evidence={"load_ms": page.load_ms, "pages": [page.url]},
        )
        for page in pages
        if page.load_ms is not None and page.load_ms > SLOW_PAGE_MS
    ]


def _is_error(status: int | None) -> bool:
    return status is not None and status >= 400


def _unique(items) -> list:
    return list(dict.fromkeys(items))


def _short(text: str, limit: int = 80) -> str:
    first_line = text.splitlines()[0] if text else ""
    return first_line if len(first_line) <= limit else first_line[: limit - 1] + "…"


def _path(url: str) -> str:
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
