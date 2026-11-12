"""List pages and their item details: remind the agent to open at least one item per list.

A tester who sees a list of orders, products, rooms or rows opens one and checks that the detail
page shows the item that was clicked. A small model tends to read the list and move on (run 4:
the order list was reached, no order was opened). The rule here is generic: a list is several
same-site links whose paths share a parent and end in an id (digits, a slug with digits, a UUID).
Nothing names a site, a product or a known bug.
"""

import re
from urllib.parse import urlsplit

from worker.agent.observe import Element

ID_SEGMENT = re.compile(
    r"^(\d+"  # 1042
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # a UUID
    r"|[\w-]*\d[\w-]*)"  # a slug with a digit: sea-view-101
    r"(\.[a-z]{2,5})?$",  # an optional extension: 1042.html
    re.IGNORECASE,
)
MIN_ITEMS = 2
MAX_SHOWN = 3


def _split(url: str) -> tuple[str, str, str] | None:
    """(origin, parent path, last segment) of a URL whose last segment looks like an id."""
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    if "/" not in path:
        return None
    parent, last = path.rsplit("/", 1)
    if not parent or not ID_SEGMENT.match(last):
        return None
    return f"{parts.scheme}://{parts.netloc}", parent, last


def item_lists(page_url: str, elements: list[Element]) -> dict[str, str]:
    """The lists on this page: {parent path: name of one item link}."""
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(page_url))
    groups: dict[str, dict[str, str]] = {}
    for element in elements:
        if not element.href:
            continue
        split = _split(element.href)
        if split is None or split[0] != origin:
            continue
        _, parent, last = split
        groups.setdefault(parent, {}).setdefault(last, element.name or element.href)
    return {
        parent: next(iter(items.values()))
        for parent, items in groups.items()
        if len(items) >= MIN_ITEMS
    }


class ListTracker:
    """Which lists the agent has seen, and which of them it has opened an item of."""

    def __init__(self) -> None:
        self._lists: dict[str, tuple[str, str]] = {}  # parent -> (page path, example item)
        self._opened: set[str] = set()

    def see(self, page_url: str, elements: list[Element]) -> None:
        self.visit(page_url)
        page_path = urlsplit(page_url).path or "/"
        for parent, example in item_lists(page_url, elements).items():
            self._lists.setdefault(parent, (page_path, example))

    def seed(self, lists: dict[str, tuple[str, str]]) -> None:
        """Lists the crawl found before the agent started (not opened by the agent yet)."""
        for parent, place in lists.items():
            self._lists.setdefault(parent, place)

    def visit(self, url: str) -> None:
        split = _split(url)
        if split is not None:
            self._opened.add(split[1])

    def reminder(self) -> str:
        waiting = [(p, v) for p, v in self._lists.items() if p not in self._opened]
        if not waiting:
            return ""
        lines = [
            f'- on {page}: open one item (e.g. "{example}") and check its page shows that item'
            for _, (page, example) in waiting[:MAX_SHOWN]
        ]
        return "LISTS WITH NO ITEM OPENED YET:\n" + "\n".join(lines)


def lists_from_crawl(pages: list[tuple[str, str | None]]) -> dict[str, tuple[str, str]]:
    """Lists among crawled pages: (url, found_on) pairs where two or more pages under one parent
    path end in an id. Returns {parent: (list page path, an item's id)}."""
    groups: dict[str, list[tuple[str, str | None]]] = {}
    for url, found_on in pages:
        split = _split(url)
        if split is not None:
            groups.setdefault(split[1], []).append((split[2], found_on))
    lists = {}
    for parent, items in groups.items():
        if len(items) < MIN_ITEMS:
            continue
        first_id, found_on = items[0]
        page = urlsplit(found_on).path or "/" if found_on else parent
        lists[parent] = (page, first_id)
    return lists
