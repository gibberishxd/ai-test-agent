"""The keyboard probe, on a synthetic page with a good and a bad dialog, menu and toggle."""

import pytest

from worker.keyboard_probe import (
    LOW,
    MEDIUM,
    opened_by,
    probe_finding,
    probe_opened,
    snapshot,
)
from worker.verify import ReplayStep


def button(name: str, css: str | None = None) -> dict:
    return {"role": "button", "name": name, "css": css}


def opened(context, site_url, control: dict) -> str | None:
    """Click `control` on the page and say what it opened."""
    page = context.new_page()
    try:
        page.goto(f"{site_url}/keyboard.html")
        snapshot(page)
        locator = (
            page.locator(control["css"])
            if control.get("css")
            else page.get_by_role("button", name=control["name"], exact=True)
        )
        handle = locator.element_handle()
        locator.click()
        page.wait_for_timeout(100)
        return opened_by(page, handle)
    finally:
        page.close()


@pytest.mark.parametrize(
    ("control", "kind"),
    [
        (button("Open good dialog"), "dialog"),
        (button("Open bad dialog"), "dialog"),  # a fixed layer over the screen, no role
        (button("Main menu"), "menu"),
        (button("", "#menu-bad"), "menu"),
        (button("Shipping details"), "disclosure"),
        (button("Return policy"), "disclosure"),
        (button("Save"), None),  # new status text is a response, not something opened
    ],
)
def test_what_a_click_opened(context, site_url, control, kind):
    assert opened(context, site_url, control) == kind


def probed(context, site_url, control: dict, kind: str):
    url = f"{site_url}/keyboard.html"
    steps = [ReplayStep("click", {}, control, url)]
    return probe_opened(context, [(url, steps)], kind, "desktop")


def checks(result) -> dict[str, str]:
    return {f["check"]: f["severity"] for f in result.failures}


def test_a_good_dialog_passes(context, site_url):
    result = probed(context, site_url, button("Open good dialog"), "dialog")
    assert result is not None and result.failures == []


def test_a_bad_dialog_fails_every_check(context, site_url):
    result = probed(context, site_url, button("Open bad dialog"), "dialog")
    assert checks(result) == {
        "role": LOW,
        "aria-modal": LOW,
        "focus-in": MEDIUM,
        "focus-trap": MEDIUM,
        "escape": MEDIUM,
    }
    assert result.severity == MEDIUM


def test_a_good_menu_passes(context, site_url):
    assert probed(context, site_url, button("Main menu"), "menu").failures == []


def test_a_bad_menu(context, site_url):
    result = probed(context, site_url, button("", "#menu-bad"), "menu")
    assert checks(result) == {"aria-expanded": LOW, "name": LOW, "escape": MEDIUM}


def test_disclosures(context, site_url):
    assert probed(context, site_url, button("Shipping details"), "disclosure").failures == []
    result = probed(context, site_url, button("Return policy"), "disclosure")
    assert checks(result) == {"aria-expanded": LOW}
    assert result.severity == LOW


def test_nothing_to_probe_when_the_click_no_longer_opens_it(context, site_url):
    assert probed(context, site_url, button("Save"), "dialog") is None


def test_one_finding_per_failing_control(context, site_url):
    result = probed(context, site_url, button("Open bad dialog"), "dialog")
    bug = probe_finding(result)
    assert bug.category == "accessibility"
    assert bug.severity == "medium"
    assert bug.source == "deterministic" and bug.status == "confirmed"
    assert 'button "Open bad dialog"' in bug.title
    assert bug.evidence["control"]["name"] == "Open bad dialog"
    assert {f["check"] for f in bug.evidence["failures"]} >= {"focus-in", "escape"}


def test_fingerprints_differ_per_control(context, site_url):
    from worker.fingerprint import fingerprint

    one = probe_finding(probed(context, site_url, button("Open bad dialog"), "dialog"))
    two = probe_finding(probed(context, site_url, button("Return policy"), "disclosure"))
    assert fingerprint(one) != fingerprint(two)
