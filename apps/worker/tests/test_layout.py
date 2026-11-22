"""The layout check, on synthetic pages with known problems (tests/fixtures/site/layout*.html)."""

import pytest

from worker.browser import visit_page
from worker.layout import MIN_FONT_PX, MIN_TARGET_PX, check_layout

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 800}


@pytest.fixture
def at(browser):
    """Open a page at a given viewport and run the layout check on it."""
    contexts = []

    def open_at(url: str, viewport: dict):
        context = browser.new_context(viewport=viewport)
        contexts.append(context)
        page = context.new_page()
        page.goto(url)
        return check_layout(page)

    yield open_at
    for context in contexts:
        context.close()


def test_page_wider_than_the_viewport_names_the_element_that_sticks_out(at, site_url):
    layout = at(f"{site_url}/layout.html", PHONE)
    assert layout.viewport_width == 390
    assert layout.overflow_px == 2000 - 390
    selectors = [e["selector"] for e in layout.sticking_out]
    assert selectors[0].endswith("#too-wide")
    # Contained in its own scroll box, or fixed to the screen: doesn't widen the page.
    assert not any("scroller" in s or "inner" in s for s in selectors)
    assert len(selectors) == 1


def test_a_page_that_cant_scroll_sideways_is_not_wider(at, site_url):
    layout = at(f"{site_url}/layout-ok.html", PHONE)
    assert layout.overflow_px == 0
    assert layout.sticking_out == []


def test_small_tap_targets_on_a_phone(at, site_url):
    layout = at(f"{site_url}/layout.html", PHONE)
    names = [t["name"] for t in layout.small_targets]
    assert names == ["Close"]  # not the disabled one, the 48 px one, the inline link,
    # the hidden checkbox with its big label, or the link in an off-screen menu
    assert layout.small_target_count == 1
    target = layout.small_targets[0]
    assert target["width"] < MIN_TARGET_PX and target["height"] < MIN_TARGET_PX


def test_tap_targets_are_not_checked_on_wide_screens(at, site_url):
    layout = at(f"{site_url}/layout.html", DESKTOP)
    assert layout.small_targets == []
    assert layout.small_target_count == 0


def test_small_text_outside_code(at, site_url):
    layout = at(f"{site_url}/layout.html", DESKTOP)
    texts = [t["text"] for t in layout.small_text]
    assert texts == ["Small print under the price."]
    assert layout.small_text[0]["font_size"] < MIN_FONT_PX
    assert layout.small_text_count == 1


def test_pages_without_problems(at, site_url):
    assert at(f"{site_url}/clean.html", DESKTOP).problems() == []
    assert at(f"{site_url}/layout-ok.html", PHONE).problems() == []


def test_visit_page_runs_the_layout_check_at_the_contexts_viewport(browser, site_url):
    context = browser.new_context(viewport=PHONE)
    try:
        page, _ = visit_page(context, f"{site_url}/layout.html")
    finally:
        context.close()
    assert page.layout is not None
    assert page.layout.viewport_width == 390
    assert page.layout.overflow_px > 0
