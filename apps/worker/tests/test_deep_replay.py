"""Replay repeats deep mode's actions too (run 9): keys, hover, any window size, a scroll
distance. Each step is recorded by the toolbox and repeated in a fresh page."""

from worker.verify import ReplayStep, replay

SEARCH = {"role": "searchbox", "name": "Search", "css": "#q"}


def test_press_key_on_a_recorded_element(context, site_url):
    page = context.new_page()
    replay(
        page,
        f"{site_url}/deep.html",
        [
            ReplayStep("type", {"text": "lamp"}, SEARCH),
            ReplayStep("press_key", {"key": "Enter"}, SEARCH),
        ],
    )
    assert page.locator("#searched").inner_text() == "Searched: lamp"


def test_press_key_without_an_element_goes_to_the_focused_one(context, site_url):
    page = context.new_page()
    replay(
        page,
        f"{site_url}/deep.html",
        [
            ReplayStep("click", {}, SEARCH),
            ReplayStep("type", {"text": "desk"}, SEARCH),
            ReplayStep("press_key", {"key": "Enter"}, None),
        ],
    )
    assert page.locator("#searched").inner_text() == "Searched: desk"


def test_hover(context, site_url):
    page = context.new_page()
    replay(
        page,
        f"{site_url}/deep.html",
        [ReplayStep("hover", {}, {"role": "button", "name": "More", "css": "#hover-me"})],
    )
    assert page.locator("#tip").is_visible()


def test_set_viewport_by_width_and_height(context, site_url):
    page = context.new_page()
    replay(
        page,
        f"{site_url}/deep.html",
        [ReplayStep("set_viewport", {"width": 768, "height": 1024}, None)],
    )
    assert page.viewport_size == {"width": 768, "height": 1024}


def test_the_current_loops_named_sizes_still_replay(context, site_url):
    page = context.new_page()
    replay(page, f"{site_url}/deep.html", [ReplayStep("set_viewport", {"size": "mobile"}, None)])
    assert page.viewport_size == {"width": 375, "height": 812}


def test_scroll_by_a_recorded_distance(context, site_url):
    page = context.new_page()
    page.set_viewport_size({"width": 400, "height": 300})
    replay(
        page,
        f"{site_url}/layout.html",
        [ReplayStep("scroll", {"direction": "down", "pixels": 50}, None)],
    )
    assert page.evaluate("window.scrollY") == 50
