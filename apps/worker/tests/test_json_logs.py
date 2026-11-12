"""Structured logs (run 4, J6): LOG_FORMAT=json writes one JSON object per line, with the run and
workspace being processed, and still redacts secrets."""

import json
import logging

from worker.logs import JsonFormatter, log_context


def record(message: str) -> logging.LogRecord:
    return logging.LogRecord("worker.runner", logging.INFO, __file__, 1, message, (), None)


def test_a_line_is_json_with_the_run_and_workspace_in_context():
    with log_context(run_id="r1", workspace_id="w1"):
        line = json.loads(JsonFormatter().format(record("claimed run")))
    assert (
        line["level"] == "info"
        and line["message"] == "claimed run"
        and line["logger"] == "worker.runner"
    )
    assert (line["run_id"], line["workspace_id"]) == ("r1", "w1")
    assert "time" in line
    outside = json.loads(JsonFormatter().format(record("idle")))
    assert "run_id" not in outside


def test_exceptions_are_one_field_not_many_lines():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        r = logging.LogRecord("w", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    line = json.loads(JsonFormatter().format(r))
    assert "ValueError: boom" in line["exception"]
