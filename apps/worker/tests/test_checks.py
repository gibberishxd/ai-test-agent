"""The deterministic checks, against real pages with known problems (tests/fixtures/site)."""

from urllib.parse import urlsplit

import pytest

from worker.browser import VisitOptions, visit_page
from worker.safety.network import NetworkGuard
from worker.safety.proxy import GuardProxy


@pytest.fixture
def problems(context, site_url):
    saved = []

    def save(png: bytes, url: str) -> str:
        saved.append(png)
        return f"shot-{len(saved)}.png"

    def save_mobile(png: bytes, url: str) -> str:
        saved.append(png)
        return "shot-mobile.png"

    options = VisitOptions(save_screenshot=save, save_mobile_screenshot=save_mobile)
    page, links = visit_page(context, f"{site_url}/problems.html", options)
    return page, links, saved


def test_collects_console_errors_and_uncaught_exceptions(problems):
    page, _, _ = problems
    by_kind = {(e.kind, e.text) for e in page.console_errors}
    assert ("console", "boom from console") in by_kind
    assert ("pageerror", "Error: uncaught boom") in by_kind


def test_drops_chromes_failed_to_load_echo(problems):
    # Chrome also logs "Failed to load resource: ... 404" for each failed request. That's
    # already a failed-request finding, so it isn't repeated as a console error.
    page, _, _ = problems
    assert not any(e.text.startswith("Failed to load resource") for e in page.console_errors)


def test_collects_4xx_and_5xx_responses(problems):
    page, _, _ = problems
    failed = {(urlsplit(r.url).path, r.status, r.resource_type) for r in page.failed_requests}
    assert ("/missing.png", 404, "image") in failed
    assert ("/status/500", 500, "fetch") in failed


def test_runs_axe(problems):
    page, _, _ = problems
    assert "image-alt" in {v.rule_id for v in page.a11y_violations}


def test_takes_a_screenshot_and_times_the_load(problems):
    page, _, saved = problems
    assert page.screenshot == "shot-1.png"
    assert saved[0].startswith(b"\x89PNG")
    assert page.load_ms is not None


def png_width(png: bytes) -> int:
    return int.from_bytes(png[16:20], "big")  # the IHDR chunk starts with width, height


def test_also_takes_a_phone_width_screenshot(problems):
    page, _, saved = problems
    assert page.mobile_screenshot == "shot-mobile.png"
    assert png_width(saved[0]) == 1280
    assert png_width(saved[1]) == 375


def test_clean_page_has_no_findings(context, site_url):
    page, _ = visit_page(context, f"{site_url}/clean.html")
    assert page.console_errors == []
    assert page.failed_requests == []
    assert page.a11y_violations == []
    assert page.soft_404 is False


def test_detects_soft_404(context, site_url):
    page, _ = visit_page(context, f"{site_url}/notfound.html")
    assert page.status == 200
    assert page.soft_404 is True


@pytest.fixture
def guarded_context(browser, site_url):
    """A browser context whose traffic goes through the guard proxy. The test site itself is
    allowed (like our demo shops in dev mode); everything else must be public."""
    port = urlsplit(site_url).port
    guard = NetworkGuard(allowed_local={("127.0.0.1", port)}, target_url=f"{site_url}/")
    with GuardProxy(guard) as proxy:
        context = browser.new_context(proxy=proxy.playwright_config)
        yield context, guard
        context.close()


def test_guard_blocks_a_redirect_to_a_private_address(guarded_context, site_url):
    # Rule 6.1: re-check after every redirect. The test site is allowed, but it redirects to an
    # internal address; that second hop must be refused.
    context, guard = guarded_context
    page, _ = visit_page(context, f"{site_url}/redirect?to=http://10.0.0.5/admin")
    assert page.status == 403 or page.error is not None
    assert [b.url for b in guard.blocked] == ["http://10.0.0.5/admin"]


def test_guard_blocks_localhost_services(guarded_context):
    # Postgres, the web app, anything else on this machine: not reachable from the browser.
    context, guard = guarded_context
    visit_page(context, "http://127.0.0.1:5432/")
    assert guard.blocked and "private" in guard.blocked[0].reason


def test_guard_lets_normal_pages_through(guarded_context, site_url):
    context, guard = guarded_context
    page, links = visit_page(context, f"{site_url}/problems.html")
    assert page.status == 200
    assert guard.blocked == []
    assert ("/status/500", 500) in {(urlsplit(r.url).path, r.status) for r in page.failed_requests}
