"""Worker entry point: `uv run worker` polls the queue forever; `--once` processes one run."""

import argparse
import logging
import time

from worker.config import get_settings
from worker.db.session import make_engine, make_session_factory
from worker.llm import make_client
from worker.runner import process_next

POLL_INTERVAL_S = 1.0

log = logging.getLogger("worker")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="worker", description="AI Test Agent worker")
    parser.add_argument("--once", action="store_true", help="process at most one run, then exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[worker] %(levelname)s %(message)s")
    settings = get_settings()
    llm = make_client(settings)
    sessions = make_session_factory(make_engine(settings))
    log.info("ready. provider=%s model=%s", llm.provider, llm.agent_model)

    if args.once:
        if not process_next(sessions, llm):
            log.info("queue is empty")
        return

    while True:
        if not process_next(sessions, llm):
            time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
