"""Worker entry point.

uv run worker             poll the run queue forever (what `npm run dev` starts)
uv run worker --once      process at most one queued run, then exit
uv run worker scan URL    passive scan without the database; writes reports/<time>/report.json
"""

import argparse
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from worker.config import REPO_ROOT, get_settings
from worker.db.session import make_engine, make_session_factory
from worker.execute import make_execute
from worker.llm import make_client
from worker.queue import recover_stale_runs
from worker.report import write_report
from worker.runner import process_next
from worker.safety.secrets import RedactingFilter
from worker.scan import passive_scan
from worker.storage import LocalStorage

POLL_INTERVAL_S = 1.0
STALE_GRACE_S = 300

log = logging.getLogger("worker")


def setup_logging(known_secrets: tuple[str, ...]) -> None:
    logging.basicConfig(level=logging.INFO, format="[worker] %(levelname)s %(message)s")
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactingFilter(known_secrets))  # rule 6.6: no secrets in logs


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="worker", description="AI Test Agent worker")
    parser.add_argument("--once", action="store_true", help="process at most one run, then exit")
    sub = parser.add_subparsers(dest="command")
    scan = sub.add_parser("scan", help="passive scan of a URL, report written to disk")
    scan.add_argument("url")
    scan.add_argument("--out", type=Path, help="output folder (default: reports/<timestamp>)")
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging((settings.anthropic_api_key.get_secret_value(),))

    if args.command == "scan":
        out = args.out or REPO_ROOT / "reports" / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        report = passive_scan(args.url, settings, LocalStorage(out), key_prefix="screenshots")
        write_report(report, out / "report.json")
        log.info("%d pages, %d bugs → %s", len(report.pages), len(report.bugs), out / "report.json")
        for bug in report.bugs:
            log.info("  [%s] %s", bug.severity, bug.title)
        return

    llm = make_client(settings)
    sessions = make_session_factory(make_engine(settings))
    execute = make_execute(settings, LocalStorage(settings.data_path()))
    with sessions() as session:
        # A run can't legitimately take longer than its time budget plus a grace period.
        recovered = recover_stale_runs(session, settings.max_run_seconds + STALE_GRACE_S)
    if recovered:
        log.warning("marked %d stale run(s) as failed", recovered)
    log.info("ready. provider=%s model=%s", llm.provider, llm.agent_model)

    if args.once:
        if not process_next(sessions, llm, execute):
            log.info("queue is empty")
        return
    while True:
        if not process_next(sessions, llm, execute):
            time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
