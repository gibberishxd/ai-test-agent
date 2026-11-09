"""Shared pytest fixtures: a local test site and a real headless browser.

pytest finds this file automatically; any test can ask for these fixtures by parameter name.
"""

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

SITE_DIR = Path(__file__).parent / "fixtures" / "site"


class QuietHandler(SimpleHTTPRequestHandler):
    """Serves files like the standard handler, without printing a line per request."""

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="session")
def site_url():
    """Serve tests/fixtures/site over real HTTP for the whole test session.

    Port 0 asks the OS for any free port, so tests never clash with something already running.
    The server runs in a background thread because serve_forever() blocks.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=SITE_DIR))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def browser():
    """One headless Chromium for all tests: launching it takes about a second."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def context(browser):
    """A fresh browser context (like a new incognito window) per test, so no state leaks."""
    context = browser.new_context()
    yield context
    context.close()
