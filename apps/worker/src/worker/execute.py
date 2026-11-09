"""What the worker does with a claimed run, writing progress to the database as it goes.

Every visited page becomes a step (so the live run page can show it immediately), every
finding becomes a bug, and tokens and cost are added to the run as they're spent.
"""

import itertools
from collections import Counter

from playwright.sync_api import Browser
from sqlalchemy.orm import Session

from worker.config import Settings
from worker.db.models import Bug, Run, RunMode, Step
from worker.llm import LLMClient, Usage
from worker.report import BugReport, PageResult
from worker.review import review_screenshots
from worker.runner import ExecuteFn
from worker.scan import passive_scan
from worker.storage import Storage

MAX_EVENTS_PER_STEP = 20


def make_execute(settings: Settings, storage: Storage, browser: Browser | None = None) -> ExecuteFn:
    """`browser`: reuse an already-running browser (tests); normally each run launches one."""

    def execute(session: Session, run: Run, llm: LLMClient) -> None:
        if run.mode == RunMode.INTERACTIVE:
            raise NotImplementedError("interactive mode is not available yet")
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
    run.summary = summarize(report.pages, bugs)
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
