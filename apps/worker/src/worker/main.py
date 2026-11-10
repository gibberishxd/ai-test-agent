"""Worker entry point.

uv run worker             poll the run queue forever (what `npm run dev` starts)
uv run worker --once      process at most one queued run, then exit
uv run worker scan URL    passive scan without the database; writes reports/<time>/report.json
uv run worker bench       benchmark: N runs on the buggy shop + 1 on the clean shop, scored
"""

import argparse
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from worker.benchmark import (
    benchmark_workspace,
    git_commit,
    judge_name,
    load_planted,
    match_report,
    print_scores,
    queue_runs,
    report_bugs,
    save_scores,
    score,
    wait_for,
)
from worker.config import REPO_ROOT, Settings, get_settings
from worker.db.models import BenchmarkResult, Run
from worker.db.session import make_engine, make_session_factory
from worker.execute import make_execute
from worker.llm import LLMClient, make_client, make_judge
from worker.queue import recover_stale_runs
from worker.report import write_report
from worker.runner import ExecuteFn, process_next
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
    bench = sub.add_parser("bench", help="score the agent against the demo shop's planted bugs")
    bench.add_argument("--runs", type=int, default=3, help="runs on the buggy shop (default 3)")
    bench.add_argument("--mode", choices=["interactive", "passive"], default="interactive")
    bench.add_argument(
        "--rescore", action="store_true", help="re-match the latest benchmark's runs, no new runs"
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

    llm = make_client(settings)
    sessions = make_session_factory(make_engine(settings))
    execute = make_execute(settings, LocalStorage(settings.data_path()))
    with sessions() as session:
        # A run can't legitimately take longer than its time budget plus a grace period.
        recovered = recover_stale_runs(session, settings.max_run_seconds + STALE_GRACE_S)
    if recovered:
        log.warning("marked %d stale run(s) as failed", recovered)
    log.info("ready. provider=%s model=%s", llm.provider, llm.agent_model)

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
        run_benchmark(settings, llm, judge, sessions, execute, args.runs, args.mode)
        return
    if args.once:
        if not process_next(sessions, llm, execute):
            log.info("queue is empty")
        return
    while True:
        if not process_next(sessions, llm, execute):
            time.sleep(POLL_INTERVAL_S)


def run_benchmark(
    settings: Settings,
    llm: LLMClient,
    judge: LLMClient,
    sessions: sessionmaker[Session],
    execute: ExecuteFn,
    runs: int,
    mode: str,
) -> None:
    """Queue the benchmark runs, process them with `llm`, then score them with `judge`."""
    with sessions() as session:
        workspace = benchmark_workspace(session)
        buggy_ids = queue_runs(session, workspace.id, [settings.demo_url] * runs, mode)
        clean_ids = queue_runs(session, workspace.id, [settings.clean_demo_url], mode)
    log.info("benchmark: %d buggy + %d clean %s runs queued", runs, len(clean_ids), mode)
    wait_for(sessions, buggy_ids + clean_ids, lambda: process_next(sessions, llm, execute))
    score_runs(sessions, judge, buggy_ids, clean_ids)


def rescore_latest(sessions: sessionmaker[Session], judge: LLMClient) -> None:
    """Re-match the reports of the latest benchmark's runs (after a matching fix), save anew."""
    with sessions() as session:
        latest = session.query(BenchmarkResult).order_by(BenchmarkResult.created_at.desc()).first()
        if latest is None:
            log.error("no benchmark result to rescore; run `uv run worker bench` first")
            return
        runs = latest.details["runs"]
    log.info("rescoring %d buggy + %d clean runs", len(runs["buggy"]), len(runs["clean"]))
    score_runs(sessions, judge, runs["buggy"], runs["clean"])


def score_runs(
    sessions: sessionmaker[Session], judge: LLMClient, buggy_ids: list[str], clean_ids: list[str]
) -> None:
    """Match every reported bug to bugs.json, compute the scores, print and save them."""
    planted = load_planted()
    with sessions() as session:
        finished = [session.get(Run, run_id) for run_id in buggy_ids + clean_ids]
        buggy = {
            run_id: [
                match_report(judge, run_id, bug, planted) for bug in report_bugs(session, run_id)
            ]
            for run_id in buggy_ids
        }
        clean = {run_id: len(report_bugs(session, run_id)) for run_id in clean_ids}
        durations = [
            (run.finished_at - run.started_at).total_seconds()
            for run in finished
            if run.started_at and run.finished_at
        ]
        scores = score(
            buggy,
            clean,
            planted,
            costs=[run.cost_usd for run in finished],
            durations=durations,
            provider=finished[0].provider or judge.provider,
            model=finished[0].model or judge.agent_model,
            git_commit=git_commit(),
            judge=judge_name(judge),
        )
        save_scores(session, scores, {"buggy": buggy_ids, "clean": clean_ids})
    print_scores(scores)


if __name__ == "__main__":
    main()
