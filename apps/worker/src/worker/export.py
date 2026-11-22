"""A run's findings as one JSON file, for analysis outside the app.

    uv run worker export RUN_ID --out results/run.json [--data-dir DIR]

Per run: id, target, model, viewport, cost and duration. Per finding: title, description,
severity, the steps to reproduce, evidence split into console / network / accessibility, the
screenshot's path on disk, and whether replay verified it. Every finding is exported, dismissed
ones too, with its status, so nothing is hidden from the reader.
"""

import json
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from worker.db.models import Bug, Run, Step

SCHEMA = "run-export/1"
DEFAULT_VIEWPORT = "1280x800"  # a run without its own viewport starts on desktop

# Evidence keys of deterministic findings (findings.py), by kind.
CONSOLE_KEYS = ("console_errors",)
NETWORK_KEYS = ("failed_requests",)
A11Y_KEYS = ("a11y",)


def export_run(session: Session, run_id: str, data_dir: Path | None = None) -> dict:
    """The run and every finding as a JSON-ready dict. `data_dir`: where local storage keeps
    screenshots (screenshot keys are made absolute paths under it); None leaves keys as they are.
    Raises LookupError for an unknown run."""
    run = session.get(Run, uuid.UUID(run_id))
    if run is None:
        raise LookupError(f"no run {run_id}")
    steps = {s.index: s for s in session.query(Step).filter_by(run_id=run.id)}
    bugs = session.query(Bug).filter_by(run_id=run.id).order_by(Bug.created_at).all()
    duration = (
        (run.finished_at - run.started_at).total_seconds()
        if run.started_at and run.finished_at
        else None
    )
    return {
        "schema": SCHEMA,
        "run_id": str(run.id),
        "target_url": run.target_url,
        "mode": run.mode,
        "status": run.status,
        "error": run.error,
        # Why the agent stopped ("finished", a budget, "the model call failed: ...").
        "stop_reason": (run.summary or {}).get("stop_reason"),
        "agent_summary": (run.summary or {}).get("agent_summary"),
        "provider": run.provider,
        "model": run.model,
        "viewport": run.viewport or DEFAULT_VIEWPORT,
        "cost_usd": run.cost_usd,
        "estimated_cost_usd": run.estimated_cost_usd,
        "duration_s": duration,
        "steps": run.step_count,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "findings": [_finding(bug, steps, data_dir) for bug in bugs],
    }


def find_run_id(session: Session, prefix: str) -> str:
    """The full id of the one run whose id starts with `prefix`; LookupError otherwise."""
    from sqlalchemy import String, cast

    ids = session.query(Run.id).filter(cast(Run.id, String).like(f"{prefix}%")).limit(2).all()
    if len(ids) != 1:
        raise LookupError(f"{'no' if not ids else 'more than one'} run starts with {prefix!r}")
    return str(ids[0][0])


def write_export(session: Session, run_id: str, out: Path, data_dir: Path | None = None) -> Path:
    data = export_run(session, run_id, data_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _finding(bug: Bug, steps: dict[int, Step], data_dir: Path | None) -> dict:
    evidence = bug.evidence or {}
    events = [e for i in bug.step_indexes or [] if i in steps for e in steps[i].events or []]
    return {
        "id": str(bug.id),
        "title": bug.title,
        "description": description_of(bug.expected, bug.actual),
        "severity": bug.severity,
        "category": bug.category,
        "source": bug.source,
        "page_url": bug.page_url,
        "status": bug.status,
        "dismiss_reason": bug.dismiss_reason,
        "duplicate_of": str(bug.duplicate_of_id) if bug.duplicate_of_id else None,
        "replay_verified": replay_verified(bug.status, evidence),
        "steps": list(bug.repro_steps or []),
        "evidence": evidence_of(evidence, events),
        "screenshot": _path(screenshot_of(bug, steps), data_dir),
    }


def description_of(expected: str | None, actual: str | None) -> str:
    parts = [f"Expected: {expected}" if expected else "", f"Actual: {actual}" if actual else ""]
    return "\n".join(p for p in parts if p)


def replay_verified(status: str, evidence: dict) -> bool:
    """Replay ran and the bug showed again. Deterministic findings are confirmed by their hard
    evidence without a replay, so they are not "replay-verified"."""
    return status == "confirmed" and bool(evidence.get("replay"))


def evidence_of(evidence: dict, step_events: list[dict]) -> dict:
    """Console, network and accessibility evidence: a deterministic finding's records, plus the
    console errors and failed requests seen on the steps that led to the report.

    Step events are stored as {"type", "text"}: an agent step's are all type "event" with the
    kind in the text ("console error: ...", "network: ..."); a crawl step's type is the kind
    (execute.page_events)."""
    console = [x for k in CONSOLE_KEYS for x in evidence.get(k, [])]
    network = [x for k in NETWORK_KEYS for x in evidence.get(k, [])]
    a11y = [x for k in A11Y_KEYS for x in evidence.get(k, [])]
    for event in step_events:
        kind = _event_kind(event)
        text = str(event.get("text", "")) if isinstance(event, dict) else str(event)
        if kind == "console":
            console.append(text)
        elif kind == "network":
            network.append(text)
        elif kind == "a11y":
            a11y.append(text)
    known = CONSOLE_KEYS + NETWORK_KEYS + A11Y_KEYS
    other = {k: v for k, v in evidence.items() if k not in known}
    return {"console": console, "network": network, "accessibility": a11y, "other": other}


def _event_kind(event) -> str | None:
    if not isinstance(event, dict):
        return None
    kind, text = event.get("type"), str(event.get("text", ""))
    if kind == "event":  # an agent step: the kind is in the text
        if text.startswith(("console error:", "pageerror error:")):
            return "console"
        return "network" if text.startswith("network:") else None
    if kind in ("console", "pageerror"):
        return "console"
    return kind if kind in ("network", "a11y") else None


def screenshot_of(bug: Bug, steps: dict[int, Step]) -> str | None:
    """The finding's own screenshot, else the one of the step it was reported at, else of the
    last step that led to it."""
    if bug.screenshot:
        return bug.screenshot
    reported_at = (bug.evidence or {}).get("reported_at")
    candidates = [reported_at, *reversed(bug.step_indexes or [])]
    for index in candidates:
        if index in steps and steps[index].screenshot:
            return steps[index].screenshot
    return None


def _path(key: str | None, data_dir: Path | None) -> str | None:
    if key is None or data_dir is None:
        return key
    return str(data_dir / key)
