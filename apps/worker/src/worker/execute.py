"""What the worker does with a claimed run, writing progress to the database as it goes.

Every visited page becomes a step (so the live run page can show it immediately), every
finding becomes a bug, and tokens and cost are added to the run as they're spent.
"""

import itertools
import logging
import time
from collections import Counter
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Browser, BrowserContext
from sqlalchemy import func
from sqlalchemy.orm import Session

from worker.agent.lists import lists_from_crawl
from worker.agent.loop import AgentConfig, AgentRun, StepRecord
from worker.agent.policy import Budget
from worker.agent.reviewer import review_candidate
from worker.config import Settings
from worker.db.models import Bug, Domain, Flow, FlowResult, Run, RunMode, Spec, Step
from worker.findings import findings_from_pages
from worker.flows import (
    MAX_FLOW_STEPS,
    FlowOutcome,
    checks_for_final_page,
    counted_replay,
    flow_task,
    parse_finish,
    recheck_reason,
    replay_flow,
    script_from_steps,
)
from worker.llm import LLMClient, Usage
from worker.login import LoginConfig, login_for_run, sign_in
from worker.report import BugReport, PageResult
from worker.review import review_screenshots
from worker.runner import ExecuteFn
from worker.safety.network import BlockedError
from worker.scan import guarded_browser, guarded_context, is_demo_target, passive_scan
from worker.spec_store import SpecRetriever, chunk_text, sync_target, target_for
from worker.specs import OllamaEmbedder
from worker.storage import Storage
from worker.triage import suppressed_count
from worker.urls import normalize
from worker.verify import ReplayStep, Verdict, find_duplicates, size_or_desktop, verify_bug

log = logging.getLogger(__name__)

MAX_EVENTS_PER_STEP = 20


def make_execute(
    settings: Settings,
    storage: Storage,
    browser: Browser | None = None,
    reviewer: LLMClient | None = None,
) -> ExecuteFn:
    """`browser`: reuse an already-running browser (tests); normally each run launches one.
    `reviewer`: the reviewer tier's client (run 5, K2), or None for the explorer alone."""

    def execute(session: Session, run: Run, llm: LLMClient) -> None:
        if run.mode == RunMode.INTERACTIVE:
            verified = is_verified_domain(session, run.workspace_id, run.target_url)
            run_interactive(session, run, llm, settings, storage, browser, verified, reviewer)
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
        viewport=size_or_desktop(run.viewport) if run.viewport else None,
    )
    bugs = list(report.bugs)

    if settings.review_pages > 0 and not run.stop_requested:
        budget = remaining_budget(settings, run)
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
        "suppressed": suppressed_count(session, run),  # triaged as false positives earlier
    }
    session.commit()


def page_events(page: PageResult) -> list[dict]:
    """A compact list of what went wrong on the page, for the live timeline."""
    events = [{"type": e.kind, "text": e.text[:300]} for e in page.console_errors]
    events += [{"type": "warning", "text": w.text[:300]} for w in page.console_warnings]
    events += [
        {"type": "network", "text": f"{r.method} {r.url} → {r.status or r.failure}"}
        for r in page.failed_requests
    ]
    events += [{"type": "a11y", "text": f"{v.rule_id}: {v.help}"} for v in page.a11y_violations]
    events += [{"type": "blocked", "text": url} for url in page.blocked_requests]
    return events[:MAX_EVENTS_PER_STEP]


def usage_fields(usage: Usage) -> dict:
    """A model call as step columns: `input_tokens` counts every input token (cached or not),
    `cache_*` the cached share; `estimated_cost_usd` is the API-equivalent cost (run 6)."""
    return {
        "model": usage.model or None,
        "input_tokens": usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "cost_usd": usage.cost_usd,
        "estimated_cost_usd": usage.api_cost_usd,
    }


def add_usage(run: Run, usage: Usage) -> None:
    fields = usage_fields(usage)
    run.input_tokens += fields["input_tokens"]
    run.output_tokens += fields["output_tokens"]
    run.cache_read_tokens += fields["cache_read_tokens"]
    run.cache_write_tokens += fields["cache_write_tokens"]
    run.cost_usd += fields["cost_usd"]
    run.estimated_cost_usd += fields["estimated_cost_usd"]


def over_budget(settings: Settings, run: Run, pending: list[Usage] = ()) -> bool:
    """Has the run (plus `pending` calls not stored yet) spent MAX_RUN_COST_USD? Counted in
    API-equivalent cost, so a run on a flat-rate plan (claude-cli) still stops (run 6)."""
    spent = run.estimated_cost_usd + sum(u.api_cost_usd for u in pending)
    return spent >= settings.max_run_cost_usd


def remaining_budget(settings: Settings, run: Run) -> float:
    return max(settings.max_run_cost_usd - run.estimated_cost_usd, 0)


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


def _save_agent_step(session: Session, run: Run, first_agent_step: int, step: StepRecord) -> None:
    """Store an agent step as the run's step `first_agent_step + step.index - 1`."""
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
            events=[{"type": "event", "text": e[:300]} for e in step.events][:MAX_EVENTS_PER_STEP],
            blocked=step.blocked,
            block_reason=step.block_reason,
            **usage_fields(step.usage),
        )
    )
    add_usage(run, step.usage)
    run.step_count += 1
    session.commit()


def flows_for(session: Session, run: Run) -> list[Flow]:
    """The run's target's critical flows, in the team's order (none without a target)."""
    target = target_for(session, run.workspace_id, run.target_url)
    if target is None:
        return []
    return (
        session.query(Flow)
        .filter_by(target_id=target.id)
        .order_by(Flow.position, Flow.created_at)
        .all()
    )


def check_flow(flow: Flow, context, budget: Budget, run: Run, make_agent) -> FlowOutcome:
    """One journey (run 7, M4): replay its script without a model; only if there is none, or a
    step can't be repeated, give it to the agent (`make_agent(budget, first_step)`) as a short
    episode. A known failure (a failing script) that still fails is found again for free."""
    if budget.max_steps <= 0 or budget.max_seconds <= 0 or budget.max_cost_usd <= 0:
        return FlowOutcome("skipped", "no budget left for this journey")
    broke = recheck = None
    if flow.script:
        result, detail = replay_flow(context, flow.script)
        failing = bool(flow.script.get("failing"))
        if result == "ok":
            fixed = " (it failed before: fixed)" if failing else ""
            return FlowOutcome("replayed", detail + fixed, replayed=True)
        if result == "checks_failed" and failing:
            # Run 8, N2: the same failure is taken from replay at most twice in a row.
            recheck = recheck_reason(flow.script, detail)
            if recheck is None:
                return FlowOutcome(
                    "failed",
                    f"still failing: {detail}",
                    replayed=True,
                    last_url=flow.script["start_url"],
                    script=counted_replay(flow.script, detail),
                )
        else:
            broke = detail
    first, cost_before = run.step_count, run.estimated_cost_usd
    agent = make_agent(budget, first)
    episode = agent.run()
    passed, checks, detail = parse_finish(episode.summary)
    if passed is not None:  # checks must agree with the page the journey ended on
        checks = checks_for_final_page(passed, checks, _page_text(agent.page))
    common = {
        "model_calls": len(episode.steps),
        "estimated_cost_usd": max(run.estimated_cost_usd - cost_before, 0.0),
        "steps": episode.steps,
        "last_url": episode.steps[-1].url if episode.steps else run.target_url,
        "first_step": first,
    }
    after_break = (
        f" (the saved replay had broken: {broke})"
        if broke
        else f" ({recheck}; the replay still failed: {detail})"
        if recheck
        else ""
    )
    if passed:
        script = script_from_steps(run.target_url, episode.steps, checks)
        return FlowOutcome(
            "repaired" if broke else "passed", detail + after_break, script=script, **common
        )
    why = detail or f"not completed ({episode.stop_reason or 'no answer'})"
    # A failure the agent pinned down (it quoted what it expected) is saved, so the next run can
    # check it without the model.
    script = (
        script_from_steps(run.target_url, episode.steps, checks, failing=True) if checks else None
    )
    if script is None and recheck:  # keep the old failing script, counting from this recheck
        script = {**flow.script, "replays_since_agent": 0, "last_replay": None}
    return FlowOutcome("failed", why + after_break, script=script, **common)


def _page_text(page) -> str:
    try:
        return page.evaluate("() => document.body.innerText") or ""
    except Exception:  # the page closed or navigated away: no text to check against
        return ""


def record_flow(session: Session, run: Run, flow: Flow, outcome: FlowOutcome, agent_bugs) -> None:
    """Store the journey's result, save or update its script, and file a finding if it failed."""
    session.add(
        FlowResult(
            workspace_id=run.workspace_id,
            run_id=run.id,
            flow_id=flow.id,
            status=outcome.status,
            replayed=outcome.replayed,
            model_calls=outcome.model_calls,
            estimated_cost_usd=outcome.estimated_cost_usd,
            detail=outcome.detail[:1000],
        )
    )
    flow.last_status, flow.last_run_id = outcome.status, run.id
    if outcome.script:
        flow.script = outcome.script
        if not outcome.replayed:  # a replay only counts itself in the script (run 8, N2)
            flow.script_saved_at = func.now()
    if outcome.status == "failed" and (outcome.steps or outcome.replayed):
        bug = flow_finding(flow, outcome, run.target_url)
        agent_bugs.append(bug)
        session.add(Bug(run_id=run.id, **bug.model_dump()))
    session.commit()


def _describe_script_step(step: dict) -> str:
    element = step.get("element") or {}
    target = f'{element.get("role", "")} "{element.get("name", "")}"'.strip() if element else ""
    args = step.get("args") or {}
    detail = args.get("text") or args.get("option") or args.get("url") or args.get("size") or ""
    return " ".join(
        p
        for p in (
            step["action"].replace("_", " ").capitalize(),
            target,
            f"({detail})" if detail else "",
        )
        if p
    )


def flow_finding(flow: Flow, outcome: FlowOutcome, target_url: str) -> BugReport:
    """A journey the agent couldn't complete, as a finding that replay verifies like any other."""
    effective = [s for s in outcome.steps if s.action not in ("finish", "note") and not s.blocked]
    if outcome.replayed:  # found again by replaying the failing script: its steps, no run steps
        script_steps = (flow.script or {}).get("steps", [])
        return BugReport(
            title=f"Critical flow failed: {flow.name}"[:200],
            severity="high",
            category="functional",
            page_url=outcome.last_url or target_url,
            expected=flow.goal,
            actual=outcome.detail,
            repro_steps=[f"Open {target_url}", *[_describe_script_step(s) for s in script_steps]],
            evidence={
                "flow": {"id": str(flow.id), "name": flow.name},
                "observed": outcome.detail,
                "replayed_script": True,
            },
            reasoning=f'Critical flow "{flow.name}" still fails (checked by replay, no model).',
            step_indexes=[],
            source="agent",
            status="confirmed",  # the replay itself is the verification
        )
    return BugReport(
        title=f"Critical flow failed: {flow.name}"[:200],
        severity="high",
        category="functional",
        page_url=outcome.last_url or target_url,
        expected=flow.goal,
        actual=outcome.detail,
        repro_steps=[f"Open {target_url}", *[s.human for s in effective]],
        evidence={
            "flow": {"id": str(flow.id), "name": flow.name},
            "observed": outcome.detail,
            "reported_at": outcome.first_step + len(outcome.steps),
            "replay_from": outcome.first_step,
        },
        reasoning=f'The team\'s critical flow "{flow.name}" could not be completed.',
        step_indexes=[outcome.first_step + s.index - 1 for s in effective],
        source="agent",
        status="candidate",
    )


def cited_requirement(session: Session, bug: Bug) -> str | None:
    """The requirement a report cites (evidence.spec, run 7), for the verifier."""
    spec = (bug.evidence or {}).get("spec") or {}
    return chunk_text(session, spec["chunk_id"]) if spec.get("chunk_id") else None


def spec_source(session: Session, run: Run, settings: Settings):
    """The run's requirements (run 7, M3): a SpecRetriever when its target has specs and
    USE_SPECS is on, else None. Changed specs are embedded first. If the embedding model can't
    be reached, the run goes on without specs (a warning, not a failure)."""
    if not settings.use_specs:
        return None
    target = target_for(session, run.workspace_id, run.target_url)
    if target is None or not session.query(Spec.id).filter_by(target_id=target.id).first():
        return None
    embedder = OllamaEmbedder(settings.ollama_url, settings.embedding_model)
    try:
        written = sync_target(session, target.id, embedder)
    except Exception as error:
        session.rollback()
        log.warning(
            "specs for %s could not be embedded (%s): running without them", target.origin, error
        )
        return None
    if written:
        log.info("embedded %d spec chunk(s) for %s", written, target.origin)
    return SpecRetriever(session, target.id, embedder)


def run_interactive(
    session: Session,
    run: Run,
    llm: LLMClient,
    settings: Settings,
    storage: Storage,
    browser: Browser | None = None,
    verified: bool = False,
    reviewer: LLMClient | None = None,
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
        viewport=size_or_desktop(run.viewport) if run.viewport else None,
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
        max_cost_usd=remaining_budget(settings, run),
        max_repeats=settings.max_repeated_actions,
    )
    agent_bugs: list[BugReport] = []

    def recorders(first_agent_step: int):
        """Save an agent's steps and bugs as the run's, numbered from `first_agent_step`
        (a journey episode and the exploration each number their own steps from 1)."""

        def on_step(step: StepRecord) -> None:
            _save_agent_step(session, run, first_agent_step, step)

        def on_bug(bug: BugReport) -> None:
            # Step numbers the model used are 1-based within its loop; store run step indexes.
            bug.step_indexes = [first_agent_step + i - 1 for i in bug.step_indexes]
            reported_at = first_agent_step + bug.evidence.get("reported_at", 1) - 1
            bug.evidence = {
                **bug.evidence,
                "reported_at": reported_at,
                "replay_from": first_agent_step,
            }
            agent_bugs.append(bug)
            session.add(Bug(run_id=run.id, **bug.model_dump()))
            session.commit()

        return on_step, on_bug

    counter = itertools.count(1)

    def save(png: bytes, name: str) -> str:
        return storage.save(f"{run.id}/agent-{next(counter):03d}-{name}.png", png)

    with guarded_context(settings, run.target_url, browser, login) as (context, guard):
        specs = spec_source(session, run, settings)

        def agent_for(focus: str | None, agent_budget: Budget, first_step: int, explore: bool):
            on_step, on_bug = recorders(first_step)
            config = AgentConfig(
                target_url=run.target_url,
                mode=run.mode,
                budget=agent_budget,
                focus=focus,
                is_demo_target=is_demo_target(settings, run.target_url),
                login=login,
                known_lists=lists_from_crawl([(p.url, p.found_on) for p in report.pages]),
                specs=specs,
                viewport=run.viewport or "desktop",
            )
            return AgentRun(
                context.new_page(),
                llm,
                guard,
                config,
                save_screenshot=save,
                on_step=on_step,
                on_bug=on_bug,
                should_stop=lambda: _stop_requested(session, run),
                relogin=(lambda: sign_in(context, login)) if login else None,
                reviewer=reviewer if explore else None,  # journeys are judged by replay
            )

        # 2a. Critical flows first (run 7, M4): replayed without a model when they can be.
        def remaining_seconds() -> float:
            return max(max_seconds - (time.monotonic() - started), 0)

        flow_steps = 0
        if run.mode == "interactive":
            for flow in flows_for(session, run):
                budget_left = Budget(
                    max_steps=min(MAX_FLOW_STEPS, max_steps - flow_steps),
                    max_seconds=remaining_seconds(),
                    max_cost_usd=remaining_budget(settings, run),
                    max_repeats=settings.max_repeated_actions,
                )
                task = flow_task(flow.name, flow.goal, signed_in=login is not None)
                outcome = check_flow(
                    flow,
                    context,
                    budget_left,
                    run,
                    lambda budget_, first, task=task: agent_for(task, budget_, first, False),
                )
                flow_steps += outcome.model_calls
                record_flow(session, run, flow, outcome, agent_bugs)

        # 2b. Then explore, with what's left.
        budget.max_steps = max(max_steps - flow_steps, 0)
        budget.max_seconds = remaining_seconds()
        budget.max_cost_usd = remaining_budget(settings, run)
        agent = agent_for(run.focus, budget, run.step_count, True)
        result = agent.run()
    if reviewer is not None:
        _review_candidates(session, run, reviewer, result.reviewer_usage, login, settings)

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
        "suppressed": suppressed_count(session, run),  # triaged as false positives earlier
        "expectation_checks": {"dismissed": result.dismissed, "ignored": result.ignored},
    }
    session.commit()


def _review_candidates(
    session: Session,
    run: Run,
    reviewer: LLMClient,
    loop_usage: list[Usage],
    login: LoginConfig | None,
    settings: Settings,
) -> None:
    """The reviewer looks at each report the explorer filed: keep (rewritten) or drop.

    Reports the reviewer filed itself during the loop aren't reviewed again. Every reviewer
    call (the loop's and these) is logged as a "review" step and summed into the run's
    reviewer_* columns, apart from the explorer's share.
    """
    run.reviewer_provider, run.reviewer_model = reviewer.provider, reviewer.agent_model
    usages = list(loop_usage)
    explorer_reports = (
        session.query(Bug)
        .filter(Bug.run_id == run.id, Bug.source == "agent", Bug.status == "candidate")
        .order_by(Bug.created_at)
        .all()
    )
    for bug in explorer_reports:
        if "reviewer" in (bug.evidence or {}):
            continue
        if over_budget(settings, run, pending=usages):
            break  # out of budget: replay still checks the rest
        review = review_candidate(
            reviewer,
            target_url=run.target_url,
            title=bug.title,
            expected=bug.expected,
            actual=bug.actual,
            evidence=(bug.evidence or {}).get("observed"),
            steps=list(bug.repro_steps or []),
            scrub=login.scrub if login else (lambda text: text),
        )
        if review.usage:
            usages.append(review.usage)
        evidence = {**(bug.evidence or {}), "reviewer": reviewer.agent_model}
        if not review.is_bug:
            bug.status, bug.dismiss_reason = "dismissed", f"reviewer: {review.reason}"
        elif review.report:
            evidence["explorer_title"] = bug.title
            bug.title = review.report["title"]
            bug.severity = review.report["severity"]
            bug.category = review.report["category"]
            bug.expected = review.report["expected"] or bug.expected
            bug.actual = review.report["actual"] or bug.actual
        bug.evidence = evidence
    for usage in usages:
        _log_model_step(session, run, "review", {"model": usage.model}, usage)
        fields = usage_fields(usage)
        run.reviewer_input_tokens += fields["input_tokens"]
        run.reviewer_output_tokens += fields["output_tokens"]
        run.reviewer_cache_read_tokens += fields["cache_read_tokens"]
        run.reviewer_cache_write_tokens += fields["cache_write_tokens"]
        run.reviewer_cost_usd += fields["cost_usd"]
        run.reviewer_estimated_cost_usd += fields["estimated_cost_usd"]
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
                if over_budget(settings, run):
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
                viewport=replay_viewport(bug, run),
                scrub=login.scrub if login else (lambda text: text),
                requirement=cited_requirement(session, bug),
            )
        finally:
            context.close()
        _log_model_step(session, run, "verify_bug", {"bug": bug.title}, verdict.usage)
        if verdict.reproduced or over_budget(settings, run):
            break
    return verdict, start_url


def replay_viewport(bug, run) -> str:
    """The screen to check a report on: the one it names (a phone-width screenshot review),
    else the run's own viewport, else desktop."""
    return (bug.evidence or {}).get("viewport") or run.viewport or "desktop"


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
