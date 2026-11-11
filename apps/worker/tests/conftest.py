"""Shared pytest fixtures: a local test site and a real headless browser.

pytest finds this file automatically; any test can ask for these fixtures by parameter name.
"""

import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import sync_playwright

SITE_DIR = Path(__file__).parent / "fixtures" / "site"


class QuietHandler(SimpleHTTPRequestHandler):
    """Serves the test site's files, plus two test endpoints, without logging each request.

    /status/<code>  → an empty response with that HTTP status (e.g. /status/500)
    /redirect?to=X  → a 302 redirect to X
    """

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path.startswith("/status/"):
            self.send_response(int(parts.path.rsplit("/", 1)[1]))
            self.end_headers()
            return
        if parts.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", parse_qs(parts.query)["to"][0])
            self.end_headers()
            return
        super().do_GET()

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


# --- Database fixtures -------------------------------------------------------------------------

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "apps" / "web" / "prisma" / "migrations"
TEST_DB = "agent_test"


def apply_migrations(engine) -> None:
    """Run Prisma's migration SQL files in order: the real schema, without needing Node."""
    with engine.begin() as conn:
        for sql_file in sorted(MIGRATIONS_DIR.glob("*/migration.sql")):
            conn.exec_driver_sql(sql_file.read_text().replace("%", "%%"))  # % is a placeholder


@pytest.fixture(scope="session")
def db_engine():
    """A fresh `agent_test` database with the current schema, for the whole session.

    Skips DB tests when Postgres isn't running (`npm run db:up`), unless REQUIRE_DB=1 (CI),
    where a missing database is a failure.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import OperationalError

    from worker.config import Settings

    admin_url = Settings().sqlalchemy_url()
    try:
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
        admin.dispose()
    except OperationalError as error:
        if os.environ.get("REQUIRE_DB") == "1":
            raise
        pytest.skip(f"Postgres not reachable ({error.__class__.__name__}); run `npm run db:up`")

    engine = create_engine(make_url(admin_url).set(database=TEST_DB))
    apply_migrations(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def sessions(db_engine):
    """A session factory on an emptied test database."""
    from sqlalchemy import text

    from worker.db.models import Base
    from worker.db.session import make_session_factory

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    return make_session_factory(db_engine)


@pytest.fixture
def workspace(sessions):
    from worker.db.models import Workspace

    with sessions() as session:
        ws = Workspace(name="Test workspace", slug="test")
        session.add(ws)
        session.commit()
        return ws
