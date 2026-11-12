"""Recognising the same bug across runs of the same target (run 4, J4).

A fingerprint is a hash of: the page route with ids normalised, the bug category, and a key that
names what is wrong (the failing request, the error message without its numbers, the axe rule,
the broken link, or for an agent report the element it acted on, else its title's words).
"""

from worker.fingerprint import fingerprint, normalize_message, normalize_route
from worker.report import BugReport


def bug(**fields) -> BugReport:
    return BugReport(**{"title": "t", "severity": "high", "source": "deterministic", **fields})


def test_routes_lose_ids_query_strings_and_trailing_slashes():
    assert normalize_route("https://shop.test/products/42?ref=home") == "/products/:id"
    assert (
        normalize_route("https://shop.test/orders/6f1c3f8e-1b1a-4f55-9a77-2d4f7d0a1c11/")
        == "/orders/:id"
    )
    assert (
        normalize_route("https://shop.test/u/5f2b9c0e8d7a6b5c4d3e2f1a/settings")
        == "/u/:id/settings"
    )
    assert normalize_route("https://shop.test/") == "/"
    assert (
        normalize_route("https://shop.test/products/desk-lamp") == "/products/desk-lamp"
    )  # a slug stays


def test_messages_lose_numbers_and_ids_but_keep_their_words():
    assert normalize_message(
        "TypeError: x is undefined at main.4f3a2b.js:12:5"
    ) == normalize_message("TypeError: x is undefined at main.9c8d7e.js:13:9")
    assert normalize_message("Order 1234 failed") == normalize_message("Order 99 failed")
    assert normalize_message("Order failed") != normalize_message("Payment failed")


def test_the_same_failing_request_on_another_product_id_is_the_same_bug():
    a = bug(
        category="network",
        page_url="https://shop.test/products/1",
        evidence={
            "failed_requests": [
                {"method": "GET", "url": "https://shop.test/api/products/1", "status": 500}
            ]
        },
    )
    b = bug(
        category="network",
        page_url="https://shop.test/products/7",
        evidence={
            "failed_requests": [
                {"method": "GET", "url": "https://shop.test/api/products/7", "status": 500}
            ]
        },
    )
    assert fingerprint(a) == fingerprint(b)


def test_the_same_message_on_two_different_pages_is_two_bugs():
    a = bug(
        category="console-error",
        page_url="https://shop.test/cart",
        evidence={"console_errors": [{"text": "TypeError: x is undefined"}]},
    )
    b = bug(
        category="console-error",
        page_url="https://shop.test/checkout",
        evidence={"console_errors": [{"text": "TypeError: x is undefined"}]},
    )
    assert fingerprint(a) != fingerprint(b)


def test_an_agent_report_reworded_on_the_same_element_is_the_same_bug():
    element = {"role": "button", "name": "Save changes"}
    a = bug(
        source="agent",
        category="functional",
        title="Save changes does nothing",
        page_url="https://shop.test/profile",
        evidence={"element": element},
    )
    b = bug(
        source="agent",
        category="functional",
        title="Clicking 'Save changes' has no effect",
        page_url="https://shop.test/profile",
        evidence={"element": element},
    )
    assert fingerprint(a) == fingerprint(b)


def test_without_an_element_the_titles_words_decide_ignoring_order_case_and_numbers():
    a = bug(
        source="agent",
        category="functional",
        title="Cart total ignores quantity: $12 instead of $36",
        page_url="https://shop.test/cart",
    )
    b = bug(
        source="agent",
        category="functional",
        title="cart TOTAL ignores the quantity ($24 instead of $48)",
        page_url="https://shop.test/cart",
    )
    c = bug(
        source="agent",
        category="functional",
        title="Discount applies twice",
        page_url="https://shop.test/cart",
    )
    assert fingerprint(a) == fingerprint(b) != fingerprint(c)


def test_categories_keep_bugs_apart_and_axe_rules_are_the_key():
    a11y = bug(
        category="accessibility",
        page_url="https://shop.test/",
        evidence={"a11y": [{"rule_id": "image-alt", "help": "Images must have alternative text"}]},
    )
    other_rule = bug(
        category="accessibility",
        page_url="https://shop.test/",
        evidence={
            "a11y": [{"rule_id": "button-name", "help": "Buttons must have discernible text"}]
        },
    )
    assert fingerprint(a11y) != fingerprint(other_rule)
    assert len(fingerprint(a11y)) == 16
