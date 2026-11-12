"""What the worker does with a claimed run, writing progress to the database as it goes.

Every visited page becomes a step (so the live run page can show it immediately), every
finding becomes a bug, and tokens and cost are added to the run as they're spent.
"""

import itertools
import time
from collections import Counter
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Browser, BrowserContext
from sqlalchemy.orm import Session

from worker.agent.loop import AgentConfig, AgentRun, StepRecord
from worker.agent.policy import Budget
from worker.config import Settings
from worker.db.models import Bug, Domain, Run, RunMode, Step
from worker.findings import findings_from_pages
from worker.llm import LLMClient, Usage
from worker.login import LoginConfig, login_for_run, sign_in
from worker.report import BugReport, PageResult
from worker.review import review_screenshots
from worker.runner import ExecuteFn
from worker.safety.network import BlockedError
from worker.scan import guarded_browser, guarded_context, is_demo_target, passive_scan
from worker.storage import Storage
from worker.triage import apply_triage
from worker.urls import normalize
from worker.verify import ReplayStep, Verdict, find_duplicates, verify_bug

MAX_EVENTS_PER_STEP = 20


def make_execute(settings: Settings, storage: Storage, browser: Browser | None = None) -> ExecuteFn:
    """`browser`: reuse an already-running browser (tests); normally each run launches one."""

    def execute(session: Session, run: Run, llm: LLMClient) -> None:
        if run.mode == RunMode.INTERACTIVE:
            verified = is_verified_domain(session, run.workspace_id, run.target_url)
            run_interactive(session, run, llm, settings, storage, browser, verified)
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
    login = login_for_run(session, settings, run)

    report = passive_scan(
        run.target_url,
        settings,
        storage,
        str(run.id),
        on_page=lambda page: _save_visit(session, run, page, next(step_numbers)),
        should_stop=lambda: _stop_requested(session, run),
        browser=browser,
        login=login,
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
    verification = verify_and_dedupe(session, run, llm, settings, browser, login)
    session.refresh(run)
    all_bugs = [BugReport.model_validate(b, from_attributes=True) for b in run.bugs]
    run.summary = {
        **summarize(report.pages, all_bugs),
        "verification": verification,
        "suppressed": apply_triage(session, run),  # triaged as false positives earlier
    }
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


def is_verified_domain(session: Session, workspace_id, url: str) -> bool:
    """Has this workspace proven it owns the target's host (DNS TXT or well-known file)?"""
    host = (urlsplit(url).hostname or "").lower()
    domain = (
        session.query(Domain)
        .filter(Domain.workspace_id == workspace_id, Domain.hostname == host)
        .filter(Domain.verified_at.isnot(None))
        .first()
    )
    return domain is not None


def interactive_allowed(settings: Settings, target_url: str, verified: bool = False) -> bool:
    """Interactive mode (typing, submitting) only on our demo shops or a verified domain."""
    return verified or is_demo_target(settings, target_url)


def run_limits(settings: Settings, run: Run) -> tuple[int, int]:
    """Steps and seconds for this run: the worker's limits, or lower ones the run asked for
    (set through the API by a CI pipeline, run 4). A run can never raise them."""
    steps = min(settings.max_steps, run.max_steps or settings.max_steps)
    seconds = min(settings.max_run_seconds, run.max_seconds or settings.max_run_seconds)
    return steps, seconds


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
    login = login_for_run(session, settings, run)

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
        login=login,
    )
    known_titles = {bug.title for bug in report.bugs}
    for bug in report.bugs:
        session.add(Bug(run_id=run.id, **bug.model_dump()))
    session.commit()
    if run.stop_requested:
        run.summary = summarize(report.pages, report.bugs)
        return

    # 2. The agent loop, with what's left of the budgets.
    max_steps, max_seconds = run_limits(settings, run)
    budget = Budget(
        max_steps=max_steps,
        max_seconds=max(max_seconds - (time.monotonic() - started), 0),
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
                args={
                    **args,
                    "result": step.result,
                    "element": step.element,
                    "box": step.box,
                    "viewport": step.viewport,
                },
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

    with guarded_context(settings, run.target_url, browser, login) as (context, guard):
        config = AgentConfig(
            target_url=run.target_url,
            mode=run.mode,
            budget=budget,
            focus=run.focus,
            is_demo_target=is_demo_target(settings, run.target_url),
            login=login,
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
            relogin=(lambda: sign_in(context, login)) if login else None,
        )
        result = agent.run()

    # 3. Errors seen while the agent clicked around are deterministic findings too.
    extra = [
        b for b in findings_from_pages(list(result.pages.values())) if b.title not in known_titles
    ]
    for bug in extra:
        session.add(Bug(run_id=run.id, **bug.model_dump()))
    session.commit()
    verification = verify_and_dedupe(session, run, llm, settings, browser, login)
    all_bugs = [BugReport.model_validate(b, from_attributes=True) for b in run.bugs]
    run.summary = {
        **summarize(report.pages, all_bugs),
        "stop_reason": result.stop_reason,
        "agent_summary": result.summary,
        "verification": verification,
        "suppressed": apply_triage(session, run),  # triaged as false positives earlier
        "expectation_checks": {"dismissed": result.dismissed, "ignored": result.ignored},
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
    login: LoginConfig | None = None,
) -> dict:
    """Merge duplicates, then replay every remaining candidate in a fresh browser (brief 5.3).

    Dedup comes first: an agent report that restates a deterministic finding (a failed request
    it noticed) is merged into that finding, which has hard evidence. Replaying it instead
    would ask the model to see a server error on screen, fail, and dismiss a real bug.
    Deterministic findings are never replayed or dismissed by replay.

    Returns counts for the run summary: candidates, confirmed, dismissed by replay, duplicates.
    """
    bugs = session.query(Bug).filter_by(run_id=run.id).order_by(Bug.created_at).all()
    steps = {s.index: s for s in session.query(Step).filter_by(run_id=run.id)}
    stats = {
        "candidates": sum(1 for b in bugs if b.status == "candidate"),
        "confirmed": 0,
        "dismissed": 0,
        "duplicates": _dedupe(session, run, llm, bugs),
    }
    candidates = [b for b in bugs if b.status == "candidate" and b.source != "deterministic"]

    if candidates and not run.stop_requested:
        with guarded_browser(settings, run.target_url, browser, login) as (new_context, _guard):
            for bug in candidates:
                if run.cost_usd >= settings.max_run_cost_usd:
                    break  # out of budget: leave the rest as unverified candidates
                verdict, start_url = _replay_bug(
                    session, run, llm, settings, new_context, bug, steps, login
                )
                if verdict.reproduced:
                    bug.status, bug.dismiss_reason = "confirmed", None
                elif verdict.replayed:
                    bug.status, bug.dismiss_reason = "dismissed", f"replay: {verdict.reason}"
                else:
                    bug.status = "dismissed"
                    bug.dismiss_reason = f"could not replay: {verdict.reason}"
                stale = ("replay_failure", "replay_diff")
                evidence = {k: v for k, v in (bug.evidence or {}).items() if k not in stale}
                bug.evidence = {**evidence, "replay": verdict.reason, "replay_start": start_url}
                if verdict.failure:
                    bug.evidence["replay_failure"] = verdict.failure
                if verdict.diff:
                    bug.evidence["replay_diff"] = verdict.diff
                stats["confirmed" if verdict.reproduced else "dismissed"] += 1
    session.commit()
    return stats


def _dedupe(session: Session, run: Run, llm: LLMClient, bugs: list[Bug]) -> int:
    """Ask the cheap model for duplicates among the bugs still standing; returns how many."""
    live = [b for b in bugs if b.status != "dismissed"]
    dedup = find_duplicates(
        llm, [{"title": b.title, "page_url": b.page_url, "actual": b.actual} for b in live]
    )
    merged = 0
    for duplicate_index, original_index in dedup.pairs:
        duplicate, original = live[duplicate_index], live[original_index]
        if duplicate.source == "deterministic" and original.source != "deterministic":
            duplicate, original = original, duplicate  # keep the one with hard evidence
        if duplicate.source == "deterministic":
            continue  # two hard findings: both stay, they were already merged by rule
        if duplicate.status == "dismissed" or original.status == "dismissed":
            continue
        duplicate.status = "dismissed"
        duplicate.dismiss_reason = f"duplicate of: {original.title}"
        duplicate.duplicate_of_id = original.id
        merged += 1
    if dedup.usage:
        _log_model_step(session, run, "dedupe", {"bugs": len(live)}, dedup.usage)
    return merged


def _replay_bug(
    session: Session,
    run: Run,
    llm: LLMClient,
    settings: Settings,
    new_context: Callable[[], BrowserContext],
    bug: Bug,
    steps: dict[int, Step],
    login: LoginConfig | None = None,
) -> tuple[Verdict, str]:
    """Try each replay plan until one reproduces the bug; returns the last verdict and start.

    Every plan runs in a new browser context: cookies, localStorage and sessions left by the
    replay before it (a cart, a sign-in) would otherwise change what this one sees. The steps
    themselves rebuild the state the agent had (they include its sign-in and its cart).
    """
    verdict, start_url = Verdict(False, "nothing to replay", replayed=False), run.target_url
    for start_url, replay_steps in replay_plans(bug, steps, run.target_url):
        context = new_context()
        try:
            verdict = verify_bug(
                context,
                llm,
                start_url,
                replay_steps,
                bug.title,
                bug.expected,
                bug.actual,
                viewport=(bug.evidence or {}).get("viewport", "desktop"),
                scrub=login.scrub if login else (lambda text: text),
            )
        finally:
            context.close()
        _log_model_step(session, run, "verify_bug", {"bug": bug.title}, verdict.usage)
        if verdict.reproduced or run.cost_usd >= settings.max_run_cost_usd:
            break
    return verdict, start_url


def replay_plans(bug, steps: dict, target_url: str) -> list[tuple[str, list[ReplayStep]]]:
    """Where to start replay and which steps to repeat, shortest first.

    An agent report replays every agent action up to the report (the model's own step list is
    often incomplete). Shorter plans come first: from the last navigate (a full page load), and
    from the agent's last return to the start page (a new flow usually starts there). Earlier
    steps matter less, can have side effects (a second order) and can fail to replay, which
    must not dismiss a bug found later. If no short plan reproduces it, the full one runs. A
    screenshot finding (no recorded steps) is checked on its own page.
    """
    indexes = replay_indexes(bug)
    if not indexes:
        return [(bug.page_url, [])]
    kept = [(i, steps[i]) for i in indexes if i in steps and _took_effect(steps[i])]
    full = [_replay_step_of(step) for _, step in kept]
    # Shorter replays first, latest start first: what happened before a page load, or before
    # the agent's last return to the start page, matters less, and one of those earlier steps
    # failing to replay (or repeating a side effect) must not decide the verdict.
    short: list[tuple[int, tuple[str, list[ReplayStep]]]] = []
    navigations = [n for n, (_, step) in enumerate(kept) if step.action == "navigate"]
    if navigations:
        n = navigations[-1]
        page = kept[n][1]
        start_url = urljoin(page.url or target_url, str((page.args or {}).get("url", "")))
        short.append((n + 1, (start_url, _viewport_before(kept, n) + full[n + 1 :])))
    on_home = [_on_start_page(step, target_url) for _, step in kept]
    arrivals = [n for n in range(1, len(kept)) if on_home[n] and not on_home[n - 1]]
    if arrivals:
        n = arrivals[-1]
        short.append((n, (target_url, _viewport_before(kept, n) + full[n:])))
    plans = [plan for _, plan in sorted(short, key=lambda item: -item[0])]
    plans.append((target_url, full))
    unique: list[tuple[str, list[ReplayStep]]] = []
    for plan in plans:  # the same replay twice would only cost a second model call
        if plan not in unique:
            unique.append(plan)
    return unique


def _took_effect(step) -> bool:
    """Did this step do something in the agent's run? Blocked steps and steps that errored
    (an element that wasn't there, text a number field refused) left the page as it was, so
    they aren't part of how the bug was reached, and repeating them would only fail replay."""
    result = str((step.args or {}).get("result") or "")
    return not step.blocked and not result.startswith("error:")


def _viewport_before(kept: list, n: int) -> list[ReplayStep]:
    """The last viewport change before step n: it outlives a page load, so it is set again."""
    return [_replay_step_of(s) for _, s in kept[:n] if s.action == "set_viewport"][-1:]


def _on_start_page(step, target_url: str) -> bool:
    """Was this step taken on the run's start page (the same URL, ignoring #fragments)?"""
    return normalize(step.url or "") == normalize(target_url)


def _replay_step_of(step) -> ReplayStep:
    args = step.args or {}
    return ReplayStep(step.action, args, args.get("element"), step.url)


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
