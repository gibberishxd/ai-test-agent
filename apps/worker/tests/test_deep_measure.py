"""Verifying deep mode's measurement and check findings: the stored snippet or check is run
again in a fresh page, at the same viewport, after the same setup steps. The same result
confirms it; a different one dismisses it; a setup that can't be repeated leaves it
unverified."""

from urllib.parse import urlsplit

import pytest

from worker.deep.measure import same_result, verify_measurement
from worker.deep.toolbox import Toolbox, ToolboxConfig
from worker.safety.network import NetworkGuard
from worker.verify import ReplayStep

COLOR = "return getComputedStyle(document.querySelector('#faint')).color"
ADD = {"role": "button", "name": "Add one", "css": "#add"}


@pytest.fixture
def check(context, site_url):
    guard = NetworkGuard(
        allowed_local={("127.0.0.1", urlsplit(site_url).port)}, target_url=f"{site_url}/"
    )

    def run(spec, setup=(), target="/deep.html"):
        return verify_measurement(
            context, guard, spec, list(setup), target_url=f"{site_url}{target}"
        )

    return run, site_url


def measure(site_url, snippet, result, url="/deep.html", viewport="1280x720"):
    return {
        "kind": "measure",
        "snippet": snippet,
        "result": result,
        "url": f"{site_url}{url}",
        "viewport": viewport,
    }


def test_the_same_measurement_confirms(check):
    run, site = check
    verdict = run(measure(site, COLOR, "rgb(187, 187, 187)"))
    assert verdict.status == "confirmed", verdict.reason


def test_a_different_measurement_dismisses(check):
    run, site = check
    verdict = run(measure(site, COLOR, "rgb(0, 0, 0)"))
    assert verdict.status == "dismissed"
    assert "rgb(187, 187, 187)" in verdict.reason and "rgb(0, 0, 0)" in verdict.reason


def test_it_is_measured_at_the_reported_viewport(check):
    run, site = check
    verdict = run(measure(site, "return window.innerWidth", 390, viewport="390x844"))
    assert verdict.status == "confirmed", verdict.reason


def test_setup_steps_are_replayed_first(check):
    run, site = check
    spec = measure(site, "return document.querySelector('#total').textContent", "2")
    steps = [ReplayStep("click", {}, ADD, f"{site}/deep.html")] * 2
    verdict = run(spec, steps)
    assert verdict.status == "confirmed", verdict.reason


def test_a_setup_that_cant_be_repeated_leaves_it_unverified(check):
    run, site = check
    spec = measure(site, "return 1", 1)
    missing = {"role": "button", "name": "Not on the page", "css": "#nope"}
    verdict = run(spec, [ReplayStep("click", {}, missing, f"{site}/deep.html")])
    assert verdict.status == "unverified"


def test_a_snippet_that_throws_now_leaves_it_unverified(check):
    run, site = check
    verdict = run(measure(site, "throw new Error('gone')", 1))
    assert verdict.status == "unverified" and "gone" in verdict.reason


def test_an_axe_rule_on_the_same_element_confirms(check):
    run, site = check
    spec = {
        "kind": "check",
        "check": "run_axe",
        "rule": "color-contrast",
        "result": {"rule_id": "color-contrast", "targets": ["#faint"]},
        "url": f"{site}/deep.html",
        "viewport": "1280x720",
    }
    assert run(spec).status == "confirmed"


def test_an_axe_rule_on_another_element_dismisses(check):
    run, site = check
    spec = {
        "kind": "check",
        "check": "run_axe",
        "rule": "color-contrast",
        "result": {"rule_id": "color-contrast", "targets": ["#somewhere-else"]},
        "url": f"{site}/deep.html",
        "viewport": "1280x720",
    }
    assert run(spec).status == "dismissed"


def test_a_meta_problem_confirms(check):
    run, site = check
    spec = {
        "kind": "check",
        "check": "check_meta",
        "rule": "og:title",
        "result": "og:title missing",
        "url": f"{site}/form.html",
        "viewport": "1280x720",
    }
    assert run(spec, target="/form.html").status == "confirmed"


def test_a_layout_problem_is_checked_at_its_viewport(check):
    run, site = check
    spec = {
        "kind": "check",
        "check": "check_layout",
        "rule": "overflow",
        "result": {"rule": "overflow"},
        "url": f"{site}/layout.html",
        "viewport": "390x844",
    }
    assert run(spec, target="/layout.html").status == "confirmed"
    fits = {**spec, "url": f"{site}/layout-ok.html"}
    assert run(fits, target="/layout-ok.html").status == "dismissed"


def test_a_keyboard_probe_finding_is_probed_again(check, context, site_url):
    # First learn what the probe reports on this control, the way the harness stores it.
    guard = NetworkGuard(allowed_local={("127.0.0.1", urlsplit(site_url).port)})
    box = Toolbox(context.new_page(), guard, ToolboxConfig(target_url=f"{site_url}/keyboard.html"))
    box.start()
    probed = box.call("keyboard_probe", {"selector": "#open-bad"})
    failed = probed.data["failures"][0]
    run, site = check
    spec = {
        "kind": "check",
        "check": "keyboard_probe",
        "rule": failed["check"],
        "result": failed,
        "element": probed.action.element,
        "url": f"{site}/keyboard.html",
        "viewport": probed.action.viewport,
    }
    assert run(spec, target="/keyboard.html").status == "confirmed"
    passing = {**spec, "rule": "a check this control passes"}
    assert run(passing, target="/keyboard.html").status == "dismissed"


@pytest.mark.parametrize(
    "a, b, same",
    [
        (12.04, 12.0, True),
        (12.2, 12.0, False),
        ({"b": 1, "a": [1.001, "x"]}, {"a": [1.0, "x"], "b": 1}, True),
        ("rgb(1, 2, 3)", "rgb(1, 2, 3)", True),
        (None, 0, False),
    ],
)
def test_same_result_allows_rounding_only(a, b, same):
    assert same_result(a, b) is same
