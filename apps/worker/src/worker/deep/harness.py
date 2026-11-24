"""Deep mode's harness: the process, the gates and the budgets, enforced in code.

A driver (the Agent SDK, or a script in tests) asks `next_prompt()` for the next turn, sends it
to the model, and routes every tool call the model makes through `call()`. The harness:

- numbers every call as a step of the run and records it (the timeline, and replay's input);
- keeps the phase: MAP → PLAN → EXECUTE → REVIEW → done. save_map leaves MAP; save_plan, which
  must cover the whole checklist (layout at every viewport), leaves PLAN; the plan items are
  handed out a batch per turn; REVIEW comes when every item is ticked or the budget runs low;
- gates the process tools: no plan before a map, no ticks for unknown items, no report without a
  flagged candidate and a re-check after the flag, no finish while items or candidates are open
  or before screenshots were seen at every viewport (unless the budget is nearly gone);
- measures a reported measurement or check itself, so a report's evidence is what the harness
  saw, not what the model claims;
- stops on the step or time budget, when the user stops the run, or when the model stops making
  progress; pauses (keeping everything) on a usage limit;
- saves the coverage (map, plan, progress, candidates, screenshots seen, budget used) after
  every call, so the run page shows it live and a paused run can resume from it.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from worker.deep.checklist import AREA_KEYS, AREAS, VIEWPORTS
from worker.deep.prompt import execute_prompt, map_prompt, nudge, plan_prompt, review_prompt
from worker.deep.toolbox import Action, Toolbox, ToolResult
from worker.deep.tools import PROCESS_TOOL_NAMES
from worker.llm.base import Usage
from worker.report import BugReport
from worker.safety.secrets import redact

PHASES = ("map", "plan", "execute", "review", "done")
BATCH = 8  # plan items handed out per execute turn
MAX_IDLE_TURNS = 3  # turns in a row without progress before the run is stopped
SEVERITIES = ("critical", "high", "medium", "low")
CHECKS = {"run_axe", "check_layout", "check_meta", "keyboard_probe"}
MAX_FIELD = 2000  # characters kept of a free-text field the model writes


class Recorder(Protocol):
    """Where the harness writes what happens (the database in a real run)."""

    def on_step(self, step: int, action: Action, result: ToolResult) -> None: ...

    def on_bug(self, bug: BugReport) -> None: ...

    def on_coverage(self, coverage: dict) -> None: ...

    def on_usage(self, usage: Usage) -> None: ...


@dataclass
class MemoryRecorder:
    """Keeps everything in memory: tests, and the CLI before it writes to the database."""

    actions: list[Action] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)
    bugs: list[BugReport] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    usage: list[Usage] = field(default_factory=list)

    def on_step(self, step: int, action: Action, result: ToolResult) -> None:
        self.actions.append(action)
        self.results.append(result)

    def on_bug(self, bug: BugReport) -> None:
        self.bugs.append(bug)

    def on_coverage(self, coverage: dict) -> None:
        self.coverage = coverage

    def on_usage(self, usage: Usage) -> None:
        self.usage.append(usage)


@dataclass
class HarnessConfig:
    max_steps: int
    max_seconds: float
    should_stop: Callable[[], bool] | None = None  # the user pressed Stop
    reserve_share: float = 0.1  # the last share of the budget is kept for review


class GateError(Exception):
    """A process tool called out of order or with an incomplete payload."""


@dataclass
class _Step:
    action: Action
    data: dict | None


class Harness:
    def __init__(
        self,
        toolbox: Toolbox,
        config: HarnessConfig,
        recorder: Recorder,
        coverage: dict | None = None,
    ):
        self.toolbox = toolbox
        self.config = config
        self.recorder = recorder
        self.phase = "map"
        self.map: dict | None = None
        self.plan: list[dict] = []
        self.not_applicable: list[dict] = []
        self.progress: dict[str, dict] = {}
        self.candidates: list[dict] = []
        self.screenshots: dict[str, int] = {}
        self.bug_titles: list[str] = []
        self.steps = 0
        self.stop_reason = ""
        self.paused = False
        self.paused_detail = ""
        self.summary = ""
        self.unticked: list[str] = []
        self.usage = Usage(model="")
        self._seconds_before = 0.0  # time used before a resume
        self._started = time.monotonic()
        self._history: dict[int, _Step] = {}  # this session's steps (not restored on resume)
        self._resumed = False
        self._last_signature: tuple | None = None
        self._idle_turns = 0
        if coverage:
            self._restore(coverage)

    # --- the driver's side -------------------------------------------------------------------

    def next_prompt(self) -> str | None:
        """The next turn's instruction, or None when the run is over."""
        if self.stop_reason or self._check_stop():
            return None
        if self.phase == "done":
            return None
        signature = self._signature()
        if signature == self._last_signature:
            self._idle_turns += 1
            if self._idle_turns >= MAX_IDLE_TURNS:
                self._stop(f"no progress in {MAX_IDLE_TURNS} turns ({self.phase} phase)")
                return None
        else:
            self._idle_turns = 0
        self._last_signature = signature
        prompt = self._phase_prompt()
        if self._idle_turns:
            prompt = nudge(self._missing()) + "\n\n" + prompt
        self._resumed = False
        return prompt

    def call(self, name: str, args: dict) -> ToolResult:
        """Run one tool call as the next step of the run."""
        if self.stop_reason or self._check_stop():
            return ToolResult(
                f"error: the run is over ({self.stop_reason}); end your turn now", is_error=True
            )
        self.steps += 1
        step = self.steps
        if name in PROCESS_TOOL_NAMES:
            action = Action(
                tool=name,
                args=dict(args or {}),
                url=self.toolbox.page.url,
                viewport=self.toolbox.viewport,
            )
            try:
                text, data = self._process(name, dict(args or {}), step)
                result = ToolResult(text, data=data)
            except GateError as error:
                result = ToolResult(f"error: {error}", is_error=True)
            action.result = result.text.splitlines()[0][:300] if result.text else ""
            result.action = action
        else:
            result = self.toolbox.call(name, args)
            action = result.action
            if name == "screenshot" and not result.is_error:
                self.screenshots[action.viewport] = self.screenshots.get(action.viewport, 0) + 1
        result.step = step
        result.text = f"#{step} {result.text}"
        self._history[step] = _Step(action, result.data)
        self.recorder.on_step(step, action, result)
        self._save_coverage()
        return result

    def add_usage(self, usage: Usage) -> None:
        """The model's tokens and cost so far, from the driver."""
        self.usage.model = self.usage.model or usage.model
        self.usage.input_tokens += usage.input_tokens
        self.usage.output_tokens += usage.output_tokens
        self.usage.cache_read_tokens += usage.cache_read_tokens
        self.usage.cache_write_tokens += usage.cache_write_tokens
        self.usage.cost_usd += usage.cost_usd
        self.usage.estimated_cost_usd += usage.estimated_cost_usd
        self.recorder.on_usage(usage)  # the run's totals (tokens and cost) in a real run
        self._save_coverage()

    def pause(self, detail: str) -> None:
        """A usage limit: stop now, keep everything, and say the run can resume."""
        self.paused = True
        self.paused_detail = detail
        self.stop_reason = "paused: usage limit"
        self._save_coverage()

    def stop(self, reason: str) -> None:
        """Stop for a reason outside the harness (a model error, the driver's own limit)."""
        self._stop(reason)

    # --- budgets -----------------------------------------------------------------------------

    @property
    def seconds_used(self) -> float:
        return self._seconds_before + time.monotonic() - self._started

    def _check_stop(self) -> bool:
        if self.config.should_stop and self.config.should_stop():
            self._stop("stopped by the user")
        elif self.steps >= self.config.max_steps:
            self._stop(f"step budget reached ({self.config.max_steps} steps)")
        elif self.seconds_used >= self.config.max_seconds:
            self._stop(f"time budget reached ({self.config.max_seconds:.0f} s)")
        return bool(self.stop_reason)

    def _stop(self, reason: str) -> None:
        self.stop_reason = self.stop_reason or reason
        self._save_coverage()

    def near_end(self) -> bool:
        """Is the budget nearly used up? Then review now, and finish is always allowed."""
        share = self.config.reserve_share
        steps_left = self.config.max_steps - self.steps
        seconds_left = self.config.max_seconds - self.seconds_used
        return steps_left <= max(2, self.config.max_steps * share) or (
            seconds_left <= self.config.max_seconds * share
        )

    # --- prompts -----------------------------------------------------------------------------

    def _phase_prompt(self) -> str:
        if self.phase == "map":
            return map_prompt(self.toolbox.config.target_url)
        if self.phase == "plan":
            return plan_prompt()
        if self.phase == "execute" and not self.near_end():
            pending = self._pending()
            if pending:
                return execute_prompt(pending[:BATCH], len(pending), resumed=self._resumed)
            self.phase = "review"
        return review_prompt(self._open_candidates(), self.near_end(), resumed=self._resumed)

    def _missing(self) -> str:
        if self.phase == "map":
            return "save_map hasn't been called"
        if self.phase == "plan":
            return "save_plan hasn't been accepted"
        if self.phase == "execute":
            return f"{len(self._pending())} plan items are still open"
        return "finish hasn't been accepted"

    def _signature(self) -> tuple:
        """What counts as progress between turns."""
        resolved = sum(1 for c in self.candidates if c["status"] != "open")
        return (
            self.phase,
            len(self.progress),
            len(self.candidates),
            resolved,
            len(self.bug_titles),
        )

    # --- process tools -----------------------------------------------------------------------

    def _process(self, name: str, args: dict, step: int) -> tuple[str, dict | None]:
        if self.phase == "done":
            raise GateError("the run is finished")
        handler = {
            "save_map": self._save_map,
            "save_plan": self._save_plan,
            "tick": self._tick,
            "flag_candidate": self._flag,
            "drop_candidate": self._drop,
            "report_bug": self._report,
            "finish": self._finish,
        }[name]
        return handler(args, step)

    def _save_map(self, args: dict, step: int) -> tuple[str, None]:
        pages = [p for p in args.get("pages") or [] if isinstance(p, dict) and p.get("url")]
        flows = [f for f in args.get("flows") or [] if isinstance(f, dict) and f.get("name")]
        if not pages or not flows:
            raise GateError("a map needs at least one page (url, purpose) and one flow")
        self.map = {
            "pages": [_clean(p, ("url", "purpose")) for p in pages],
            "flows": [_clean(f, ("name", "description")) for f in flows],
            "summary": _text(args.get("summary")),
        }
        if self.phase == "map":
            self.phase = "plan"
            return f"map saved ({len(pages)} pages, {len(flows)} flows). End your turn.", None
        return f"map updated ({len(pages)} pages, {len(flows)} flows)", None

    def _save_plan(self, args: dict, step: int) -> tuple[str, None]:
        if self.phase == "map":
            raise GateError("save the map first (save_map), then write the plan")
        if self.phase != "plan":
            raise GateError("the plan is already saved; work through its items")
        items, problems = [], []
        seen: set[str] = set()
        for raw in args.get("items") or []:
            if not isinstance(raw, dict):
                continue
            item = _clean(raw, ("id", "area", "description", "viewport"))
            if not item.get("id") or item["id"] in seen:
                problems.append(f"item ids must be unique and not empty ({item.get('id')!r})")
                continue
            if item.get("area") not in AREA_KEYS:
                problems.append(f"{item['id']}: unknown area {item.get('area')!r}")
                continue
            seen.add(item["id"])
            items.append(item)
        skipped = {
            n["area"]: _text(n.get("reason"))
            for n in args.get("not_applicable") or []
            if isinstance(n, dict) and n.get("area") in AREA_KEYS and _text(n.get("reason"))
        }
        planned = {item["area"] for item in items}
        for area in AREAS:
            if area.key in planned:
                continue
            if area.key in skipped and area.can_skip:
                continue
            problems.append(f"no item for {area.key} ({area.title})")
        layout_viewports = {i.get("viewport") for i in items if i["area"] == "layout"}
        missing = [v for v in VIEWPORTS if v not in layout_viewports]
        if missing:
            problems.append(f"layout items are missing for {', '.join(missing)}")
        if problems:
            raise GateError("the plan isn't complete: " + "; ".join(problems))
        self.plan = items
        self.not_applicable = [{"area": a, "reason": r} for a, r in skipped.items()]
        self.phase = "execute"
        return f"plan saved ({len(items)} items). End your turn.", None

    def _tick(self, args: dict, step: int) -> tuple[str, None]:
        if self.phase not in ("execute", "review"):
            raise GateError("there is no plan to tick yet")
        item_id = _text(args.get("item_id"))
        if item_id not in {item["id"] for item in self.plan}:
            raise GateError(f"no plan item {item_id!r}")
        status = args.get("status")
        if status not in ("done", "skipped", "blocked"):
            raise GateError("status must be done, skipped or blocked")
        self.progress[item_id] = {"status": status, "note": _text(args.get("note")), "step": step}
        return f"{item_id} {status}; {len(self._pending())} items open", None

    def _flag(self, args: dict, step: int) -> tuple[str, None]:
        title = _text(args.get("title"))
        if not title:
            raise GateError("a candidate needs a title")
        candidate = {
            "id": f"c{len(self.candidates) + 1}",
            "title": title,
            "observation": _text(args.get("observation")),
            "step": step,
            "url": self.toolbox.page.url,
            "status": "open",
        }
        self.candidates.append(candidate)
        return (
            f"candidate {candidate['id']} flagged. Try to disprove it before you report it.",
            None,
        )

    def _drop(self, args: dict, step: int) -> tuple[str, None]:
        candidate = self._open_candidate(args.get("candidate_id"))
        candidate.update(status="dropped", reason=_text(args.get("reason")))
        return f"{candidate['id']} dropped", None

    def _report(self, args: dict, step: int) -> tuple[str, dict]:
        candidate = self._open_candidate(args.get("candidate_id"))
        rechecks = [
            s
            for s, recorded in self._history.items()
            if s > candidate["step"] and recorded.action.tool not in PROCESS_TOOL_NAMES
        ]
        if not rechecks:
            raise GateError(
                f"re-check {candidate['id']} first: look at it again with a browser tool and try "
                "to disprove it"
            )
        title = redact(_text(args.get("title")))[:200]
        if not title:
            raise GateError("a report needs a title")
        if title in self.bug_titles:
            raise GateError("this bug was already reported")
        severity = args.get("severity")
        if severity not in SEVERITIES:
            raise GateError(f"severity must be one of {', '.join(SEVERITIES)}")
        self_review = _text(args.get("self_review"))
        if not self_review:
            raise GateError("say how you tried to disprove it (self_review)")
        verify = self._verify_spec(args.get("verify"), step)
        steps = verify.get("steps") or verify.get("setup_steps") or []
        bug = BugReport(
            title=title,
            severity=severity,
            category=_text(args.get("category")) or "functional",
            page_url=self.toolbox.page.url,
            expected=redact(_text(args.get("expected"))) or None,
            actual=redact(_text(args.get("actual"))) or None,
            repro_steps=self._repro(args.get("steps_to_reproduce"), steps),
            evidence={
                "engine": "deep",
                "verify": verify,
                "self_review": redact(self_review),
                "candidate": candidate["id"],
                "observed": redact(candidate["observation"]),
                "viewport": self.toolbox.viewport,
                "reported_at": step,
                **self._last_element(steps),
            },
            reasoning=redact(self_review),
            step_indexes=list(steps),
            source="agent",
            status="candidate",
        )
        candidate.update(status="reported", bug=title)
        self.bug_titles.append(title)
        self.recorder.on_bug(bug)
        return f"bug recorded from {candidate['id']}; it will be verified in a fresh browser", {
            "verify": verify
        }

    def _finish(self, args: dict, step: int) -> tuple[str, None]:
        if not self.near_end():
            problems = []
            if self.phase not in ("execute", "review"):
                problems.append(f"the {self.phase} phase isn't done")
            pending = [item["id"] for item in self._pending()]
            if pending:
                problems.append("plan items still open: " + ", ".join(pending[:20]))
            missing = [v for v in VIEWPORTS if not self.screenshots.get(v)]
            if missing:
                problems.append("no screenshot seen at " + ", ".join(missing))
            open_ids = [c["id"] for c in self._open_candidates()]
            if open_ids:
                problems.append("candidates still open: " + ", ".join(open_ids))
            if problems:
                raise GateError("not finished: " + "; ".join(problems))
        self.unticked = [item["id"] for item in self._pending()]
        self.summary = _text(args.get("summary"))
        self.phase = "done"
        self.stop_reason = "finished"
        return "finished", None

    # --- verification specs ------------------------------------------------------------------

    def _verify_spec(self, raw, step: int) -> dict:
        if not isinstance(raw, dict) or raw.get("kind") not in ("replay", "measure", "check"):
            raise GateError("verify must say kind: replay, measure or check")
        kind = raw["kind"]
        if kind == "replay":
            steps = self._replay_steps(raw.get("steps"), "steps", step)
            if not steps:
                raise GateError("a replay needs the steps that reproduce the bug")
            return {"kind": "replay", "steps": steps}
        setup = self._replay_steps(raw.get("setup_steps") or [], "setup_steps", step)
        where = {"url": self.toolbox.page.url, "viewport": self.toolbox.viewport}
        if kind == "measure":
            snippet = raw.get("snippet")
            if not isinstance(snippet, str) or not snippet.strip():
                raise GateError("a measurement needs the snippet that measures it")
            measured = self.toolbox.call("evaluate_js", {"snippet": snippet})
            data = measured.data or {}
            if measured.is_error or data.get("error"):
                raise GateError(f"the snippet failed when the harness ran it: {data.get('error')}")
            if data.get("changed_the_page") or data.get("blocked_requests"):
                raise GateError("a measuring snippet must not change the page or send data")
            return {
                "kind": "measure",
                "snippet": snippet,
                "setup_steps": setup,
                "result": data.get("value"),
                **where,
            }
        check = raw.get("check")
        rule = _text(raw.get("rule"))
        if check not in CHECKS or not rule:
            raise GateError(f"a check needs one of {', '.join(sorted(CHECKS))} and its rule")
        if check == "keyboard_probe":
            return self._probe_spec(raw, rule)
        result = self.toolbox.call(check, {})
        found = rule_detail(check, rule, result.data or {})
        if found is None:
            raise GateError(f"{check} doesn't report {rule!r} on this page now")
        return {
            "kind": "check",
            "check": check,
            "rule": rule,
            "setup_steps": setup,
            "result": found,
            **where,
        }

    def _probe_spec(self, raw: dict, rule: str) -> dict:
        probe_step = raw.get("step")
        recorded = self._history.get(probe_step) if isinstance(probe_step, int) else None
        if recorded is None or recorded.action.tool != "keyboard_probe" or not recorded.data:
            raise GateError("name the keyboard_probe step whose result you report (step)")
        failures = recorded.data.get("failures") or []
        failed = next((f for f in failures if f.get("check") == rule), None)
        if failed is None:
            raise GateError(f"that probe didn't fail the {rule!r} check")
        setup = [s for s in sorted(self._history) if s < probe_step and self._replayable(s)]
        return {
            "kind": "check",
            "check": "keyboard_probe",
            "rule": rule,
            "step": probe_step,
            "setup_steps": setup,
            "element": recorded.action.element,
            "result": failed,
            "url": recorded.action.url,
            "viewport": recorded.action.viewport,
        }

    def _replay_steps(self, raw, name: str, now: int) -> list[int]:
        if not isinstance(raw, list) or not all(isinstance(s, int) for s in raw):
            raise GateError(f"{name} must be a list of step numbers")
        bad = [s for s in raw if not (0 < s < now and self._replayable(s))]
        if bad:
            raise GateError(
                f"{name} {bad} aren't browser actions of this run that replay can repeat "
                "(navigate, click, type, select, press_key, hover, scroll, set_viewport, go_back)"
            )
        return list(raw)

    def _replayable(self, step: int) -> bool:
        recorded = self._history.get(step)
        return recorded is not None and recorded.action.replayable

    # --- helpers -----------------------------------------------------------------------------

    def _pending(self) -> list[dict]:
        return [item for item in self.plan if item["id"] not in self.progress]

    def _open_candidates(self) -> list[dict]:
        return [c for c in self.candidates if c["status"] == "open"]

    def _open_candidate(self, candidate_id) -> dict:
        candidate = next(
            (c for c in self.candidates if c["id"] == candidate_id and c["status"] == "open"),
            None,
        )
        if candidate is None:
            raise GateError(f"no open candidate {candidate_id!r}: flag_candidate first")
        return candidate

    def _repro(self, written, steps: list[int]) -> list[str]:
        """The model's own steps to reproduce, else the recorded actions it named."""
        if isinstance(written, list) and written:
            return [redact(_text(s))[:300] for s in written if _text(s)][:30]
        return [_describe(self._history[s].action) for s in steps if s in self._history]

    def _last_element(self, steps: list[int]) -> dict:
        for s in reversed(steps):
            element = self._history[s].action.element if s in self._history else None
            if element and element.get("name"):
                return {"element": {"role": element.get("role"), "name": element["name"]}}
        return {}

    def coverage(self) -> dict:
        return {
            "phase": self.phase,
            "map": self.map,
            "plan": self.plan,
            "not_applicable": self.not_applicable,
            "progress": self.progress,
            "candidates": self.candidates,
            "screenshots": self.screenshots,
            "bugs": self.bug_titles,
            "steps": self.steps,
            "seconds": round(self.seconds_used, 1),
            "unticked": self.unticked,
            "summary": self.summary,
            "stop_reason": self.stop_reason,
            "paused_reason": self.paused_detail or None,
            "usage": {
                "model": self.usage.model,
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "cache_read_tokens": self.usage.cache_read_tokens,
                "cache_write_tokens": self.usage.cache_write_tokens,
                "cost_usd": round(self.usage.cost_usd, 6),
                "estimated_cost_usd": round(self.usage.estimated_cost_usd, 6),
            },
        }

    def _save_coverage(self) -> None:
        self.recorder.on_coverage(self.coverage())

    def _restore(self, saved: dict) -> None:
        """Continue a paused run: everything but the browser's state and this session's steps."""
        self.phase = saved.get("phase") if saved.get("phase") in PHASES else "map"
        if self.phase == "done":
            self.phase = "review"
        self.map = saved.get("map")
        self.plan = list(saved.get("plan") or [])
        self.not_applicable = list(saved.get("not_applicable") or [])
        self.progress = dict(saved.get("progress") or {})
        self.candidates = list(saved.get("candidates") or [])
        self.screenshots = dict(saved.get("screenshots") or {})
        self.bug_titles = list(saved.get("bugs") or [])
        self.steps = int(saved.get("steps") or 0)
        self._seconds_before = float(saved.get("seconds") or 0)
        usage = saved.get("usage") or {}
        self.usage = Usage(
            model=usage.get("model") or "",
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_read_tokens=int(usage.get("cache_read_tokens") or 0),
            cache_write_tokens=int(usage.get("cache_write_tokens") or 0),
            cost_usd=float(usage.get("cost_usd") or 0),
            estimated_cost_usd=float(usage.get("estimated_cost_usd") or 0),
        )
        self._resumed = True


def _text(value) -> str:
    return str(value).strip()[:MAX_FIELD] if isinstance(value, str | int | float) else ""


def _clean(raw: dict, keys: tuple[str, ...]) -> dict:
    return {k: redact(_text(raw.get(k))) for k in keys if _text(raw.get(k))}


def rule_detail(check: str, rule: str, data: dict):
    """What the check reports for `rule` now, or None if it doesn't report it."""
    if check == "run_axe":
        return next((v for v in data.get("violations") or [] if v.get("rule_id") == rule), None)
    if check == "check_layout":
        if rule not in (data.get("problems") or []):
            return None
        key = {"overflow": "sticking_out", "small-targets": "small_targets"}.get(rule, "small_text")
        return {"rule": rule, "overflow_px": data.get("overflow_px"), "items": data.get(key)}
    if check == "check_meta":
        return next((p for p in data.get("problems") or [] if rule.lower() in p.lower()), None)
    return None


def _describe(action: Action) -> str:
    element = action.element or {}
    target = f' {element.get("role", "")} "{element.get("name", "")}"' if element else ""
    args = {k: v for k, v in action.args.items() if k not in ("ref", "selector")}
    shown = f" {args}" if args else ""
    return f"{action.tool}{target}{shown}".strip()
