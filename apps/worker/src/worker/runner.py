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
from worker.queue import Heartbeat, claim_next_run, transition
from worker.webhooks import enqueue_run_finished

log = logging.getLogger(__name__)

# (session, run, llm) -> None. Raises on failure; sets nothing about the final status.
ExecuteFn = Callable[[Session, Run, LLMClient], None]


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def noop_execute(session: Session, run: Run, llm: LLMClient) -> None:
    """Placeholder work until the scan and agent loop exist: just proves the plumbing."""


ClientFor = Callable[[Session, Run, LLMClient], LLMClient]

LEASE_S = 60  # a run whose worker is silent this long is failed by another worker
HEARTBEAT_S = LEASE_S / 4  # several beats per lease, so one slow beat doesn't lose it


def process_next(
    sessions: sessionmaker[Session],
    llm: LLMClient,
    execute: ExecuteFn = noop_execute,
    client_for: ClientFor | None = None,
    only: list | None = None,
    skip_benchmark: bool = False,
) -> bool:
    """Claim and process one run. Returns False when the queue was empty.

    `only` / `skip_benchmark`: see claim_next_run (a benchmark and regular workers keep to
    their own runs)."""
    with sessions() as session:
        run = claim_next_run(session, worker_id(), only=only, skip_benchmark=skip_benchmark)
        if run is None:
            return False
        log.info("claimed run %s (%s, %s)", run.id, run.mode, run.target_url)

        try:
            with Heartbeat(sessions, run.id, HEARTBEAT_S):
                # The run's own model (a workspace model) or the worker's default.
                run_llm = client_for(session, run, llm) if client_for else llm
                run.provider = run_llm.provider
                run.model = run_llm.agent_model
                session.commit()
                execute(session, run, run_llm)
        except Exception as error:  # any failure ends the run as "failed", with the reason
            session.rollback()
            log.exception("run %s failed", run.id)
            if _still_ours(session, run):
                transition(run, RunStatus.FAILED, error=f"{type(error).__name__}: {error}")
                session.commit()
                enqueue_run_finished(session, run)
            session.commit()
            return True

        if not _still_ours(session, run):
            session.commit()
            return True
        final = RunStatus.STOPPED if run.stop_requested else RunStatus.DONE
        transition(run, final)
        session.commit()
        enqueue_run_finished(session, run)  # the workspace's webhooks, sent by deliver_due
        log.info("run %s %s", run.id, final)
        return True


def _still_ours(session: Session, run: Run) -> bool:
    """Lock the run's row and re-read it: is it still running (not failed by lease recovery)?

    The row lock (held until the caller commits) makes recovery's UPDATE wait, so a run can't
    be failed between this check and the final status being written.
    """
    session.refresh(run, ["status", "stop_requested"], with_for_update=True)
    if run.status != RunStatus.RUNNING:
        log.warning("run %s was %s while this worker worked on it; leaving it", run.id, run.status)
        return False
    return True
