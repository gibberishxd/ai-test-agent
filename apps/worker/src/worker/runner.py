"""Takes one claimed run from "running" to a final status.

`execute` is where the real work plugs in: the passive scan (M3) and the agent loop (M4).
Whatever happens inside, the run always ends as done, failed or stopped, never stuck in running.
"""

import logging
import os
import socket
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from worker.db.models import Run, RunStatus
from worker.llm import LLMClient
from worker.queue import claim_next_run, transition

log = logging.getLogger(__name__)

# (session, run, llm) -> None. Raises on failure; sets nothing about the final status.
ExecuteFn = Callable[[Session, Run, LLMClient], None]


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def noop_execute(session: Session, run: Run, llm: LLMClient) -> None:
    """Placeholder work until the scan and agent loop exist: just proves the plumbing."""


def process_next(
    sessions: sessionmaker[Session], llm: LLMClient, execute: ExecuteFn = noop_execute
) -> bool:
    """Claim and process one run. Returns False when the queue was empty."""
    with sessions() as session:
        run = claim_next_run(session, worker_id())
        if run is None:
            return False
        log.info("claimed run %s (%s, %s)", run.id, run.mode, run.target_url)
        run.provider = llm.provider
        run.model = llm.agent_model
        session.commit()

        try:
            execute(session, run, llm)
        except Exception as error:  # any failure ends the run as "failed", with the reason
            session.rollback()
            log.exception("run %s failed", run.id)
            transition(run, RunStatus.FAILED, error=f"{type(error).__name__}: {error}")
            session.commit()
            return True

        session.refresh(run, ["stop_requested"])
        final = RunStatus.STOPPED if run.stop_requested else RunStatus.DONE
        transition(run, final)
        session.commit()
        log.info("run %s %s", run.id, final)
        return True
