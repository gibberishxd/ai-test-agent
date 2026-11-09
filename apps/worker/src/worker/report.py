"""The checker's output format.

These Pydantic models are the contract between the worker (which writes report.json) and the
web app (which reads it later). Pydantic checks types at runtime and handles JSON conversion.
Bump `schema_version` whenever a field changes in a way that would break an existing reader.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ConsoleError(BaseModel):
    """A console.error() call ("console") or an uncaught JavaScript exception ("pageerror")."""

    kind: Literal["console", "pageerror"]
    text: str
    location: str | None = None  # "file.js:12:5" when the browser provides it


class FailedRequest(BaseModel):
    """A request that failed at the network level, or got an HTTP 4xx/5xx response."""

    url: str
    method: str
    resource_type: str  # document, script, image, fetch, ...
    status: int | None = None  # None: no response at all (network failure)
    failure: str | None = None  # e.g. "net::ERR_CONNECTION_REFUSED"


class A11yViolation(BaseModel):
    """One axe-core rule that failed on a page."""

    rule_id: str  # e.g. "color-contrast"
    impact: Literal["minor", "moderate", "serious", "critical"] | None
    help: str
    help_url: str
    targets: list[str]  # CSS selectors of the offending elements


class PageResult(BaseModel):
    """Everything the checker found on one visited page."""

    url: str
    status: int | None  # HTTP status of the page itself; None if navigation failed
    title: str | None = None
    found_on: str | None = None  # the page that linked here; None for the start URL
    screenshot: str | None = None  # path relative to the report folder
    console_errors: list[ConsoleError] = Field(default_factory=list)
    failed_requests: list[FailedRequest] = Field(default_factory=list)
    a11y_violations: list[A11yViolation] = Field(default_factory=list)
    error: str | None = None  # set when navigation itself failed or timed out
    load_ms: int | None = None  # time until the "load" event
    soft_404: bool = False  # status 200, but the page says "not found" (single-page apps)
    blocked_requests: list[str] = Field(default_factory=list)  # refused by the safety guard


class BrokenLink(BaseModel):
    """A same-origin link whose target returned 4xx/5xx or could not be loaded."""

    url: str
    status: int | None
    found_on: list[str]  # every page that links to it


class BugReport(BaseModel):
    """One bug, as stored in the `bugs` table and shown on the report page.

    The web app has a TypeScript copy of this shape; tests fail if the two drift apart.
    """

    title: str
    severity: Literal["critical", "high", "medium", "low"]
    category: str  # console-error, network, broken-link, accessibility, performance, visual, ...
    page_url: str
    expected: str | None = None
    actual: str | None = None
    repro_steps: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)  # console errors, failed requests, axe results
    reasoning: str | None = None  # why the agent thinks it's a bug (agent findings)
    screenshot: str | None = None  # storage reference
    step_indexes: list[int] = Field(default_factory=list)  # steps that led here (for replay)
    source: Literal["deterministic", "agent"]
    status: Literal["candidate", "confirmed", "dismissed"] = "candidate"
    dismiss_reason: str | None = None


class Report(BaseModel):
    """The full result of one checker run."""

    schema_version: Literal[1] = 1
    target: str
    started_at: datetime
    finished_at: datetime
    pages: list[PageResult] = Field(default_factory=list)
    broken_links: list[BrokenLink] = Field(default_factory=list)
    bugs: list[BugReport] = Field(default_factory=list)


def write_report(report: Report, path: Path) -> None:
    """Save the report as pretty-printed JSON, creating parent folders if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def load_report(path: Path) -> Report:
    """Read a report back, validating it against the models."""
    return Report.model_validate_json(path.read_text(encoding="utf-8"))
