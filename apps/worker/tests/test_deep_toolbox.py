"""Deep mode's toolbox against real pages: every tool, its safety rules, and what it records
for replay. No model: the tests call the tools the way the model would."""

import io
import json
from urllib.parse import urlsplit

import pytest
from PIL import Image

from worker.deep.toolbox import REPLAYED_TOOLS, Toolbox, ToolboxConfig
from worker.safety.network import NetworkGuard


@pytest.fixture
def toolbox(context, site_url):
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )

    def make(path="/deep.html", **config):
        page = context.new_page()
        box = Toolbox(page, guard, ToolboxConfig(target_url=f"{site_url}{path}", **config))
        box.start()
        return box, page

    return make


def ref_of(box: Toolbox, role: str, name: str) -> int:
    """The ref the latest snapshot gave the element with this role and name."""
    box.call("snapshot", {})
    return next(e.id for e in box.elements if e.role == role and e.name == name)


# --- seeing --------------------------------------------------------------------------------


def test_snapshot_lists_elements_with_refs_and_the_accessibility_tree(toolbox):
    box, _ = toolbox()
    result = box.call("snapshot", {})
    assert not result.is_error
    assert '[3] button "Add one"' in result.text or 'button "Add one"' in result.text
    assert 'heading "Deep tools"' in result.text  # from the accessibility tree
    assert "<page_content>" in result.text  # the page's words are marked as untrusted data


def test_page_text_cannot_close_the_untrusted_block(toolbox):
    box, _ = toolbox("/form.html")
    text = box.call("visible_text", {}).text
    assert text.count("</page_content>") == 1  # the page's own "</page_content>" is defused


def test_screenshot_is_a_jpeg_no_wider_than_the_limit(toolbox):
    box, _ = toolbox(screenshot_max_width=1280)
    box.call("set_viewport", {"width": 1440, "height": 900})
    result = box.call("screenshot", {})
    image = Image.open(io.BytesIO(result.image))
    assert image.format == "JPEG"
    assert image.width == 1280


def test_a_small_screen_screenshot_keeps_its_size(toolbox):
    box, _ = toolbox()
    box.call("set_viewport", {"width": 390, "height": 844})
    image = Image.open(io.BytesIO(box.call("screenshot", {}).image))
    assert (image.width, image.height) == (390, 844)


# --- acting and recording ------------------------------------------------------------------


def test_click_by_ref_acts_and_records_what_replay_needs(toolbox):
    box, page = toolbox()
    ref = ref_of(box, "button", "Add one")
    result = box.call("click", {"ref": ref})
    assert not result.is_error
    assert page.locator("#total").inner_text() == "1"
    action = result.action
    assert action.tool == "click" and action.replayable
    assert action.element["role"] == "button" and action.element["name"] == "Add one"
    assert action.element["css"]
    assert action.url.endswith("/deep.html")
    assert action.viewport == "1280x720"  # the test browser's default size


def test_type_and_press_enter_in_a_field(toolbox):
    box, page = toolbox()
    ref = ref_of(box, "searchbox", "Search")
    box.call("type", {"ref": ref, "text": "lamp"})
    result = box.call("press_key", {"key": "Enter", "ref": ref})
    assert not result.is_error
    assert page.locator("#searched").inner_text() == "Searched: lamp"
    assert result.action.replayable and result.action.element["name"] == "Search"


def test_hover_shows_what_hover_shows(toolbox):
    box, page = toolbox()
    result = box.call("hover", {"ref": ref_of(box, "button", "More")})
    assert not result.is_error and result.action.replayable
    assert page.locator("#tip").is_visible()


def test_a_css_selector_works_where_no_ref_fits(toolbox):
    box, page = toolbox()
    result = box.call("click", {"selector": "#add"})
    assert not result.is_error
    assert page.locator("#total").inner_text() == "1"
    assert result.action.element["css"] == "#add"


def test_a_selector_must_point_at_exactly_one_element(toolbox):
    box, _ = toolbox()
    result = box.call("click", {"selector": "button"})
    assert result.is_error and "2 elements" in result.text


def test_a_stale_ref_asks_for_a_new_snapshot(toolbox):
    box, _ = toolbox()
    result = box.call("click", {"ref": 999})
    assert result.is_error and "snapshot" in result.text


def test_set_viewport_takes_any_size_within_reason(toolbox):
    box, page = toolbox()
    result = box.call("set_viewport", {"width": 768, "height": 1024})
    assert page.viewport_size == {"width": 768, "height": 1024}
    assert result.action.replayable and result.action.args == {"width": 768, "height": 1024}
    assert box.call("set_viewport", {"width": 20, "height": 20}).is_error


def test_scroll_and_go_back_are_recorded(toolbox):
    box, page = toolbox()
    box.call("navigate", {"url": "/form.html"})
    assert box.call("scroll", {"direction": "down"}).action.replayable
    box.call("go_back", {})
    assert page.url.endswith("/deep.html")


def test_actions_that_only_look_are_not_replayed():
    assert {"screenshot", "snapshot", "visible_text", "evaluate_js", "console"}.isdisjoint(
        REPLAYED_TOOLS
    )
    assert {"click", "type", "press_key", "hover", "navigate", "set_viewport"} <= REPLAYED_TOOLS


# --- safety --------------------------------------------------------------------------------


def test_the_deny_list_blocks_a_destructive_click(toolbox):
    box, page = toolbox("/form.html")
    result = box.call("click", {"ref": ref_of(box, "button", "Delete account")})
    assert result.is_error and result.action.blocked
    assert "delete" in result.action.block_reason.lower()
    assert page.locator("#status").inner_text() == ""


def test_the_deny_list_also_blocks_enter_on_a_destructive_button(toolbox):
    box, page = toolbox("/form.html")
    result = box.call("press_key", {"key": "Enter", "ref": ref_of(box, "button", "Delete account")})
    assert result.action.blocked
    assert page.locator("#status").inner_text() == ""


def test_navigation_off_the_target_is_blocked(toolbox):
    box, page = toolbox()
    result = box.call("navigate", {"url": "https://example.com/"})
    assert result.action.blocked
    assert page.url.endswith("/deep.html")


def test_a_button_that_leaves_the_site_is_undone(toolbox):
    box, page = toolbox("/offsite.html")
    result = box.call("click", {"ref": ref_of(box, "button", "Continue")})
    assert result.action.blocked
    assert page.url.endswith("/offsite.html")


def test_unknown_tools_and_bad_arguments_are_errors_not_crashes(toolbox):
    box, _ = toolbox()
    assert box.call("teleport", {}).is_error
    assert box.call("type", {"ref": "x"}).is_error


# --- measuring -----------------------------------------------------------------------------


def test_evaluate_js_returns_a_measurement(toolbox):
    box, _ = toolbox()
    result = box.call(
        "evaluate_js",
        {"snippet": "return getComputedStyle(document.querySelector('#faint')).color"},
    )
    assert not result.is_error
    assert json.loads(result.data_text())["value"] == "rgb(187, 187, 187)"


def test_evaluate_js_says_when_a_snippet_changed_the_page(toolbox):
    box, _ = toolbox()
    result = box.call(
        "evaluate_js", {"snippet": "document.querySelector('#add').click(); return 1"}
    )
    assert json.loads(result.data_text())["changed_the_page"] is True


def test_evaluate_js_cannot_send_data(toolbox):
    box, _ = toolbox()
    result = box.call(
        "evaluate_js",
        {
            "snippet": "try { await fetch('/api/x', {method: 'POST', body: 'x'}); return 'sent' }"
            " catch (e) { return 'failed' }"
        },
    )
    data = json.loads(result.data_text())
    assert data["value"] == "failed"
    assert data["blocked_requests"] == ["POST /api/x"]


def test_evaluate_js_reports_a_thrown_error(toolbox):
    box, _ = toolbox()
    result = box.call("evaluate_js", {"snippet": "throw new Error('nope')"})
    assert "nope" in json.loads(result.data_text())["error"]


def test_page_source_is_the_html_the_server_sent(toolbox):
    box, page = toolbox()
    page.evaluate("document.querySelector('h1').textContent = 'Changed later'")
    result = box.call("page_source", {})
    assert "Deep tools" in result.text and "Changed later" not in result.text
    assert "/deep.js" in result.text  # the scripts it loads are listed


def test_read_script_returns_a_loaded_script(toolbox, site_url):
    box, _ = toolbox()
    result = box.call("read_script", {"url": f"{site_url}/deep.js"})
    assert "total += 1" in result.text


def test_read_script_never_fetches_something_new(toolbox, site_url):
    box, _ = toolbox()
    result = box.call("read_script", {"url": f"{site_url}/counter.js"})
    assert result.is_error and "not loaded" in result.text


# --- evidence ------------------------------------------------------------------------------


def test_console_and_network_since_a_mark(toolbox):
    box, _ = toolbox()
    first = box.call("console", {"since": 0}).text
    assert "deep.js loaded" in first  # the page's own warning
    mark = box.mark
    box.call("navigate", {"url": "/problems.html"})
    console = box.call("console", {"since": mark}).text
    assert "boom from console" in console and "deep.js loaded" not in console
    network = box.call("network", {"since": mark}).text
    assert "500" in network and "/status/500" in network


def test_errors_are_logged_per_page_for_deterministic_findings(toolbox):
    box, _ = toolbox()
    box.call("navigate", {"url": "/problems.html"})
    box.call("snapshot", {})  # a later call files what arrived after the navigation settled
    problems = next(page for url, page in box.pages.items() if url.endswith("/problems.html"))
    errors = {(e.kind, e.text) for e in problems.console_errors}
    assert ("console", "boom from console") in errors
    assert any(kind == "pageerror" and "uncaught boom" in text for kind, text in errors)
    assert any(r.url.endswith("/status/500") and r.status == 500 for r in problems.failed_requests)
    start = next(page for url, page in box.pages.items() if url.endswith("/deep.html"))
    assert [w.text for w in start.console_warnings] == ["deep.js loaded"]


def test_the_models_own_snippets_are_not_logged_as_site_errors(toolbox):
    box, _ = toolbox()
    box.call("evaluate_js", {"snippet": "console.error('from the model'); return 1"})
    box.call("snapshot", {})
    logged = [e.text for page in box.pages.values() for e in page.console_errors]
    assert "from the model" not in logged


def test_every_result_carries_the_current_mark(toolbox):
    box, _ = toolbox()
    result = box.call("snapshot", {})
    assert f"mark {box.mark}" in result.text


# --- our checks as tools -------------------------------------------------------------------


def test_axe_finds_the_low_contrast_text(toolbox):
    box, _ = toolbox()
    result = box.call("run_axe", {})
    assert "color-contrast" in result.text and "#faint" in result.text


def test_layout_check_at_a_phone_width(toolbox):
    box, _ = toolbox("/layout.html")
    box.call("set_viewport", {"width": 390, "height": 844})
    result = box.call("check_layout", {})
    assert not result.is_error and "overflow" in result.text


def test_meta_check(toolbox):
    box, _ = toolbox("/form.html")
    assert "og:title missing" in box.call("check_meta", {}).text


def test_keyboard_probe_opens_a_control_and_checks_it(toolbox):
    box, _ = toolbox("/keyboard.html")
    result = box.call("keyboard_probe", {"ref": ref_of(box, "button", "Open bad dialog")})
    assert not result.is_error
    assert "dialog" in result.text and "Escape" in result.text
    # Its key presses (Tab, Escape) leave the page in a state replay can't rebuild exactly, so
    # a probe is evidence, not a step to repeat.
    assert result.action.tool == "keyboard_probe" and not result.action.replayable


def test_every_tool_the_model_is_offered_has_a_handler_and_back(toolbox):
    from worker.deep.tools import BROWSER_TOOL_NAMES

    box, _ = toolbox()
    assert set(box._handlers) == BROWSER_TOOL_NAMES
