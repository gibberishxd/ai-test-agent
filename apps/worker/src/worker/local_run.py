"""One interactive run against any app on this machine (an external fixture), from the command line.

    uv run worker run-local http://localhost:PORT/ [--viewport 390x844] [--data-dir DIR]
                            [--export FILE]

For testing an app that isn't one of our demo shops without the web app: the app must be on
localhost / 127.0.0.1 with an explicit port, and DEV_MODE=true must be set (only then do local
apps get past the network guard). Only this app is allowed for the run (LOCAL_APP_URLS is
replaced, not extended). Screenshots go to --data-dir instead of DATA_DIR, so a run's artifacts
can live outside the repo. Budgets are the worker's usual ones (MAX_STEPS, MAX_RUN_SECONDS,
MAX_RUN_COST_USD). The run is stored in the "local-runs" workspace.
"""

from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Browser
from sqlalchemy.orm import Session, sessionmaker

from worker.browser import parse_viewport
from worker.config import Settings
from worker.db.models import Bug, Run, Workspace
from worker.execute import make_execute
from worker.export import write_export
from worker.llm import LLMClient
from worker.runner import process_next
from worker.storage import make_storage

LOCAL_WORKSPACE_SLUG = "local-runs"
LOCAL_HOSTS = ("localhost", "127.0.0.1")


def local_origin(url: str) -> str:
    """`scheme://host:port` of a URL on this machine; ValueError for anything else."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.hostname not in LOCAL_HOSTS:
        raise ValueError(f"not a localhost URL: {url!r}")
    if parts.port is None:
        raise ValueError(f"give the app's port explicitly: {url!r}")
    return f"{parts.scheme}://{parts.hostname}:{parts.port}"


def local_settings(settings: Settings, url: str, data_dir: Path) -> Settings:
    """The settings for one local run: this app allowed (only it), artifacts in `data_dir`."""
    if not settings.dev_mode:
        raise ValueError("DEV_MODE=true is required to test an app on localhost")
    return settings.model_copy(
        update={"local_app_urls": local_origin(url), "data_dir": str(data_dir.resolve())}
    )


def queue_local_run(session: Session, url: str, viewport: str | None) -> str:
    """Queue an interactive run of `url` at `viewport` (None = desktop); returns its id."""
    if viewport is not None:
        parse_viewport(viewport)  # refuse a bad size before anything is stored
    workspace = session.query(Workspace).filter_by(slug=LOCAL_WORKSPACE_SLUG).one_or_none()
    if workspace is None:
        workspace = Workspace(name="Local runs", slug=LOCAL_WORKSPACE_SLUG)
        session.add(workspace)
        session.flush()
    run = Run(workspace_id=workspace.id, target_url=url, mode="interactive", viewport=viewport)
    session.add(run)
    session.commit()
    return str(run.id)


def run_local(
    sessions: sessionmaker[Session],
    settings: Settings,
    llm: LLMClient,
    url: str,
    viewport: str | None,
    export: Path | None = None,
    browser: Browser | None = None,
) -> dict:
    """Queue, run and (with `export`) export one run; returns a short summary of it.
    `settings` come from local_settings()."""
    with sessions() as session:
        run_id = queue_local_run(session, url, viewport)
    execute = make_execute(settings, make_storage(settings), browser)
    process_next(sessions, llm, execute, only=[run_id])
    with sessions() as session:
        run = session.get(Run, run_id)
        findings = session.query(Bug).filter_by(run_id=run.id).count()
        if export is not None:
            write_export(session, run_id, export, data_dir=settings.data_path())
        return {
            "run_id": run_id,
            "status": run.status,
            "error": run.error,
            "stop_reason": (run.summary or {}).get("stop_reason"),
            "cost_usd": run.cost_usd,
            "findings": findings,
            "export": str(export) if export else None,
        }
