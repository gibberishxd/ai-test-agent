"""What a replayed action changed: a compact page state before and after it, and their diff.

Replay used to show the judge one screenshot of the end state. That can show a wrong change,
but never that nothing happened ("Save changes does nothing" looks exactly like a page where
Save hasn't been clicked yet). So replay records two compact states, one just before the last
action and one after the page settles, plus what happened in between: requests, dialogs, new
tabs, console messages, and text that appeared only briefly (a toast). The diff says what
changed, with harmless changes (spinners, ticking clocks, polling) set aside, and whether
anything meaningful changed at all.

Privacy: password values are never read, storage and cookie values are kept only as short
fingerprints, and request URLs lose their query strings. The diff summary goes to a model.
"""

import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from PIL import Image, ImageDraw
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from worker.browser import wait_until_quiet

SETTLE_MS = 2000
MAX_LINES = 400
MAX_SEEN = 200
MAX_LISTED = 12  # per section of the summary
IMAGE_MAX_WIDTH = 1024  # each half of the before/after picture

# Resource types whose GET requests are page furniture, not a response to an action.
STATIC_TYPES = {"image", "stylesheet", "script", "font", "media", "manifest", "texttrack"}

SPINNER = re.compile(
    r"^(loading|saving|please wait|updating|processing|submitting|sending|refreshing)\b[\s.…]*$",
    re.IGNORECASE,
)
# Times, dates and relative times. A line that differs from another only here is a ticking
# clock, not a response.
TIME_PARTS = re.compile(
    r"\b\d{1,2}:\d{2}(:\d{2})?(\s?[ap]m)?\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
    r"|\b\d+\s+(second|minute|hour|day)s?\s+ago\b",
    re.IGNORECASE,
)
TIMESTAMP_WORDS = re.compile(r"\b(updated|synced|refreshed|last|as of|ago|now)\b", re.IGNORECASE)
TOTAL = re.compile(r"\b(total|subtotal|grand total|amount due|balance)\b.*\d", re.IGNORECASE)

# Reports that say an action had no effect. Matched on title + actual.
NO_EFFECT = re.compile(
    r"does ?n[o']?t do anything|does nothing|nothing happens|nothing changes|no effect"
    r"|no (visible )?(feedback|response|reaction|confirmation)"
    r"|(does not|doesn't|did not|didn't|fails to|failed to|won't|will not) "
    r"(save|update|apply|submit|work|respond|change|persist|react|increment|decrement|increase"
    r"|decrease|open|close|expand|collapse|toggle|load|navigate|add|remove|clear|reset|refresh"
    r"|trigger|do anything)"
    r"|not (saved|applied|submitted|persisted)"
    r"|unresponsive|no message and no error",
    re.IGNORECASE,
)

STATE_JS = """() => {
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const text = document.body ? document.body.innerText : '';
  const lines = text.split('\\n').map((s) => s.trim()).filter(Boolean);
  const labelOf = (el) => {
    if (el.labels && el.labels.length) return el.labels[0].innerText.trim();
    return el.getAttribute('aria-label') || el.name || el.id || el.placeholder || el.type;
  };
  const fields = {};
  for (const el of document.querySelectorAll('input, select, textarea')) {
    if (el.type === 'hidden' || !visible(el)) continue;
    const label = labelOf(el) || 'field';
    let key = label, n = 2;
    while (key in fields) key = label + ' #' + n++;
    let value;
    if (el.type === 'password') value = el.value ? '••••' : '';
    else if (el.type === 'checkbox' || el.type === 'radio') {
      value = el.checked ? 'checked' : 'unchecked';
    } else if (el.tagName === 'SELECT') {
      value = el.selectedOptions[0] ? el.selectedOptions[0].text : '';
    }
    else value = String(el.value || '');
    fields[key] = value.slice(0, 200);
  }
  const storage = {};
  const stores = [['localStorage', window.localStorage], ['sessionStorage', window.sessionStorage]];
  for (const [name, store] of stores) {
    try {
      for (let i = 0; i < store.length; i++) {
        const key = store.key(i);
        storage[name + '.' + key] = store.getItem(key);
      }
    } catch (e) { /* storage blocked */ }
  }
  const seen = window.__ataSeen || [];
  return { url: location.href, title: document.title, lines, fields, storage, seen };
}"""

# Starts collecting text that is added to the page from now on, so a toast that disappears
# before the "after" capture still counts.
WATCH_JS = """(limit) => {
  if (window.__ataObserver) window.__ataObserver.disconnect();
  window.__ataSeen = [];
  const push = (value) => {
    const text = (value || '').trim();
    if (text && text.length <= 200 && window.__ataSeen.length < limit) window.__ataSeen.push(text);
  };
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === 'characterData') push(m.target.textContent);
      for (const node of m.addedNodes) push(node.textContent);
    }
  });
  observer.observe(document, { subtree: true, childList: true, characterData: true });
  window.__ataObserver = observer;
}"""


@dataclass
class PageState:
    url: str
    title: str
    lines: list[str]
    fields: dict[str, str] = field(default_factory=dict)
    storage: dict[str, str] = field(default_factory=dict)  # key -> fingerprint, never the value
    totals: list[str] = field(default_factory=list)
    # What happened since the previous capture:
    requests: list[str] = field(default_factory=list)  # "POST /api/profile → 200"
    console: list[str] = field(default_factory=list)
    dialogs: list[str] = field(default_factory=list)
    popups: list[str] = field(default_factory=list)
    seen: list[str] = field(default_factory=list)  # text added to the page meanwhile


def _fingerprint(value: str | None) -> str:
    return hashlib.sha256((value or "").encode()).hexdigest()[:12]


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class StateRecorder:
    """Listens to one page from before it loads, and captures its state on request.

    Create it before `page.goto`, so requests and dialogs are seen from the start.
    """

    def __init__(self, page: Page):
        self.page = page
        self._requests: list[dict] = []
        self._console: list[str] = []
        self._dialogs: list[str] = []
        self._popups: list[str] = []
        self._marks = {"requests": 0, "console": 0, "dialogs": 0, "popups": 0}
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("console", self._on_console)
        page.on("dialog", self._on_dialog)
        page.on("popup", lambda popup: self._popups.append(_path(popup.url)))

    def _on_request(self, request) -> None:
        if request.method == "GET" and request.resource_type in STATIC_TYPES:
            return
        entry = {"method": request.method, "url": request.url, "status": None, "obj": request}
        self._requests.append(entry)

    def _on_response(self, response) -> None:
        for entry in reversed(self._requests):
            if entry["obj"] is response.request:
                entry["status"] = response.status
                return

    def _on_console(self, message) -> None:
        if message.type in ("error", "warning"):
            self._console.append(f"{message.type}: {message.text[:200]}")

    def _on_dialog(self, dialog) -> None:
        self._dialogs.append(f"{dialog.type}: {dialog.message[:200]}")
        try:
            dialog.dismiss()
        except PlaywrightError:
            pass

    def settle(self) -> None:
        """Wait until the network is quiet and the page has stopped redrawing."""
        from worker.verify import wait_until_drawn  # verify imports this module

        wait_until_quiet(self.page, SETTLE_MS)
        wait_until_drawn(self.page)

    def capture(self) -> PageState:
        """The page's state now, plus what happened since the previous capture."""
        raw = self.page.evaluate(STATE_JS)
        storage = {key: _fingerprint(value) for key, value in raw["storage"].items()}
        try:
            for cookie in self.page.context.cookies(raw["url"]):
                storage[f"cookie.{cookie['name']}"] = _fingerprint(cookie["value"])
        except PlaywrightError:
            pass
        lines = raw["lines"][:MAX_LINES]
        page_origin = _origin(raw["url"])
        state = PageState(
            url=raw["url"],
            title=raw["title"],
            lines=lines,
            fields=raw["fields"],
            storage=storage,
            totals=[line for line in lines if TOTAL.search(line)],
            requests=[_describe(e, page_origin) for e in self._since("requests", self._requests)],
            console=self._since("console", self._console),
            dialogs=self._since("dialogs", self._dialogs),
            popups=self._since("popups", self._popups),
            seen=raw["seen"],
        )
        try:
            self.page.evaluate(WATCH_JS, MAX_SEEN)
        except PlaywrightError:
            pass
        return state

    def _since(self, name: str, items: list) -> list:
        start, self._marks[name] = self._marks[name], len(items)
        return list(items[start:])


def _path(url: str) -> str:
    """A URL without its query string or fragment (they can carry tokens)."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.netloc else url


def _describe(entry: dict, page_origin: str) -> str:
    parts = urlsplit(entry["url"])
    where = parts.path or "/"
    if _origin(entry["url"]) != page_origin:
        where = f"{parts.netloc}{where}"
    status = f" → {entry['status']}" if entry["status"] is not None else ""
    return f"{entry['method']} {where}{status}"


def is_noise_line(line: str) -> bool:
    """A line that says nothing about the action: a spinner, or a clock / "updated" stamp."""
    text = line.strip()
    if SPINNER.match(text) or text.lower() == "just now":
        return True
    return bool(TIME_PARTS.search(text) and TIMESTAMP_WORDS.search(text))


def _without_time(line: str) -> str:
    return TIME_PARTS.sub("<time>", line)


def claims_no_effect(title: str, actual: str | None) -> bool:
    """Does this report say that an action had no effect (as opposed to a wrong effect)?"""
    return bool(NO_EFFECT.search(f"{title}\n{actual or ''}"))


@dataclass
class StateDiff:
    url_change: tuple[str, str] | None
    added: list[str]
    removed: list[str]
    transient: list[str]
    fields: list[str]
    storage: list[str]
    requests: list[str]
    dialogs: list[str]
    popups: list[str]
    console: list[str]
    totals: tuple[list[str], list[str]]
    ignored: list[str]

    @property
    def meaningful(self) -> bool:
        """Did the page respond in a way a user (or the app's data) would notice?

        Console messages don't count: users don't see them. They're listed as evidence.
        """
        return bool(
            self.url_change
            or self.added
            or self.removed
            or self.transient
            or self.fields
            or self.storage
            or self.requests
            or self.dialogs
            or self.popups
        )

    def summary(self) -> str:
        out: list[str] = []
        if self.url_change:
            out.append(f"URL changed: {_path(self.url_change[0])} → {_path(self.url_change[1])}")
        sections = [
            ("Text that appeared", self.added),
            ("Text that disappeared", self.removed),
            ("Text that appeared briefly and went away", self.transient),
            ("Form fields that changed", self.fields),
            ("Stored data (local/session storage, cookies)", self.storage),
            ("Requests sent", self.requests),
            ("Dialogs shown", self.dialogs),
            ("New tabs opened", self.popups),
            ("Console errors and warnings (not visible to users)", self.console),
        ]
        for name, items in sections:
            if items:
                shown = [f"- {item}" for item in items[:MAX_LISTED]]
                if len(items) > MAX_LISTED:
                    shown.append(f"- … and {len(items) - MAX_LISTED} more")
                out.append(f"{name}:\n" + "\n".join(shown))
        before, after = self.totals
        if before and before == after:
            out.append("Totals unchanged: " + "; ".join(after))
        elif before or after:
            out.append(f"Totals: {'; '.join(before) or '(none)'} → {'; '.join(after) or '(none)'}")
        if self.ignored:
            out.append("Ignored as harmless: " + "; ".join(self.ignored[:MAX_LISTED]))
        if not self.meaningful:
            out.insert(
                0,
                "No change: no new or removed text, no field, storage or URL change, "
                "no request, no dialog and no new tab after the action.",
            )
        return "\n".join(out)

    def to_dict(self) -> dict:
        return {"meaningful": self.meaningful, "summary": self.summary()}


def diff_states(before: PageState, after: PageState, typed: str | None = None) -> StateDiff:
    """What changed from `before` to `after` (`after` carries what happened in between).

    `typed`: the text the action typed, if it was a typing action. The field holding exactly
    that text is the action itself, not the page's response to it.
    """
    ignored: list[str] = []
    gone = Counter(before.lines) - Counter(after.lines)
    new = Counter(after.lines) - Counter(before.lines)
    removed, added = list(gone.elements()), list(new.elements())

    # A line whose only change is a time or date is a ticking clock. Totals never pair this way.
    for line in list(removed):
        twin = next(
            (a for a in added if _without_time(a) == _without_time(line) and not TOTAL.search(a)),
            None,
        )
        if twin is not None and not TOTAL.search(line):
            removed.remove(line)
            added.remove(twin)
            ignored.append(f"time changed: {twin}")
    for lines in (added, removed):
        for line in list(lines):
            if is_noise_line(line):
                lines.remove(line)
                ignored.append(line)

    on_page = set(before.lines) | set(after.lines)
    transient = []
    for text in after.seen:
        for line in (s.strip() for s in text.splitlines()):
            if not line or line in on_page or line in transient:
                continue
            if any(line in visible for visible in on_page):  # part of a line still shown
                continue
            if is_noise_line(line):
                ignored.append(line) if line not in ignored else None
                continue
            transient.append(line)

    fields = []
    for name in sorted(set(before.fields) | set(after.fields)):
        old, now = before.fields.get(name), after.fields.get(name)
        if old == now or (typed is not None and now == typed):
            continue
        fields.append(f'{name}: "{old if old is not None else "(absent)"}" → "{now or ""}"')

    storage = []
    for key in sorted(set(before.storage) | set(after.storage)):
        if key not in before.storage:
            storage.append(f"{key} added")
        elif key not in after.storage:
            storage.append(f"{key} removed")
        elif before.storage[key] != after.storage[key]:
            storage.append(f"{key} changed")

    requests = _requests_that_count(before.requests, after.requests, ignored)
    url_change = (before.url, after.url) if before.url != after.url else None
    return StateDiff(
        url_change=url_change,
        added=added,
        removed=removed,
        transient=transient,
        fields=fields,
        storage=storage,
        requests=requests,
        dialogs=list(after.dialogs),
        popups=list(after.popups),
        console=list(after.console),
        totals=(before.totals, after.totals),
        ignored=ignored,
    )


def _requests_that_count(earlier: list[str], during: list[str], ignored: list[str]) -> list[str]:
    """Requests sent after the action, minus polling.

    A GET that the page also sent before the action, or sent more than once during the
    settle window, is the page polling on its own. Anything other than GET always counts.
    """

    def key(request: str) -> str:
        return request.split(" → ")[0]

    before_keys = {key(r) for r in earlier}
    repeats = Counter(key(r) for r in during)
    counted, seen = [], set()
    for request in during:
        k = key(request)
        if k.startswith("GET ") and (k in before_keys or repeats[k] > 1):
            if k not in seen:
                ignored.append(f"polling: {k}")
                seen.add(k)
            continue
        counted.append(request)
    return counted


def side_by_side(before: bytes, after: bytes) -> bytes:
    """One PNG: the page before the action on the left, after it on the right, labelled."""
    left, right = (_scaled(Image.open(io.BytesIO(png)).convert("RGB")) for png in (before, after))
    label, gap = 24, 12
    width = left.width + gap + right.width
    height = label + max(left.height, right.height)
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(left, (0, label))
    canvas.paste(right, (left.width + gap, label))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([left.width, 0, left.width + gap - 1, height], fill=(120, 120, 120))
    draw.text((6, 6), "BEFORE the action", fill="black")
    draw.text((left.width + gap + 6, 6), "AFTER the action", fill="black")
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def _scaled(image: Image.Image) -> Image.Image:
    if image.width <= IMAGE_MAX_WIDTH:
        return image
    height = round(image.height * IMAGE_MAX_WIDTH / image.width)
    return image.resize((IMAGE_MAX_WIDTH, height))
