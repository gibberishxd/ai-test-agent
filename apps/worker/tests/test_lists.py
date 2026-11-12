"""List pages and their item details (run 5, K2): a generic exploration rule.

Run 4's traces: Gemma reached a list of orders and never opened one, so a bug on the detail
page could not be found. The agent is now reminded, per list page, to open at least one item.
A list is recognised from the page's own links (several links to the same path ending in an
id), never from a site-specific name.
"""

from worker.agent.lists import ListTracker, item_lists
from worker.agent.observe import Element
from worker.agent.prompt import SYSTEM_PROMPT


def link(n: int, name: str, href: str) -> Element:
    return Element(id=n, role="link", name=name, tag="a", href=href)


ORIGIN = "http://shop.test"
ORDERS = [
    link(1, "Home", f"{ORIGIN}/"),
    link(2, "Order #1042", f"{ORIGIN}/orders/1042"),
    link(3, "Order #1043", f"{ORIGIN}/orders/1043"),
    link(4, "Order #1044", f"{ORIGIN}/orders/1044"),
]


def test_links_to_one_path_ending_in_ids_are_a_list():
    lists = item_lists(f"{ORIGIN}/orders", ORDERS)
    assert lists == {"/orders": "Order #1042"}


def test_ids_can_be_slugs_with_digits_or_uuids():
    rooms = [
        link(1, "Room A", f"{ORIGIN}/rooms/sea-view-101"),
        link(2, "Room B", f"{ORIGIN}/rooms/garden-202"),
    ]
    rows = [
        link(1, "Row 1", f"{ORIGIN}/admin/rows/3f2b8c1e-1d2a-4c55-9a7e-0b1c2d3e4f50"),
        link(2, "Row 2", f"{ORIGIN}/admin/rows/9a8b7c6d-1d2a-4c55-9a7e-0b1c2d3e4f50"),
    ]
    assert item_lists(f"{ORIGIN}/rooms", rooms) == {"/rooms": "Room A"}
    assert item_lists(f"{ORIGIN}/admin", rows) == {"/admin/rows": "Row 1"}


def test_one_link_or_navigation_words_are_not_a_list():
    menu = [
        link(1, "About", f"{ORIGIN}/about"),
        link(2, "Contact", f"{ORIGIN}/contact"),
        link(3, "Order #1", f"{ORIGIN}/orders/1"),
    ]
    assert item_lists(f"{ORIGIN}/", menu) == {}


def test_links_to_other_sites_are_ignored():
    away = [link(1, "A", "https://other.test/p/1"), link(2, "B", "https://other.test/p/2")]
    assert item_lists(f"{ORIGIN}/", away) == {}


def test_the_reminder_stays_until_an_item_of_that_list_is_opened():
    tracker = ListTracker()
    tracker.see(f"{ORIGIN}/orders", ORDERS)
    assert tracker.reminder() and "/orders" in tracker.reminder()
    assert "Order #1042" in tracker.reminder()

    tracker.visit(f"{ORIGIN}/orders/1043")
    assert tracker.reminder() == ""


def test_opening_an_item_of_another_list_does_not_count():
    tracker = ListTracker()
    tracker.see(f"{ORIGIN}/orders", ORDERS)
    tracker.see(
        f"{ORIGIN}/",
        [link(1, "Socks", f"{ORIGIN}/products/1"), link(2, "Hat", f"{ORIGIN}/products/2")],
    )
    tracker.visit(f"{ORIGIN}/products/2")
    reminder = tracker.reminder()
    assert "/orders" in reminder and "/products" not in reminder


def test_an_item_page_linking_to_its_siblings_is_not_a_new_list():
    """A detail page with 'next / previous order' links is already an opened item."""
    tracker = ListTracker()
    tracker.visit(f"{ORIGIN}/orders/1042")
    tracker.see(f"{ORIGIN}/orders/1042", ORDERS)
    assert tracker.reminder() == ""


def test_the_charter_asks_to_open_list_items_without_naming_a_site():
    assert "detail page" in SYSTEM_PROMPT
    lowered = SYSTEM_PROMPT.lower()
    assert "order #" not in lowered and "1042" not in lowered


def test_lists_the_crawl_found_are_reminded_until_the_agent_opens_an_item():
    """Run 5 K2 benchmark: only the free crawl visited the order pages; the agent never went to
    the list, so it was never reminded. Lists the crawl found seed the reminder."""
    from worker.agent.lists import lists_from_crawl

    crawled = [
        (f"{ORIGIN}/", None),
        (f"{ORIGIN}/orders", f"{ORIGIN}/"),
        (f"{ORIGIN}/orders/1001", f"{ORIGIN}/orders"),
        (f"{ORIGIN}/orders/1002", f"{ORIGIN}/orders"),
        (f"{ORIGIN}/about", f"{ORIGIN}/"),
    ]
    found = lists_from_crawl(crawled)
    assert found == {"/orders": ("/orders", "1001")}

    tracker = ListTracker()
    tracker.seed(found)
    assert "on /orders" in tracker.reminder()
    tracker.visit(f"{ORIGIN}/orders/1002")  # the crawl's own visits don't count; the agent's do
    assert tracker.reminder() == ""
