"""Re-check an old run's agent reports with today's replay, without changing the run.

After a replay fix, the question is "would these reports verify now?". This replays each
candidate the run's verification looked at (agent reports, not duplicates) from its stored
steps, in a fresh browser context per plan, and returns the outcome. The stored verdicts stay
as they were recorded: benchmark history isn't rewritten.

Without a judge it only replays (no model call): did the steps reach the reported state? With
a judge it also asks the model, exactly as verification does.
"""

import uuid

from playwright.sync_api import Browser
from sqlalchemy.orm import Session

from worker.config import Settings
from worker.db.models import Bug, Run, Step
from worker.execute import replay_plans
from worker.llm import LLMClient
from worker.login import login_at_the_time
from worker.scan import guarded_browser
from worker.verify import VIEWPORTS, ReplayError, failure_of, replay, verify_bug


def reverify_run(
    session: Session,
    run_id: uuid.UUID,
    settings: Settings,
    browser: Browser | None = None,
    judge: LLMClient | None = None,
    only_status: str | None = None,
) -> list[dict]:
    """One outcome per agent report: title, recorded status/reason, replayed, reproduced, ..."""
    run = session.get(Run, run_id)
    steps = {s.index: s for s in session.query(Step).filter_by(run_id=run_id)}
    query = session.query(Bug).filter(
        Bug.run_id == run_id, Bug.source != "deterministic", Bug.duplicate_of_id.is_(None)
    )
    if only_status:  # e.g. "dismissed": re-check only what replay rejected
        query = query.filter(Bug.status == only_status)
    bugs = query.order_by(Bug.created_at).all()
    outcomes = []
    login = login_at_the_time(session, settings, run)  # signed in only if the run was
    scrub = login.scrub if login else (lambda text: text)
    with guarded_browser(settings, run.target_url, browser, login) as (new_context, _guard):
        for bug in bugs:
            outcome = {
                "title": bug.title,
                "recorded_status": bug.status,
                "recorded_reason": bug.dismiss_reason,
                "replayed": False,
                "reproduced": None,
                "failure": None,
                "start": None,
                "reason": None,
                "diff": None,  # what the last replayed action changed (with a judge only)
            }
            viewport = (bug.evidence or {}).get("viewport", "desktop")
            for start_url, replay_steps in replay_plans(bug, steps, run.target_url):
                context = new_context()
                try:
                    if judge is None:
                        page = context.new_page()
                        page.set_viewport_size(VIEWPORTS.get(viewport, VIEWPORTS["desktop"]))
                        try:
                            replay(page, start_url, replay_steps)
                            replayed, reproduced, failure, reason = True, None, None, page.url
                        except ReplayError as error:
                            replayed, reproduced, reason = False, None, str(error)
                            failure = failure_of(error)
                    else:
                        verdict = verify_bug(
                            context,
                            judge,
                            start_url,
                            replay_steps,
                            bug.title,
                            bug.expected,
                            bug.actual,
                            viewport=viewport,
                            scrub=scrub,
                        )
                        replayed, reproduced = verdict.replayed, verdict.reproduced
                        failure, reason = verdict.failure, verdict.reason
                        outcome["diff"] = verdict.diff
                finally:
                    context.close()
                outcome.update(
                    replayed=replayed,
                    reproduced=reproduced,
                    failure=failure,
                    start=start_url,
                    reason=reason,
                )
                if reproduced or (judge is None and replayed):
                    break
            outcomes.append(outcome)
    return outcomes
