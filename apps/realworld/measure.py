"""Measure the agent on one real-world bug (run 8, N4).

    cd apps/worker && env -u ANTHROPIC_API_KEY LLM_PROVIDER=claude-cli \\
        CLAUDE_CLI_MODEL=claude-haiku-5-5 CLAUDE_CLI_CHEAP_MODEL=claude-haiku-5-5 DEV_MODE=true \\
        MAX_RUN_COST_USD=1 BENCH_MAX_COST_USD=2 JUDGE_PROVIDER=ollama JUDGE_MODEL=gemma4:12b \\
        uv run python ../realworld/measure.py IT-1 --runs 3

The app must already be running (realworld.py start <bug>). Queues `--runs` interactive runs in
the "realworld" workspace, each starting on the bug's feature page with no description of the
bug, processes them with the configured agent, then classifies each run:

- found: a report that survived verification and the judge (ollama/gemma4:12b, the benchmark's
  pinned judge) matched to the real bug;
- reached, not reported: the run did the bug's trigger (bugs.json "reach": an action of the right
  kind on the right page, mentioning the trigger) but no verified report matched;
- never reached: neither.

Every report is listed too, so reports that look like other real bugs can be reviewed by hand.
The result is appended to apps/realworld/results.jsonl with commit, model, provider, settings
and date. A claude-cli usage limit stops the runs at once (the worker latches it).
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from realworld import bug_and_app, url_of  # noqa: E402

from worker.benchmark import (  # noqa: E402
    PlantedBug,
    all_reports,
    check_pinned_models,
    git_commit,
    staged_match,
)
from worker.config import get_settings  # noqa: E402
from worker.db.models import Run, Step, Workspace  # noqa: E402
from worker.db.session import make_engine, make_session_factory  # noqa: E402
from worker.execute import make_execute  # noqa: E402
from worker.llm import make_client, make_judge  # noqa: E402
from worker.main import process_until_done, setup_logging  # noqa: E402
from worker.runner import process_next  # noqa: E402
from worker.storage import make_storage  # noqa: E402

SLUG = "realworld"
RESULTS = HERE / "results.jsonl"
BENCHMARK = "real-world v1"


def reached(steps: list[Step], rule: dict) -> bool:
    """Did any agent step do the bug's trigger? An action of the listed kinds, on a URL containing
    rule["path"], whose arguments, element or reasoning mention one of rule["any_text"]."""
    for step in steps:
        if step.action not in rule["actions"]:
            continue
        if rule["path"] and rule["path"] not in (step.url or ""):
            continue
        text = f"{json.dumps(step.args or {})} {step.reasoning or ''}".lower()
        if any(word in text for word in rule["any_text"]):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bug_id")
    parser.add_argument("--runs", type=int, default=3)
    # Run 9: deep mode runs on the same bugs, so the two engines can be compared.
    parser.add_argument("--engine", choices=["loop", "deep"], default="loop")
    args = parser.parse_args()
    bug, _ = bug_and_app(args.bug_id)
    if bug.get("dropped"):
        raise SystemExit(f"{args.bug_id} was dropped: {bug['dropped']}")
    app_url = url_of(bug)
    settings = get_settings()
    if not settings.dev_mode:
        raise SystemExit("measure.py: DEV_MODE=true is required (the app runs on localhost)")
    settings = settings.model_copy(update={"local_app_urls": app_url})
    setup_logging((settings.anthropic_api_key.get_secret_value(),))
    llm = make_client(settings)
    check_pinned_models([llm])
    judge = make_judge(settings, llm)
    commit = git_commit()
    sessions = make_session_factory(make_engine(settings, admin=True))
    execute = make_execute(settings, make_storage(settings))
    target = app_url + bug["start_path"]
    with sessions() as session:
        workspace = session.query(Workspace).filter_by(slug=SLUG).one_or_none()
        if workspace is None:
            workspace = Workspace(name="Real-world benchmark", slug=SLUG)
            session.add(workspace)
            session.commit()
        run_ids = []
        for _ in range(args.runs):
            run = Run(
                workspace_id=workspace.id, target_url=target, mode="interactive", engine=args.engine
            )
            session.add(run)
            session.commit()
            run_ids.append(str(run.id))
    stopped = process_until_done(
        sessions,
        run_ids,
        lambda: process_next(sessions, llm, execute, only=run_ids),
        settings.bench_max_cost_usd,
    )
    planted = [PlantedBug(1, bug["page"], bug["title"], bug["description"], "agent")]
    runs_out = []
    with sessions() as session:
        for run_id in run_ids:
            run = session.get(Run, run_id)
            steps = session.query(Step).filter_by(run_id=run_id).order_by(Step.index).all()
            reports = []
            found = False
            for report in all_reports(session, run_id):
                decision = staged_match(judge, run_id, report, planted)
                hit = decision.matched == 1 and decision.stage == "verified"
                found = found or hit
                reports.append(
                    {
                        "title": report.title,
                        "status": report.status,
                        "stage": decision.stage,
                        "matched": decision.matched,
                        "judge_reason": decision.reason[:200],
                    }
                )
            did_trigger = reached(steps, bug["reach"])
            outcome = "found" if found else "reached" if did_trigger else "never"
            seconds = (
                (run.finished_at - run.started_at).total_seconds()
                if run.started_at and run.finished_at
                else None
            )
            runs_out.append(
                {
                    "run": run_id,
                    "status": run.status,
                    "error": run.error,
                    "outcome": outcome,
                    "steps": run.step_count,
                    "seconds": seconds,
                    "estimated_cost_usd": round(run.estimated_cost_usd, 4),
                    "cost_usd": round(run.cost_usd, 4),
                    "paused_reason": run.paused_reason,
                    "reports": reports,
                }
            )
    result = {
        "benchmark": BENCHMARK,
        "bug": args.bug_id,
        "issue": bug["issue"],
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": commit,
        "engine": args.engine,
        # A deep run's model is deep mode's own (DEEP_MODEL); `llm` only judges its replays.
        "provider": llm.provider if args.engine == "loop" else f"deep/{settings.deep_auth}",
        "model": llm.agent_model if args.engine == "loop" else settings.deep_model,
        "judge": f"{judge.provider}/{judge.cheap_model}",
        "settings": {
            "max_steps": settings.max_steps if args.engine == "loop" else settings.deep_max_steps,
            "max_run_seconds": (
                settings.max_run_seconds if args.engine == "loop" else settings.deep_max_seconds
            ),
            "start": bug["start_path"],
        },
        "stopped": stopped,
        "runs": runs_out,
    }
    with RESULTS.open("a", encoding="utf-8") as out:
        out.write(json.dumps(result) + "\n")
    print(f"\n{args.bug_id}: {bug['title']}")
    for r in runs_out:
        print(f"  run {r['run'][:8]} {r['status']:<6} {r['outcome']:<8} {r['steps']} steps")
        for rep in r["reports"]:
            mark = "✓" if rep["matched"] == 1 and rep["stage"] == "verified" else " "
            print(f"     {mark} [{rep['stage']}] {rep['title'][:100]}")
    if stopped:
        print(f"STOPPED: {stopped}")


if __name__ == "__main__":
    main()
