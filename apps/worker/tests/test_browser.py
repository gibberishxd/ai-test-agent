"""Integration tests: a real headless Chromium against the local test site."""

import socket

from worker.browser import visit_page
from worker.crawler import crawl


def test_crawls_the_test_site(context, site_url):
    pages = crawl(f"{site_url}/", lambda url: visit_page(context, url))

    assert {p.url for p in pages} == {
        f"{site_url}/",
        f"{site_url}/about.html",
        f"{site_url}/products.html",  # only linked from JavaScript, after load
    }
    assert {p.title for p in pages} == {"Home", "About", "Products"}
    assert all(p.status == 200 for p in pages)


def test_missing_page_reports_404(context, site_url):
    page, links = visit_page(context, f"{site_url}/missing.html")
    assert page.status == 404
    assert page.error is None


def closed_port() -> int:
    """A port with nothing listening: the OS hands us a free one, then we release it.

    (Not a fixed port like 1: Chrome refuses "unsafe" ports before even trying to connect.)
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_unreachable_server_reports_error(context):
    page, links = visit_page(context, f"http://127.0.0.1:{closed_port()}/")
    assert page.status is None
    assert "ERR_CONNECTION_REFUSED" in page.error
    assert links == []
