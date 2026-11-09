"""What the worker does with a claimed run, writing progress to the database as it goes.

Every visited page becomes a step (so the live run page can show it immediately), every
finding becomes a bug, and tokens and cost are added to the run as they're spent.
"""

import itertools
import time
from collections import Counter

from playwright.sync_api import Browser
from sqlalchemy.orm import Session

from worker.agent.loop import AgentConfig, AgentRun, StepRecord
from worker.agent.policy import Budget
from worker.config import Settings
from worker.db.models import Bug, Run, RunMode, Step
from worker.findings import findings_from_pages
from worker.llm import LLMClient, Usage
from worker.report import BugReport, PageResult
from worker.review import review_screenshots
from worker.runner import ExecuteFn
from worker.safety.network import BlockedError
from worker.scan import guarded_context, is_demo_target, passive_scan
from worker.storage import Storage
from worker.verify import ReplayStep, find_duplicates, verify_bug

MAX_EVENTS_PER_STEP = 20


def make_execute(settings: Settings, storage: Storage, browser: Browser | None = None) -> ExecuteFn:
    """`browser`: reuse an already-running browser (tests); normally each run launches one."""

    def execute(session: Session, run: Run, llm: LLMClient) -> None:
        if run.mode == RunMode.INTERACTIVE:
            run_interactive(session, run, llm, settings, storage, browser)
        else:
            run_passive(session, run, llm, settings, storage, browser)

    return execute


def run_passive(
    session: Session,
    run: Run,
    llm: LLMClient,
    settings: Settings,
    storage: Storage,
    browser: Browser | None = None,
) -> None:
    step_numbers = itertools.count(run.step_count)

    def on_page(page: PageResult) -> None:
        session.add(
            Step(
                run_id=run.id,
                index=next(step_numbers),
                action="visit",
                args={"url": page.url, "status": page.status},
                url=page.url,
                screenshot=page.screenshot,
                events=page_events(page),
                blocked=bool(page.blocked_requests),
                block_reason=", ".join(page.blocked_requests[:3]) or None,
            )
        )
        run.pages_visited += 1
        run.step_count += 1
        session.commit()

    def should_stop() -> bool:
        session.refresh(run, ["stop_requested"])
        return run.stop_requested

    report = passive_scan(
        run.target_url, settings, storage, str(run.id), on_page, should_stop, browser
    )
    bugs = list(report.bugs)

    if settings.review_pages > 0 and not run.stop_requested:
        budget = max(settings.max_run_cost_usd - run.cost_usd, 0)
        review = review_screenshots(report.pages, llm, storage, settings.review_pages, budget)
        for usage in review.usages:
            index = next(step_numbers)
            session.add(
                Step(run_id=run.id, index=index, action="review_screenshot", **usage_fields(usage))
            )
            add_usage(run, usage)
            run.step_count += 1
        bugs += review.bugs

    for bug in bugs:
        session.add(Bug(run_id=run.id, **bug.model_dump()))
    session.commit()
    verification = verify_and_dedupe(session, run, llm, settings, browser)
    session.refresh(run)
    all_bugs = [BugReport.model_validate(b, from_attributes=True) for b in run.bugs]
    run.summary = {**summarize(report.pages, all_bugs), "verification": verification}
    session.commit()


def page_events(page: PageResult) -> list[dict]:
    """A compact list of what went wrong on the page, for the live timeline."""
    events = [{"type": e.kind, "text": e.text[:300]} for e in page.console_errors]
    events += [
        {"type": "network", "text": f"{r.method} {r.url} → {r.status or r.failure}"}
        for r in page.failed_requests
    ]
    events += [{"type": "a11y", "text": f"{v.rule_id}: {v.help}"} for v in page.a11y_violations]
    events += [{"type": "blocked", "text": url} for url in page.blocked_requests]
    return events[:MAX_EVENTS_PER_STEP]


def usage_fields(usage: Usage) -> dict:
    return {
        "input_tokens": usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": usage.cost_usd,
    }


def add_usage(run: Run, usage: Usage) -> None:
    fields = usage_fields(usage)
    run.input_tokens += fields["input_tokens"]
    run.output_tokens += fields["output_tokens"]
    run.cost_usd += fields["cost_usd"]


def summarize(pages: list[PageResult], bugs: list[BugReport]) -> dict:
    by_severity = Counter(b.severity for b in bugs if b.status != "dismissed")
    return {
        "pages": len(pages),
        "bugs": sum(by_severity.values()),
        "by_severity": {s: by_severity.get(s, 0) for s in ("critical", "high", "medium", "low")},
        "blocked_requests": sum(len(p.blocked_requests) for p in pages),
    }


def interactive_allowed(settings: Settings, target_url: str, verified: bool = False) -> bool:
    """Interactive mode (typing, submitting) only on our demo shops or a verified domain."""
    return verified or is_demo_target(settings, target_url)


def run_interactive(
    session: Session,
    run: Run,
    llm: LLMClient,
    settings: Settings,
    storage: Storage,
    browser: Browser | None = None,
    verified: bool = False,
) -> None:
    """Deterministic scan first (free), then the agent loop. Everything is saved as it happens."""
    if not interactive_allowed(settings, run.target_url, verified):
        raise BlockedError("interactive mode is only allowed on the demo shop and verified domains")
    started = time.monotonic()

    # 1. The free part: crawl and run the deterministic checks (no screenshot review; the agent
    #    looks at screenshots itself).
    step_numbers = itertools.count(run.step_count)
    report = passive_scan(
        run.target_url,
        settings,
        storage,
        str(run.id),
        on_page=lambda page: _save_visit(session, run, page, next(step_numbers)),
        should_stop=lambda: _stop_requested(session, run),
        browser=browser,
    )
    known_titles = {bug.title for bug in report.bugs}
    for bug in report.bugs:
        session.add(Bug(run_id=run.id, **bug.model_dump()))
    session.commit()
    if run.stop_requested:
        run.summary = summarize(report.pages, report.bugs)
        return

    # 2. The agent loop, with what's left of the budgets.
    budget = Budget(
        max_steps=settings.max_steps,
        max_seconds=max(settings.max_run_seconds - (time.monotonic() - started), 0),
        max_cost_usd=max(settings.max_run_cost_usd - run.cost_usd, 0),
        max_repeats=settings.max_repeated_actions,
    )
    first_agent_step = run.step_count
    agent_bugs: list[BugReport] = []

    def on_step(step: StepRecord) -> None:
        args = {k: v for k, v in step.args.items() if k != "reasoning"}
        session.add(
            Step(
                run_id=run.id,
                index=first_agent_step + step.index - 1,
                action=step.action,
                args={**args, "result": step.result, "element": step.element},
                reasoning=step.reasoning,
                url=step.url,
                screenshot=step.screenshot,
                events=[{"type": "event", "text": e[:300]} for e in step.events][
                    :MAX_EVENTS_PER_STEP
                ],
                blocked=step.blocked,
                block_reason=step.block_reason,
                **usage_fields(step.usage),
            )
        )
        add_usage(run, step.usage)
        run.step_count += 1
        session.commit()

    def on_bug(bug: BugReport) -> None:
        # Step numbers the model used are 1-based within the agent loop; store run step indexes.
        bug.step_indexes = [first_agent_step + i - 1 for i in bug.step_indexes]
        reported_at = first_agent_step + bug.evidence.get("reported_at", 1) - 1
        bug.evidence = {**bug.evidence, "reported_at": reported_at, "replay_from": first_agent_step}
        agent_bugs.append(bug)
        session.add(Bug(run_id=run.id, **bug.model_dump()))
        session.commit()

    counter = itertools.count(1)

    def save(png: bytes, name: str) -> str:
        return storage.save(f"{run.id}/agent-{next(counter):03d}-{name}.png", png)

    with guarded_context(settings, run.target_url, browser) as (context, guard):
        config = AgentConfig(
            target_url=run.target_url,
            mode=run.mode,
            budget=budget,
            focus=run.focus,
            is_demo_target=is_demo_target(settings, run.target_url),
        )
        agent = AgentRun(
            context.new_page(),
            llm,
            guard,
            config,
            save_screenshot=save,
            on_step=on_step,
            on_bug=on_bug,
            should_stop=lambda: _stop_requested(session, run),
        )
        result = agent.run()

    # 3. Errors seen while the agent clicked around are deterministic findings too.
    extra = [
        b for b in findings_from_pages(list(result.pages.values())) if b.title not in known_titles
    ]
    for bug in extra:
        session.add(Bug(run_id=run.id, **bug.model_dump()))
    session.commit()
    verification = verify_and_dedupe(session, run, llm, settings, browser)
    all_bugs = [BugReport.model_validate(b, from_attributes=True) for b in run.bugs]
    run.summary = {
        **summarize(report.pages, all_bugs),
        "stop_reason": result.stop_reason,
        "agent_summary": result.summary,
        "verification": verification,
    }
    session.commit()


def _save_visit(session: Session, run: Run, page: PageResult, index: int) -> None:
    session.add(
        Step(
            run_id=run.id,
            index=index,
            action="visit",
            args={"url": page.url, "status": page.status},
            url=page.url,
            screenshot=page.screenshot,
            events=page_events(page),
            blocked=bool(page.blocked_requests),
            block_reason=", ".join(page.blocked_requests[:3]) or None,
        )
    )
    run.pages_visited += 1
    run.step_count += 1
    session.commit()


def _stop_requested(session: Session, run: Run) -> bool:
    session.refresh(run, ["stop_requested"])
    return run.stop_requested


def verify_and_dedupe(
    session: Session,
    run: Run,
    llm: LLMClient,
    settings: Settings,
    browser: Browser | None = None,
) -> dict:
    """Replay every candidate bug in a fresh browser, then merge duplicates (brief 5.3).

    Returns counts for the run summary: candidates, confirmed, dismissed by replay, duplicates.
    """
    bugs = session.query(Bug).filter_by(run_id=run.id).order_by(Bug.created_at).all()
    steps = {s.index: s for s in session.query(Step).filter_by(run_id=run.id)}
    candidates = [b for b in bugs if b.status == "candidate"]
    stats = {"candidates": len(candidates), "confirmed": 0, "dismissed": 0, "duplicates": 0}

    if candidates and not run.stop_requested:
        with guarded_context(settings, run.target_url, browser) as (context, _guard):
            for bug in candidates:
                if run.cost_usd >= settings.max_run_cost_usd:
                    break  # out of budget: leave the rest as unverified candidates
                replay_steps = [
                    ReplayStep(s.action, s.args or {}, (s.args or {}).get("element"))
                    for i in replay_indexes(bug)
                    if (s := steps.get(i)) is not None and not s.blocked
                ]
                start_url = run.target_url if replay_steps else bug.page_url
                verdict = verify_bug(
                    context, llm, start_url, replay_steps, bug.title, bug.expected, bug.actual
                )
                bug.status = "confirmed" if verdict.reproduced else "dismissed"
                bug.dismiss_reason = None if verdict.reproduced else f"replay: {verdict.reason}"
                bug.evidence = {**(bug.evidence or {}), "replay": verdict.reason}
                stats["confirmed" if verdict.reproduced else "dismissed"] += 1
                _log_model_step(session, run, "verify_bug", {"bug": bug.title}, verdict.usage)

    live = [b for b in bugs if b.status != "dismissed"]
    dedup = find_duplicates(
        llm, [{"title": b.title, "page_url": b.page_url, "actual": b.actual} for b in live]
    )
    for duplicate_index, original_index in dedup.pairs:
        duplicate, original = live[duplicate_index], live[original_index]
        if duplicate.source == "deterministic" and original.source == "agent":
            duplicate, original = original, duplicate  # keep the one with hard evidence
        if duplicate.status == "dismissed" or original.status == "dismissed":
            continue
        duplicate.status = "dismissed"
        duplicate.dismiss_reason = f"duplicate of: {original.title}"
        duplicate.duplicate_of_id = original.id
        stats["duplicates"] += 1
    if dedup.usage:
        _log_model_step(session, run, "dedupe", {"bugs": len(live)}, dedup.usage)
    session.commit()
    return stats


def replay_indexes(bug: Bug) -> list[int]:
    """Which steps to repeat: every agent action up to where the bug was reported.

    The model's own step list is often incomplete (it forgets the "add to cart" that made the
    cart non-empty), so replaying everything up to the report reaches the same state.
    """
    evidence = bug.evidence or {}
    if "reported_at" in evidence and "replay_from" in evidence:
        return list(range(evidence["replay_from"], evidence["reported_at"]))
    return list(bug.step_indexes or [])


def _log_model_step(
    session: Session, run: Run, action: str, args: dict, usage: Usage | None
) -> None:
    """A step that only called the model (verification, dedup): recorded for cost tracking."""
    session.add(
        Step(
            run_id=run.id,
            index=run.step_count,
            action=action,
            args=args,
            **(usage_fields(usage) if usage else {}),
        )
    )
    if usage:
        add_usage(run, usage)
    run.step_count += 1
    session.commit()
