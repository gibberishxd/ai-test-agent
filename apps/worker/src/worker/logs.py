"""Structured worker logs (run 4, J6).

LOG_FORMAT=json writes one JSON object per line (time, level, logger, message, and the run and
workspace being processed), so a log collector can filter by run. The ids come from context
variables set while a run is processed (`log_context`), so no log call has to pass them.
Secrets are still redacted by the RedactingFilter on the handler.
"""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

_context: ContextVar[dict[str, str] | None] = ContextVar("log_context", default=None)


@contextmanager
def log_context(**ids: str) -> Iterator[None]:
    token = _context.set({**(_context.get() or {}), **{k: str(v) for k, v in ids.items()}})
    try:
        yield
    finally:
        _context.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            **(_context.get() or {}),
        }
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line)
