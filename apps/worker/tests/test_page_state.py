"""Before/after page state for replay: what changed when the replayed action ran (K1).

A screenshot can't show that nothing happened. A diff of two compact page states can: no new
text, no field or storage change, no request, no dialog. These tests cover the capture, the diff,
and the harmless changes (a ticking clock, a spinner, polling) that must not count.
"""

import io

import pytest
from PIL import Image

from worker.page_state import (
    PageState,
    StateRecorder,
    claims_no_effect,
    diff_states,
    is_noise_line,
    side_by_side,
)


def run_action(context, url: str, selector: str = "button[type=submit]", fill: str | None = None):
    """Open `url`, optionally type a new name, capture, click, settle, capture again."""
    page = context.new_page()
    recorder = StateRecorder(page)
    page.goto(url)
    if fill is not None:
        page.fill("#name", fill)
    before = recorder.capture()
    page.click(selector)
    recorder.settle()
    after = recorder.capture()
    return before, after


def state(**fields) -> PageState:
    base = {"url": "http://shop.test/profile", "title": "Profile", "lines": ["Profile"]}
    return PageState(**{**base, **fields})


# --- Capture --------------------------------------------------------------------------------


def test_capture_records_url_text_fields_and_totals(context, site_url):
    page = context.new_page()
    recorder = StateRecorder(page)
    page.goto(f"{site_url}/state/dead.html")
    captured = recorder.capture()
    assert captured.url.endswith("/state/dead.html")
    assert "Hello, Demo User" in captured.lines
    assert captured.fields["Display name"] == "Demo User"
    assert captured.totals == ["Order total: $24.00"]


def test_capture_never_records_a_password_value(context, site_url):
    page = context.new_page()
    recorder = StateRecorder(page)
    page.goto(f"{site_url}/state/dead.html")
    captured = recorder.capture()
    assert captured.fields["Password"] == "••••"
    assert "hunter2" not in repr(captured)


# --- What counts as a change ----------------------------------------------------------------


def test_a_dead_save_button_changes_nothing(context, site_url):
    before, after = run_action(context, f"{site_url}/state/dead.html", fill="New Name")
    diff = diff_states(before, after)
    assert not diff.meaningful
    assert "no change" in diff.summary().lower()


def test_a_working_save_shows_the_new_text(context, site_url):
    before, after = run_action(context, f"{site_url}/state/works.html", fill="New Name")
    diff = diff_states(before, after)
    assert diff.meaningful
    assert "Saved" in diff.added
    assert "Hello, Demo User" in diff.removed
    assert "Saved" in diff.summary()


def test_a_request_counts_as_a_change(context, site_url):
    before, after = run_action(context, f"{site_url}/state/request.html")
    diff = diff_states(before, after)
    assert diff.meaningful
    assert any(r.startswith("POST /status/204") for r in diff.requests)


def test_a_storage_write_counts_as_a_change(context, site_url):
    before, after = run_action(context, f"{site_url}/state/storage.html")
    diff = diff_states(before, after)
    assert diff.meaningful
    assert diff.storage == ["localStorage.profile added"]


def test_a_toast_that_disappears_before_the_capture_still_counts(context, site_url):
    before, after = run_action(context, f"{site_url}/state/toast.html")
    diff = diff_states(before, after)
    assert diff.meaningful
    assert "Profile updated" in diff.transient


def test_a_dialog_counts_as_a_change(context, site_url):
    before, after = run_action(context, f"{site_url}/state/dialog.html")
    diff = diff_states(before, after)
    assert diff.meaningful
    assert diff.dialogs == ["alert: Saved!"]


def test_a_console_error_alone_is_shown_but_is_not_a_visible_response(context, site_url):
    """Users don't see the console: an error there with nothing on screen is still 'nothing
    happened' for them, and the error is evidence of why."""
    before, after = run_action(context, f"{site_url}/state/console.html")
    diff = diff_states(before, after)
    assert not diff.meaningful
    assert any("TypeError" in m for m in diff.console)
    assert "TypeError" in diff.summary()


# --- Harmless changes must not count ---------------------------------------------------------


def test_a_ticking_clock_and_a_spinner_are_not_a_change(context, site_url):
    before, after = run_action(context, f"{site_url}/state/noisy.html")
    diff = diff_states(before, after)
    assert not diff.meaningful, diff.summary()
    assert diff.ignored  # the summary says what was ignored, so the judge can see it


def test_polling_requests_that_ran_before_the_action_are_not_a_change(context, site_url):
    before, after = run_action(context, f"{site_url}/state/polling.html")
    diff = diff_states(before, after)
    assert not diff.meaningful, diff.summary()


@pytest.mark.parametrize(
    "line",
    [
        "Loading…",
        "Saving...",
        "Please wait",
        "Last updated 10:42:13",
        "Updated 3 seconds ago",
        "just now",
        "Synced at 2026-11-12 08:15",
    ],
)
def test_noise_lines(line):
    assert is_noise_line(line)


@pytest.mark.parametrize("line", ["Saved", "Total: $24.00", "Order #1042 placed", "Hello, Ana"])
def test_real_lines_are_not_noise(line):
    assert not is_noise_line(line)


def test_a_timestamp_that_only_changes_its_digits_is_ignored():
    before = state(lines=["Profile", "Last synced 10:42:13 by Ana"])
    after = state(lines=["Profile", "Last synced 10:42:19 by Ana"])
    assert not diff_states(before, after).meaningful


def test_a_changed_total_is_a_change_even_though_only_digits_change():
    before = state(lines=["Cart", "Total: $12.00"], totals=["Total: $12.00"])
    after = state(lines=["Cart", "Total: $24.00"], totals=["Total: $24.00"])
    diff = diff_states(before, after)
    assert diff.meaningful
    assert "Total: $12.00 → Total: $24.00" in diff.summary()


def test_a_changed_url_is_a_change():
    diff = diff_states(state(), state(url="http://shop.test/profile/saved"))
    assert diff.meaningful
    assert diff.url_change == ("http://shop.test/profile", "http://shop.test/profile/saved")


def test_typing_into_the_field_itself_is_not_the_response():
    """'Typing in search does nothing': the field's own new value is the action, not a
    response to it."""
    before = state(fields={"Search": ""})
    after = state(fields={"Search": "socks"})
    assert not diff_states(before, after, typed="socks").meaningful
    assert diff_states(before, after).meaningful


def test_storage_values_never_reach_the_summary():
    before = state(storage={"localStorage.token": "a1"})
    after = state(storage={"localStorage.token": "b2"})
    diff = diff_states(before, after)
    assert diff.storage == ["localStorage.token changed"]
    assert "a1" not in diff.summary() and "b2" not in diff.summary()


def test_a_wrong_change_is_described_by_the_diff(context, site_url):
    """A 'wrong change' report (quantity goes up, total stays) is confirmed by what the diff
    shows: the quantity changed and the total didn't."""
    page = context.new_page()
    recorder = StateRecorder(page)
    page.goto(f"{site_url}/state/wrong-total.html")
    before = recorder.capture()
    page.click("#plus")
    recorder.settle()
    diff = diff_states(before, recorder.capture())
    assert diff.meaningful
    assert "Socks × 2" in diff.added
    assert diff.transient == []  # the "2" that was drawn is part of a line still on the page
    assert "Totals unchanged: Total: $12.00" in diff.summary()


# --- Which reports claim that nothing happened -------------------------------------------------


@pytest.mark.parametrize(
    "title, actual",
    [
        ("'Save changes' on the profile does nothing", ""),
        ("Save changes button does not update profile display name", ""),
        ("Profile update button does not save changes", ""),
        ("Apply button", "Nothing happens when clicking Apply"),
        ("Submit has no effect", ""),
        ("No confirmation after saving", "The page shows no message and no error"),
        ("Clicking Subscribe gives no feedback", ""),
        ("Quantity spinbutton does not increment value", ""),
        ("Menu button doesn't open the menu", ""),
        ("Load more fails to load more items", ""),
    ],
)
def test_reports_that_claim_no_effect(title, actual):
    assert claims_no_effect(title, actual)


@pytest.mark.parametrize(
    "title, actual",
    [
        ("Cart total ignores quantity", "Total stays $12 with 2 items"),
        ("Wool Socks price shows $NaN", ""),
        ("Checkout accepts an invalid email", "The order is placed"),
        ("Opening an order shows a different order", ""),
    ],
)
def test_reports_of_a_wrong_change_are_not_no_effect_claims(title, actual):
    assert not claims_no_effect(title, actual)


# --- The image the judge gets ----------------------------------------------------------------


def _png(color: str, size=(40, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def test_side_by_side_puts_before_left_and_after_right():
    combined = Image.open(io.BytesIO(side_by_side(_png("red"), _png("blue"))))
    width, height = combined.size
    assert width >= 80 and height >= 30
    assert combined.getpixel((5, height - 5))[0] > 200  # red on the left
    assert combined.getpixel((width - 5, height - 5))[2] > 200  # blue on the right
