"""Running one deep-mode run, from a claimed run to a finished, stopped or paused one.

1. The same free part as the current loop: crawl and run the deterministic checks (skipped on a
   resume: they ran the first time).
2. The harness and a driver (the Agent SDK, or a script when LLM_PROVIDER=fake), in a guarded
   browser context; every step, finding and coverage update is written to the database as it
   happens (DbRecorder), so the run page shows them live.
3. Verification of every finding, paused runs included: replay, re-measurement, or unverified.

A usage limit pauses the run: its status becomes `paused` (the runner sets it) with the reason,
and `worker resume RUN_ID` or the dashboard's Resume button queues it again. A resumed run starts
the browser fresh on the target and continues from its saved coverage; the Agent SDK session is
resumed too when this machine still has it.
"""

import itertools
import json
import time

from playwright.sync_api import Browser
from sqlalchemy.orm import Session

from worker.config import Settings
from worker.db.models import Bug, ModelConfig, Run, RunStatus, Step, Workspace
from worker.deep.config import deep_limits, deep_model
from worker.deep.harness import Harness, HarnessConfig
from worker.deep.scripted import ScriptedDriver, TurnDriver
from worker.deep.sdk_driver import SdkConfig, SdkDriver, check_auth, run_workdir
from worker.deep.toolbox import Action, Toolbox, ToolboxConfig, ToolResult
from worker.llm.base import LLMClient, Usage
from worker.model_configs import ModelConfigError, decrypt_key
from worker.report import BugReport
from worker.safety.network import BlockedError
from worker.storage import Storage
from worker.verify import size_or_desktop

MAX_EVENTS_PER_STEP = 20


class DbRecorder:
    """Writes the harness's steps, findings, coverage and usage to the run, as they happen.

    Harness step n is stored as the run's step `first_step + n - 1` (the crawl's visits come
    first), and the step numbers inside a finding are moved the same way. A resumed run
    continues after the last stored step (verification may have logged steps when it paused),
    so its `first_step` is shifted back by the steps already taken. `segment_start` is where
    this browser session began: a replay of everything up to a report starts there, because the
    browser was fresh at that point."""

    def __init__(
        self,
        session: Session,
        run: Run,
        storage: Storage,
        first_step: int,
        segment_start: int | None = None,
    ):
        self.session = session
        self.run = run
        self.storage = storage
        self.first_step = first_step
        self.segment_start = first_step if segment_start is None else segment_start
        self.session_id: str | None = (run.coverage or {}).get("session_id")
        self._last_screenshot: str | None = None

    def index(self, step: int) -> int:
        return self.first_step + step - 1

    def on_step(self, step: int, action: Action, result: ToolResult) -> None:
        index = self.index(step)
        screenshot = None
        if action.image:
            screenshot = self.storage.save(f"{self.run.id}/deep-{index:04d}.jpg", action.image)
            self._last_screenshot = screenshot
        args = {k: v for k, v in action.args.items()}
        self.session.add(
            Step(
                run_id=self.run.id,
                index=index,
                action=action.tool,
                args={
                    **args,
                    "result": action.result,
                    "element": action.element,
                    "viewport": action.viewport,
                },
                url=action.url,
                screenshot=screenshot,
                blocked=action.blocked,
                block_reason=action.block_reason,
            )
        )
        self.run.step_count = max(self.run.step_count, index + 1)
        self.session.commit()

    def on_bug(self, bug: BugReport) -> None:
        evidence = dict(bug.evidence)
        verify = dict(evidence.get("verify") or {})
        for key in ("steps", "setup_steps"):
            if key in verify:
                verify[key] = [self.index(s) for s in verify[key]]
        if isinstance(verify.get("step"), int):
            verify["step"] = self.index(verify["step"])
        evidence["verify"] = verify
        evidence["reported_at"] = self.index(evidence.get("reported_at", 1))
        evidence["replay_from"] = self.segment_start
        stored = bug.model_copy(
            update={
                "evidence": evidence,
                "step_indexes": [self.index(s) for s in bug.step_indexes],
                "screenshot": bug.screenshot or self._last_screenshot,
            }
        )
        self.session.add(Bug(run_id=self.run.id, **stored.model_dump()))
        self.session.commit()

    def on_coverage(self, coverage: dict) -> None:
        self.run.coverage = {
            **coverage,
            "first_step": self.first_step,
            "session_id": self.session_id,
        }
        self.session.commit()

    def on_usage(self, usage: Usage) -> None:
        self.run.input_tokens += usage.input_tokens
        self.run.output_tokens += usage.output_tokens
        self.run.cache_read_tokens += usage.cache_read_tokens
        self.run.cache_write_tokens += usage.cache_write_tokens
        self.run.cost_usd += usage.cost_usd
        self.run.estimated_cost_usd += usage.api_cost_usd
        self.session.commit()


def run_deep(
    session: Session,
    run: Run,
    llm: LLMClient,
    settings: Settings,
    storage: Storage,
    browser: Browser | None = None,
    verified: bool = False,
    driver: TurnDriver | None = None,
) -> None:
    """Run (or resume) a deep-mode run. `llm` judges replays and duplicates, as for the loop;
    `driver`: tests pass their own, otherwise make_driver picks it."""
    # Imported here: execute imports this module, and these live in execute.
    from worker.execute import (
        _save_visit,
        _stop_requested,
        interactive_allowed,
        summarize,
        verify_and_dedupe,
    )
    from worker.login import login_for_run
    from worker.scan import guarded_context, is_demo_target, passive_scan

    if not interactive_allowed(settings, run.target_url, verified):
        raise BlockedError("deep mode is only allowed on the demo shop and verified domains")
    workspace = session.get(Workspace, run.workspace_id)
    limits = deep_limits(settings, workspace, run)
    model = deep_model(settings, run)
    driver = driver or make_driver(session, run, settings, model)
    login = login_for_run(session, settings, run)
    viewport = size_or_desktop(run.viewport) if run.viewport else None
    resuming = bool(run.coverage)
    deterministic: list[BugReport] = []
    pages = []
    if resuming:
        run.paused_reason = None
        # Continue after every stored step: harness step n → first_step + n - 1.
        first_step = run.step_count - int(run.coverage.get("steps") or 0)
    else:
        numbers = itertools.count(run.step_count)
        report = passive_scan(
            run.target_url,
            settings,
            storage,
            str(run.id),
            on_page=lambda page: _save_visit(session, run, page, next(numbers)),
            should_stop=lambda: _stop_requested(session, run),
            browser=browser,
            login=login,
            viewport=viewport,
        )
        pages, deterministic = report.pages, report.bugs
        for bug in deterministic:
            session.add(Bug(run_id=run.id, **bug.model_dump()))
        session.commit()
        first_step = run.step_count
        if run.stop_requested:
            run.summary = summarize(pages, deterministic)
            return
    recorder = DbRecorder(session, run, storage, first_step, segment_start=run.step_count)
    started = time.monotonic()
    with guarded_context(settings, run.target_url, browser, login, viewport) as (context, guard):
        toolbox = Toolbox(
            context.new_page(),
            guard,
            ToolboxConfig(
                target_url=run.target_url,
                mode=run.mode,
                is_demo_target=is_demo_target(settings, run.target_url),
                signed_in=login is not None,
                screenshot_max_width=settings.deep_screenshot_max_width,
                screenshot_quality=settings.deep_screenshot_quality,
                scrub=login.scrub if login else (lambda text: text),
            ),
        )
        toolbox.start()
        harness = Harness(
            toolbox,
            HarnessConfig(
                max_steps=limits.steps,
                max_seconds=limits.seconds,
                should_stop=lambda: _stop_requested(session, run),
            ),
            recorder,
            coverage=run.coverage if resuming else None,
        )
        outcome = driver.run(harness)
        recorder.session_id = getattr(driver, "session_id", None) or recorder.session_id
        recorder.on_coverage(harness.coverage())
    if harness.paused:
        run.paused_reason = harness.paused_detail or "usage limit"
    # Findings so far are verified as usual, a paused run's too.
    verification = verify_and_dedupe(session, run, llm, settings, browser, login)
    all_bugs = [BugReport.model_validate(b, from_attributes=True) for b in run.bugs]
    coverage = harness.coverage()
    run.summary = {
        **summarize(pages, all_bugs),
        "engine": "deep",
        "model": model,
        "stop_reason": outcome.stop_reason,
        "agent_summary": harness.summary or None,
        "verification": verification,
        "coverage": {
            "pages_mapped": len((coverage.get("map") or {}).get("pages") or []),
            "plan_items": len(coverage["plan"]),
            "ticked": len(coverage["progress"]),
            "unticked": coverage["unticked"],
            "candidates": len(coverage["candidates"]),
            "screenshots": coverage["screenshots"],
        },
        "seconds": round(coverage["seconds"] or (time.monotonic() - started), 1),
    }
    session.commit()


def make_driver(session: Session, run: Run, settings: Settings, model: str) -> TurnDriver:
    """The scripted driver with LLM_PROVIDER=fake (DEEP_SCRIPT), else the Agent SDK."""
    if settings.provider() == "fake":
        return ScriptedDriver(parse_script(settings.deep_script))
    auth = settings.deep_auth
    api_key = api_key_for(session, run, settings) if auth == "api" else None
    check_auth(settings, auth, api_key)
    run.provider = "claude-agent-sdk" if auth == "api" else "claude-cli"
    run.model = model
    session.commit()
    return SdkDriver(
        SdkConfig(
            model=model,
            effort=settings.deep_effort,
            auth=auth,
            workdir=run_workdir(str(run.id)),
            api_key=api_key,
            resume_session=(run.coverage or {}).get("session_id"),
        )
    )


def api_key_for(session: Session, run: Run, settings: Settings) -> str | None:
    """The run's workspace's own Anthropic key (its model), else the worker's."""
    if run.model_config_id is not None:
        config = session.get(ModelConfig, run.model_config_id)
        if config is None or config.workspace_id != run.workspace_id:
            raise ModelConfigError("the run's model doesn't belong to this workspace")
        if config.provider != "claude":
            raise ModelConfigError("deep mode needs an Anthropic model (Settings → Models)")
        return decrypt_key(config, settings)
    return settings.anthropic_api_key.get_secret_value() or None


def parse_script(text: str) -> list[list[tuple[str, dict]]]:
    """DEEP_SCRIPT: the fake model's turns, as JSON [[["tool", {args}], ...], ...]."""
    if not text.strip():
        return []
    turns = json.loads(text)
    return [[(str(name), dict(args)) for name, args in turn] for turn in turns]


def resume(session: Session, run_id: str) -> Run:
    """Queue a paused run again (CLI `worker resume`, the dashboard's Resume button)."""
    from worker.queue import transition

    run = session.get(Run, run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    if run.status != RunStatus.PAUSED:
        raise ValueError(f"run {run_id} is {run.status}, not paused")
    transition(run, RunStatus.QUEUED)
    session.commit()
    return run
