from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from worker.report import (
    A11yViolation,
    ConsoleError,
    FailedRequest,
    PageResult,
    Report,
    load_report,
    write_report,
)


def make_report() -> Report:
    """A small report with one of everything, so the round-trip test covers every model."""
    page = PageResult(
        url="http://localhost:5173/",
        status=200,
        title="Demo shop",
        found_on=None,
        screenshot="screenshots/0001.png",
        console_errors=[ConsoleError(kind="pageerror", text="boom", location=None)],
        failed_requests=[
            FailedRequest(
                url="http://localhost:5173/logo.png",
                method="GET",
                resource_type="image",
                status=404,
                failure=None,
            )
        ],
        a11y_violations=[
            A11yViolation(
                rule_id="image-alt",
                impact="critical",
                help="Images must have alternative text",
                help_url="https://dequeuniversity.com/rules/axe/image-alt",
                targets=["img.logo"],
            )
        ],
    )
    return Report(
        target="http://localhost:5173",
        started_at=datetime(2026, 11, 9, 10, 0, tzinfo=UTC),
        finished_at=datetime(2026, 11, 9, 10, 1, tzinfo=UTC),
        pages=[page],
    )


def test_report_round_trips_through_json(tmp_path):
    report = make_report()
    path = tmp_path / "report.json"

    write_report(report, path)

    assert load_report(path) == report


def test_new_report_has_schema_version_1():
    assert make_report().schema_version == 1


def test_lists_default_to_empty():
    page = PageResult(url="http://localhost:5173/", status=200)
    assert page.console_errors == []
    assert page.failed_requests == []
    assert page.a11y_violations == []


def test_rejects_unknown_impact_level():
    with pytest.raises(ValidationError):
        A11yViolation(rule_id="x", impact="catastrophic", help="", help_url="", targets=[])
