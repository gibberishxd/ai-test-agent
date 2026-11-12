"""A finding's fingerprint: how the same bug is recognised in later runs of a target (run 4, J4).

fingerprint = first 16 hex characters of SHA-256 over "route | category | key":
- route: the page's path with ids replaced by ":id" (numbers, UUIDs, long hex), no query string
  and no trailing slash, so /products/42 and /products/7 are the same page template;
- category: console-error, network, accessibility, functional, ... (two kinds of problem on one
  page stay apart);
- key: what is wrong, normalised so run-to-run noise doesn't change it:
  network → method + normalised request path + status; console-error → the message without
  numbers, hashes or file positions; accessibility → the axe rule; broken-link → the normalised
  link; agent reports → the element acted on (role + name), else the title's words (lowercase,
  no numbers or stopwords, sorted).

The same message on two different pages is two bugs (the route differs); a reworded agent report
on the same element is one bug (the key is the element, not the wording).
"""

import hashlib
import re
from urllib.parse import urlsplit

from worker.report import BugReport

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
HEXID = re.compile(r"^[0-9a-f]{16,}$", re.I)
NUMBERISH = re.compile(r"\b[0-9a-f]*\d[0-9a-f]*\b", re.I)  # 42, 4f3a2b, 12:5 parts
STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "to",
    "on",
    "in",
    "is",
    "it",
    "and",
    "or",
    "for",
    "with",
    "when",
    "after",
    "instead",
    "does",
    "doesn",
    "not",
    "has",
    "no",
    "s",
    "t",
}


def normalize_route(url: str) -> str:
    segments = [s for s in urlsplit(url).path.split("/") if s]
    normal = [
        ":id" if s.isdigit() or UUID.match(s) or HEXID.match(s) else s.lower() for s in segments
    ]
    return "/" + "/".join(normal)


def normalize_message(text: str) -> str:
    """Lowercase words of a message, with numbers, hashes and positions taken out."""
    text = NUMBERISH.sub("#", text.lower())
    return re.sub(r"[^a-z#]+", " ", text).strip()


def _title_words(title: str) -> str:
    words = re.findall(r"[a-z]+", re.sub(r"\$?\d[\d.,]*", " ", title.lower()))
    return " ".join(sorted({w for w in words if w not in STOPWORDS}))


def _key(bug: BugReport) -> str:
    evidence = bug.evidence or {}
    if bug.category == "network" and evidence.get("failed_requests"):
        request = evidence["failed_requests"][0]
        status = request.get("status") or request.get("failure") or ""
        return f"{request.get('method', '')} {normalize_route(request.get('url', ''))} {status}"
    if bug.category == "console-error" and evidence.get("console_errors"):
        return normalize_message(evidence["console_errors"][0].get("text", ""))
    if bug.category == "accessibility" and evidence.get("a11y"):
        return evidence["a11y"][0].get("rule_id", "")
    if bug.category == "broken-link" and evidence.get("link"):
        return normalize_route(evidence["link"])
    element = evidence.get("element")
    if isinstance(element, dict) and element.get("name"):
        return f"{element.get('role', '')}:{element['name'].strip().lower()}"
    return _title_words(bug.title)


def fingerprint(bug: BugReport) -> str:
    """Works on a BugReport or a stored Bug row (same attribute names)."""
    raw = f"{normalize_route(bug.page_url)}|{bug.category}|{_key(bug)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
