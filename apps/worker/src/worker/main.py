"""Worker entry point.

uv run worker             poll the run queue forever (what `npm run dev` starts)
uv run worker --once      process at most one queued run, then exit
uv run worker scan URL    passive scan without the database; writes reports/<time>/report.json
uv run worker bench       benchmark: N runs on the buggy shop + 1 on the clean shop, scored
uv run worker reverify ID replay an old run's agent reports again (read-only); --judge asks
                          the pinned judge model too
"""

import argparse
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from worker.benchmark import (
    HOLDOUT_BUGS_JSON,
    BenchmarkScores,
    all_reports,
    benchmark_workspace,
    git_commit,
    judge_name,
    load_planted,
    print_scores,
    queue_runs,
    report_bugs,
    reviewer_of,
    save_scores,
    score,
    staged_match,
    wait_for,
)
from worker.config import REPO_ROOT, Settings, get_settings
from worker.db.models import BenchmarkResult, Run
from worker.db.session import make_engine, make_session_factory
from worker.execute import make_execute
from worker.llm import LLMClient, make_client, make_judge, make_reviewer
from worker.login_checks import process_login_check
from worker.logs import JsonFormatter
from worker.model_configs import client_for_run
from worker.queue import recover_expired_leases, recover_stale_runs
from worker.report import write_report
from worker.retention import apply_retention
from worker.runner import LEASE_S, ExecuteFn, process_next
from worker.safety.secrets import RedactingFilter
from worker.scan import passive_scan
from worker.storage import LocalStorage, make_storage
from worker.triage import backfill_fingerprints
from worker.webhooks import deliver_due

POLL_INTERVAL_S = 1.0
RETENTION_EVERY_S = 3600  # delete expired screenshots and steps once an hour
STALE_GRACE_S = 300

log = logging.getLogger("worker")


def setup_logging(known_secrets: tuple[str, ...]) -> None:
    logging.basicConfig(level=logging.INFO, format="[worker] %(levelname)s %(message)s")
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactingFilter(known_secrets))  # rule 6.6: no secrets in logs
        if os.environ.get("LOG_FORMAT") == "json":  # production: one JSON object per line
            handler.setFormatter(JsonFormatter())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="worker", description="AI Test Agent worker")
    parser.add_argument("--once", action="store_true", help="process at most one run, then exit")
    sub = parser.add_subparsers(dest="command")
    scan = sub.add_parser("scan", help="passive scan of a URL, report written to disk")
    scan.add_argument("url")
    scan.add_argument("--out", type=Path, help="output folder (default: reports/<timestamp>)")
    bench = sub.add_parser("bench", help="score the agent against the demo shop's planted bugs")
    bench.add_argument("--runs", type=int, default=3, help="runs on the buggy shop (default 3)")
    bench.add_argument(
        "--holdout-runs",
        type=int,
        default=2,
        help="runs on the buggy holdout app, apps/demo2 (default 2; 0 skips the holdout)",
    )
    bench.add_argument("--mode", choices=["interactive", "passive"], default="interactive")
    bench.add_argument(
        "--holdout-first",
        action="store_true",
        help="run the holdout app before the shop (judge a change on the holdout first)",
    )
    bench.add_argument(
        "--rescore", action="store_true", help="re-match the latest benchmark's runs, no new runs"
    )
    again = sub.add_parser("reverify", help="replay an old run's agent reports (read-only)")
    again.add_argument("run_id", help="the run's id (a unique prefix is enough)")
    again.add_argument("--judge", action="store_true", help="also ask JUDGE_* whether it shows")
    sub.add_parser(
        "backfill-fingerprints", help="give findings stored before run 4 their fingerprint (J4)"
    )
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

    if args.command == "reverify":
        reverify(settings, args.run_id, args.judge)
        return

    if args.command == "backfill-fingerprints":
        with make_session_factory(make_engine(settings))() as session:
            log.info("fingerprinted %d older finding(s)", backfill_fingerprints(session))
        return

    llm = make_client(settings)
    sessions = make_session_factory(make_engine(settings))
    reviewer = make_reviewer(settings)
    execute = make_execute(settings, make_storage(settings), reviewer=reviewer)
    with sessions() as session:
        # A run can't legitimately take longer than its time budget plus a grace period.
        recovered = recover_stale_runs(session, settings.max_run_seconds + STALE_GRACE_S)
    if recovered:
        log.warning("marked %d stale run(s) as failed", recovered)
    log.info("ready. provider=%s model=%s", llm.provider, llm.agent_model)
    if reviewer is not None:
        log.info("reviewer tier: provider=%s model=%s", reviewer.provider, reviewer.agent_model)

    def client_for(session, run, default):
        return client_for_run(session, run, default, settings)

    if args.command == "bench":
        judge = make_judge(settings, llm)
        log.info("benchmark judge: %s", judge_name(judge))
        if judge is llm and llm.provider == "ollama":
            log.warning(
                "the judge is the model under test; set JUDGE_MODEL to compare models fairly"
            )
    if args.command == "bench" and args.rescore:
        rescore_latest(sessions, judge)
        return
    if args.command == "bench":
        run_benchmark(
            settings,
            llm,
            judge,
            sessions,
            execute,
            args.runs,
            args.mode,
            args.holdout_runs,
            holdout_first=args.holdout_first,
        )
        return
    if args.once:
        if not process_next(sessions, llm, execute, client_for, skip_benchmark=True):
            log.info("queue is empty")
        return
    last_recovery = last_retention = 0.0
    storage = make_storage(settings)
    while True:
        if time.monotonic() - last_retention > RETENTION_EVERY_S:
            with sessions() as session:
                purged = apply_retention(session, storage)
            if purged["runs"]:
                log.info("retention: purged %d run(s), %d file(s)", purged["runs"], purged["files"])
            last_retention = time.monotonic()
        if time.monotonic() - last_recovery > LEASE_S / 2:  # any live worker cleans up
            with sessions() as session:
                if recovered := recover_expired_leases(session, LEASE_S):
                    log.warning("failed %d run(s) whose worker stopped responding", recovered)
            last_recovery = time.monotonic()
        # A "Test sign-in" is quick and someone is waiting for it: before the next run.
        checked = process_login_check(sessions, settings)
        deliver_due(sessions, settings)  # webhooks whose time has come
        busy = process_next(sessions, llm, execute, client_for, skip_benchmark=True)
        if not busy and not checked:
            time.sleep(POLL_INTERVAL_S)


def reverify(settings: Settings, run_prefix: str, use_judge: bool) -> None:
    from sqlalchemy import String, cast

    from worker.reverify import reverify_run

    sessions = make_session_factory(make_engine(settings))
    judge = make_judge(settings, make_client(settings)) if use_judge else None
    with sessions() as session:
        [run_id] = session.query(Run.id).filter(cast(Run.id, String).like(f"{run_prefix}%")).all()
        outcomes = reverify_run(session, uuid.UUID(str(run_id[0])), settings, judge=judge)
    print(json.dumps(outcomes, indent=2))


def run_benchmark(
    settings: Settings,
    llm: LLMClient,
    judge: LLMClient,
    sessions: sessionmaker[Session],
    execute: ExecuteFn,
    runs: int,
    mode: str,
    holdout_runs: int = 0,
    holdout_first: bool = False,
) -> None:
    """Queue the benchmark runs, process them with `llm`, then score them with `judge`.

    `holdout_first` queues the holdout app's runs before the shop's: a change is judged on the
    holdout first, and the shop runs can be stopped if it drops.

    The commit is read before the runs start: the runs use the code loaded now, and new
    commits made while a long benchmark runs must not relabel it.
    """
    commit = git_commit()
    with sessions() as session:
        workspace = benchmark_workspace(session)
        ensure_demo_sign_in(session, workspace, settings)
        run_ids: dict[str, list[str]] = {}

        def queue_shop() -> None:
            run_ids["buggy"] = queue_runs(session, workspace.id, [settings.demo_url] * runs, mode)
            run_ids["clean"] = queue_runs(session, workspace.id, [settings.clean_demo_url], mode)

        def queue_holdout() -> None:
            if holdout_runs > 0:
                run_ids["holdout_buggy"] = queue_runs(
                    session, workspace.id, [settings.demo2_url] * holdout_runs, mode
                )
                run_ids["holdout_clean"] = queue_runs(
                    session, workspace.id, [settings.clean_demo2_url], mode
                )

        for queue in (queue_holdout, queue_shop) if holdout_first else (queue_shop, queue_holdout):
            queue()
    every_run = [run_id for ids in run_ids.values() for run_id in ids]
    log.info("benchmark: %d runs queued (%s)", len(every_run), mode)
    wait_for(sessions, every_run, lambda: process_next(sessions, llm, execute, only=every_run))
    score_runs(sessions, judge, run_ids, commit)


# The demo shop's own test account, shown on its login page (apps/demo/src/store.tsx): not a secret.
DEMO_ACCOUNT = ("demo@example.com", "password123")


def ensure_demo_sign_in(session: Session, workspace, settings: Settings) -> None:
    """Run 4 (owner's question 3, decided without owner, option a): the shop benchmark runs signed
    in with a saved sign-in setup, as a customer's app behind a login would; logout is then denied,
    so planted bug 11 can't be triggered (reported separately). The holdout app has no login."""
    from urllib.parse import urlsplit

    from worker.db.models import LoginSetup
    from worker.secret_box import encrypt_secret, server_key

    raw_key = settings.model_keys_secret.get_secret_value()
    if not raw_key:
        log.warning("MODEL_KEYS_SECRET isn't set: the shop benchmark runs without a saved sign-in")
        return
    key = server_key(raw_key)
    for url in (settings.demo_url, settings.clean_demo_url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        exists = (
            session.query(LoginSetup).filter_by(workspace_id=workspace.id, origin=origin).first()
        )
        if exists:
            continue
        username, password = DEMO_ACCOUNT
        session.add(
            LoginSetup(
                workspace_id=workspace.id,
                origin=origin,
                kind="form",
                login_url=f"{origin}/login",
                username=username,
                password_ciphertext=encrypt_secret(password, str(workspace.id), key),
            )
        )
    session.commit()


def rescore_latest(sessions: sessionmaker[Session], judge: LLMClient) -> None:
    """Re-match the reports of the latest benchmark's runs (after a matching fix), save anew.

    The new row keeps the commit the runs were made on; the commit the rescore ran on is
    recorded separately, so a rescore never looks like a fresh benchmark of newer code.
    """
    with sessions() as session:
        latest = session.query(BenchmarkResult).order_by(BenchmarkResult.created_at.desc()).first()
        if latest is None:
            log.error("no benchmark result to rescore; run `uv run worker bench` first")
            return
        runs, original_commit = latest.details["runs"], latest.git_commit
    log.info("rescoring the runs of commit %s", original_commit)
    score_runs(sessions, judge, runs, original_commit, rescore_commit=git_commit())


def score_runs(
    sessions: sessionmaker[Session],
    judge: LLMClient,
    run_ids: dict[str, list[str]],
    commit: str,
    rescore_commit: str | None = None,
) -> None:
    """Match every reported bug to its app's bugs.json, compute the scores, print and save."""
    with sessions() as session:
        scores = _score_set(
            session, judge, run_ids["buggy"], run_ids["clean"], load_planted(), commit
        )
        if run_ids.get("holdout_buggy"):
            scores.holdout = _score_set(
                session,
                judge,
                run_ids["holdout_buggy"],
                run_ids.get("holdout_clean", []),
                load_planted(HOLDOUT_BUGS_JSON),
                commit,
            )
        scores.rescore_commit = rescore_commit
        save_scores(session, scores, run_ids)
    print_scores(scores)


def _score_set(session, judge, buggy_ids, clean_ids, planted, commit) -> BenchmarkScores:
    finished = [run for run_id in buggy_ids + clean_ids if (run := session.get(Run, run_id))]
    buggy = {
        run_id: [staged_match(judge, run_id, bug, planted) for bug in all_reports(session, run_id)]
        for run_id in buggy_ids
    }
    clean = {run_id: len(report_bugs(session, run_id)) for run_id in clean_ids}
    clean_before = {
        run_id: sum(1 for bug in all_reports(session, run_id) if bug.duplicate_of_id is None)
        for run_id in clean_ids
    }
    durations = [
        (run.finished_at - run.started_at).total_seconds()
        for run in finished
        if run.started_at and run.finished_at
    ]
    first = finished[0] if finished else None
    return score(
        buggy,
        clean,
        planted,
        costs=[run.cost_usd for run in finished],
        durations=durations,
        provider=(first.provider if first else None) or judge.provider,
        model=(first.model if first else None) or judge.agent_model,
        git_commit=commit,
        judge=judge_name(judge),
        clean_before=clean_before,
        reviewer=reviewer_of(finished),
    )


if __name__ == "__main__":
    main()
