"""Safety rule 6.6: secrets never appear in logs, reports or stored text.

`redact` masks API keys and auth headers in any text the worker stores or logs: console
messages and page text from the target site, error messages, LLM output. `RedactingFilter`
applies it to every log line.
"""

import logging
import re

MASK = "[REDACTED]"

PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),  # Anthropic keys
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # other "sk-" style API keys
    re.compile(r"(?i)(authorization:\s*(?:bearer|basic)\s+)[^\s\"']+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]{20,}=*"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*[=:]\s*)[^\s&\"',;]{6,}"),
]


def redact(text: str, known_secrets: tuple[str, ...] = ()) -> str:
    """Mask secrets in `text`. `known_secrets` are exact values (e.g. our own API key)."""
    for secret in known_secrets:
        if secret:
            text = text.replace(secret, MASK)
    for pattern in PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + MASK, text)
    return text


class RedactingFilter(logging.Filter):
    """A logging filter that redacts every record before it's written."""

    def __init__(self, known_secrets: tuple[str, ...] = ()):
        super().__init__()
        self.known_secrets = known_secrets

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage(), self.known_secrets)
        record.args = ()
        return True
