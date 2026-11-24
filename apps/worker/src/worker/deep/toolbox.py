"""Deep mode's toolbox: the browser tools the model calls, behind the worker's safety rules.

The model only asks; the toolbox decides. Before an action it applies the same rules as the
current loop: look-only passive mode (rule 6.2), the deny list for destructive controls, no
card numbers outside the demo shop, no navigation off the target (6.1), and a return to the site
when a button or script leaves it. The browser's traffic still goes through the guard proxy.

Measuring with JavaScript runs in a measure-only window: while a snippet runs, any request that
sends data (anything but GET, HEAD, OPTIONS) is blocked, and the model is told if the snippet
changed the DOM. Reading the page source and scripts returns only responses the browser already
loaded, so nothing new is fetched.

Every call returns what the model reads (text, and an image for a screenshot) and an `Action`:
what the harness stores as a step. Actions that change the page record what replay needs to
repeat them in a fresh browser (the element's role, name and CSS path, the URL, the viewport).

Page content is untrusted: it goes to the model inside <page_content> tags, defused so the page
can't close them, and passes through secret redaction first.
"""

import io
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page

from worker.agent.loop import text_changes
from worker.agent.observe import CONTEXT_JS, CSS_PATH_JS, Element, fence, read_page
from worker.agent.policy import card_number_reason, deny_reason
from worker.browser import from_extension, parse_viewport, run_axe, wait_until_quiet
from worker.keyboard_probe import opened_by, probe, snapshot
from worker.layout import check_layout
from worker.meta import check_meta
from worker.safety.actions import check_mode
from worker.safety.network import NetworkGuard
from worker.safety.secrets import redact
from worker.urls import is_same_site

ACTION_TIMEOUT_MS = 5000
NAVIGATION_TIMEOUT_MS = 15_000
SETTLE_MS = 2000
SCROLL_PX = 700
MAX_TEXT = 8000  # characters of page text, source or script per call (the rest by offset)
MAX_TREE = 6000  # characters of the accessibility tree in a snapshot
MAX_EVENTS = 60  # console or network lines per call
MAX_FULL_PAGE_HEIGHT = 4000  # px: taller full-page screenshots are cut (and the model told)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
OFF_SITE = "safe mode: this leads to another site ({host}); testing stays on the target site"

# Tools whose effect replay repeats, in order, to rebuild the state a bug was found in.
REPLAYED_TOOLS = frozenset(
    {
        "navigate",
        "click",
        "type",
        "select",
        "press_key",
        "hover",
        "scroll",
        "set_viewport",
        "go_back",
    }
)
TARGETED_TOOLS = {"click", "type", "select", "press_key", "hover", "keyboard_probe"}
# Keys that activate the focused control, so the deny list applies to them like to a click.
ACTIVATING_KEYS = {"enter", "space", " "}

# What the deny list needs to know about an element found by a CSS selector (a ref already
# carries it from the snapshot). Roles follow ARIA's implicit roles, as in observe.py.
DESCRIBE_JS = r"""(el) => {
  const contextOf = /*CONTEXT*/;
  const cssPathOf = /*CSS_PATH*/;
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute('type') || '').toLowerCase();
  const implicit = { a: 'link', button: 'button', select: 'combobox', textarea: 'textbox',
                     summary: 'button' };
  const inputRole = { checkbox: 'checkbox', radio: 'radio', submit: 'button', button: 'button',
                      reset: 'button', range: 'slider', search: 'searchbox', number: 'spinbutton' };
  const role = el.getAttribute('role') || implicit[tag]
    || (tag === 'input' ? (inputRole[type] || 'textbox') : tag);
  const labels = el.labels ? Array.from(el.labels).map(l => l.innerText).join(' ') : '';
  const buttonValue = tag === 'input' && ['submit', 'button'].includes(type) ? el.value : '';
  const name = (el.getAttribute('aria-label') || labels || el.innerText || buttonValue
    || el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('alt')
    || '').trim().replace(/\s+/g, ' ').slice(0, 80);
  return {
    role, name, tag,
    href: tag === 'a' ? el.href : null,
    aria_label: el.getAttribute('aria-label'),
    input_type: tag === 'button' ? (el.getAttribute('type') || (el.form ? 'submit' : 'button'))
      : (tag === 'input' ? (type || 'text') : null),
    form_action: el.form ? el.form.action : null,
    value: tag === 'input' && ['submit', 'button', 'reset'].includes(type) ? el.value : null,
    context: contextOf(el),
    css: cssPathOf(el),
  };
}""".replace("/*CONTEXT*/", CONTEXT_JS).replace("/*CSS_PATH*/", CSS_PATH_JS)

# The measuring wrapper: run the model's snippet as an async function body, watch the DOM for
# changes (ignoring the refs our snapshot sets), and return a JSON-safe value.
MEASURE_JS = """async () => {
  const changes = [];
  const observer = new MutationObserver((list) => {
    for (const r of list) {
      if (!(r.type === 'attributes' && r.attributeName === 'data-agent-id')) changes.push(r);
    }
  });
  observer.observe(document.documentElement,
    { subtree: true, childList: true, attributes: true, characterData: true });
  let value = null, error = null;
  try {
    value = await (async () => {
/*SNIPPET*/
    })();
  } catch (e) {
    error = String((e && e.message) ? `${e.name}: ${e.message}` : e);
  }
  await new Promise((resolve) => setTimeout(resolve, 50));
  observer.disconnect();
  let safe;
  try { safe = JSON.parse(JSON.stringify(value === undefined ? null : value)); }
  catch (e) { safe = String(value); }
  return { value: safe, error, mutations: changes.length };
}"""


class ToolError(Exception):
    """The call can't run as asked (bad arguments, a stale ref): the model is told why."""


@dataclass(frozen=True)
class ToolboxConfig:
    target_url: str
    mode: str = "interactive"
    is_demo_target: bool = False
    signed_in: bool = False
    screenshot_max_width: int = 1280
    screenshot_quality: int = 75
    scrub: Callable[[str], str] = lambda text: text  # removes the test account's secrets


@dataclass
class Action:
    """One tool call, as the harness stores it (a step of the run)."""

    tool: str
    args: dict
    url: str  # the page it was called on
    viewport: str  # "WIDTHxHEIGHT" when it was called
    element: dict | None = None  # role, name, css... of the element acted on, for replay
    result: str = ""
    blocked: bool = False
    block_reason: str | None = None
    image: bytes | None = None  # the screenshot it returned, kept as evidence

    @property
    def replayable(self) -> bool:
        """Does repeating this step help rebuild the state? Only actions that ran."""
        return (
            self.tool in REPLAYED_TOOLS and not self.blocked and not self.result.startswith("error")
        )


@dataclass
class ToolResult:
    text: str
    image: bytes | None = None  # JPEG, for a screenshot
    is_error: bool = False
    action: Action | None = None
    data: dict | None = None  # the machine-readable result of a measurement
    step: int | None = None  # the run's step number, set by the harness

    def data_text(self) -> str:
        return json.dumps(self.data)


@dataclass
class _Request:
    seq: int
    method: str
    url: str
    kind: str
    started: float
    status: int | None = None
    failure: str | None = None
    ms: int | None = None


@dataclass
class _Logs:
    """Console and network events, each numbered (a "mark") so the model can ask for what
    happened since a point."""

    seq: int = 0
    console: list[tuple[int, str]] = field(default_factory=list)
    requests: list[_Request] = field(default_factory=list)

    def next(self) -> int:
        self.seq += 1
        return self.seq


class Toolbox:
    def __init__(self, page: Page, guard: NetworkGuard, config: ToolboxConfig):
        self.page = page
        self.guard = guard
        self.config = config
        self.elements: list[Element] = []  # from the latest snapshot; refs point into it
        self._logs = _Logs()
        self._by_request: dict[int, _Request] = {}
        self._document = None  # the main frame's latest document response
        self._scripts: dict[str, object] = {}  # url → response, for the current document
        self._measuring = False
        self._blocked_requests: list[str] = []
        self._image_cache: dict[str, str | None] = {}
        self._last_site_url = config.target_url
        self._handlers = {
            "navigate": self._navigate,
            "click": self._click,
            "type": self._type,
            "select": self._select,
            "press_key": self._press_key,
            "hover": self._hover,
            "scroll": self._scroll,
            "set_viewport": self._set_viewport,
            "go_back": self._go_back,
            "screenshot": self._screenshot,
            "snapshot": self._snapshot,
            "visible_text": self._visible_text,
            "evaluate_js": self._evaluate_js,
            "page_source": self._page_source,
            "read_script": self._read_script,
            "console": self._console,
            "network": self._network,
            "run_axe": self._run_axe,
            "check_layout": self._check_layout,
            "check_meta": self._check_meta,
            "keyboard_probe": self._keyboard_probe,
        }

    @property
    def mark(self) -> int:
        """The latest event number: pass it as `since` later to see only what came after."""
        return self._logs.seq

    @property
    def viewport(self) -> str:
        size = self.page.viewport_size or {"width": 0, "height": 0}
        return f"{size['width']}x{size['height']}"

    def start(self) -> None:
        """Listen to the page and open the target."""
        self.page.on("console", self._on_console)
        self.page.on("pageerror", self._on_page_error)
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)
        self.page.on("requestfailed", self._on_request_failed)
        self.page.route("**/*", self._route)
        self.page.goto(self.config.target_url, timeout=NAVIGATION_TIMEOUT_MS)
        wait_until_quiet(self.page, SETTLE_MS)

    # --- the one entry point -------------------------------------------------------------------

    def call(self, name: str, args: dict) -> ToolResult:
        """Run one tool call. Never raises for the model's mistakes: they come back as errors."""
        args = dict(args or {})
        action = Action(tool=name, args=args, url=self.page.url, viewport=self.viewport)
        handler = self._handlers.get(name)
        if handler is None:
            action.result = f"error: there is no tool {name!r}"
            return ToolResult(self._with_mark(action.result), is_error=True, action=action)
        try:
            result = handler(args, action)
        except ToolError as error:
            action.result = f"error: {error}"
            return ToolResult(self._with_mark(action.result), is_error=True, action=action)
        except PlaywrightError as error:
            action.result = f"error: {_first_line(error)}"
            return ToolResult(self._with_mark(action.result), is_error=True, action=action)
        if action.blocked:
            result.is_error = True
        result.action = action
        action.result = action.result or _first_line_of(result.text)
        action.image = result.image
        result.text = self._with_mark(result.text)
        return result

    def _with_mark(self, text: str) -> str:
        return f"{text}\n(mark {self.mark})"

    # --- acting ----------------------------------------------------------------------------

    def _navigate(self, args: dict, action: Action) -> ToolResult:
        url = urljoin(self.page.url, _text(args, "url"))
        reason = self.guard.check_navigation(url)
        if reason:
            return self._blocked(action, reason)
        return self._act(action, lambda: self.page.goto(url, timeout=NAVIGATION_TIMEOUT_MS))

    def _click(self, args: dict, action: Action) -> ToolResult:
        target, element = self._target(args, action)
        reason = self._activation_reason("click", element)
        if reason:
            return self._blocked(action, reason)
        return self._act(action, lambda: target.click(timeout=ACTION_TIMEOUT_MS))

    def _type(self, args: dict, action: Action) -> ToolResult:
        target, element = self._target(args, action)
        text = _text(args, "text")
        reason = check_mode(self.config.mode, "type", element.info()) or card_number_reason(
            text, self.config.is_demo_target
        )
        if reason:
            return self._blocked(action, reason)
        return self._act(action, lambda: target.fill(text, timeout=ACTION_TIMEOUT_MS))

    def _select(self, args: dict, action: Action) -> ToolResult:
        target, element = self._target(args, action)
        option = _text(args, "option")
        reason = check_mode(self.config.mode, "select", element.info())
        if reason:
            return self._blocked(action, reason)
        return self._act(
            action, lambda: target.select_option(label=option, timeout=ACTION_TIMEOUT_MS)
        )

    def _press_key(self, args: dict, action: Action) -> ToolResult:
        key = _text(args, "key")
        if "ref" in args or "selector" in args:
            target, element = self._target(args, action)
        else:
            target, element = self._focused()
        reason = check_mode(self.config.mode, "press_key", element.info() if element else None)
        if not reason and element is not None and key.lower() in ACTIVATING_KEYS:
            reason = self._activation_reason("click", element)
        if reason:
            return self._blocked(action, reason)
        if target is None:
            return self._act(action, lambda: self.page.keyboard.press(key))
        return self._act(action, lambda: target.press(key, timeout=ACTION_TIMEOUT_MS))

    def _hover(self, args: dict, action: Action) -> ToolResult:
        target, _ = self._target(args, action)
        return self._act(action, lambda: target.hover(timeout=ACTION_TIMEOUT_MS))

    def _scroll(self, args: dict, action: Action) -> ToolResult:
        direction = _text(args, "direction")
        if direction not in ("up", "down"):
            raise ToolError("direction must be up or down")
        pixels = _int(args, "pixels", SCROLL_PX)
        action.args = {"direction": direction, "pixels": pixels}
        distance = -pixels if direction == "up" else pixels
        return self._act(action, lambda: self.page.evaluate("y => window.scrollBy(0, y)", distance))

    def _set_viewport(self, args: dict, action: Action) -> ToolResult:
        width, height = _int(args, "width"), _int(args, "height")
        try:
            size = parse_viewport(f"{width}x{height}")
        except ValueError as error:
            raise ToolError(str(error)) from error
        action.args = size
        self.page.set_viewport_size(size)
        wait_until_quiet(self.page, SETTLE_MS)
        return ToolResult(f"ok: the window is now {width}×{height}")

    def _go_back(self, args: dict, action: Action) -> ToolResult:
        return self._act(action, lambda: self.page.go_back(timeout=NAVIGATION_TIMEOUT_MS))

    def _act(self, action: Action, run: Callable[[], object]) -> ToolResult:
        """Run an allowed action, let the page settle, and say what changed."""
        before_url, before_text = self.page.url, self._body_text()
        run()
        wait_until_quiet(self.page, SETTLE_MS)
        left = self._return_to_site()
        if left:
            action.blocked, action.block_reason = True, left
            return ToolResult(f"BLOCKED: {left}; you are back on {self.page.url}")
        self._last_site_url = self.page.url
        if self.page.url != before_url:
            return ToolResult(f"ok, now on {self.page.url}")
        changes = text_changes(before_text, self._body_text())
        return ToolResult(f"ok; new on the page: {self._safe(changes)}" if changes else "ok")

    def _blocked(self, action: Action, reason: str) -> ToolResult:
        action.blocked, action.block_reason = True, reason
        return ToolResult(f"BLOCKED: {reason}")

    def _activation_reason(self, action: str, element: Element) -> str | None:
        """Why activating this element (a click, Enter on it) isn't allowed, or None."""
        info = element.info()
        reason = check_mode(self.config.mode, action, info)
        if reason:
            return reason
        if info.href and self._off_site(info.href):
            return OFF_SITE.format(host=urlsplit(info.href).hostname)
        return deny_reason(
            info, is_demo_target=self.config.is_demo_target, signed_in=self.config.signed_in
        )

    def _off_site(self, url: str) -> bool:
        is_web = urlsplit(url).scheme.lower() in ("http", "https")
        return is_web and not is_same_site(url, self.config.target_url)

    def _return_to_site(self) -> str | None:
        """A button or a script can leave the site without saying so: go back if it did."""
        if not self._off_site(self.page.url):
            return None
        reason = OFF_SITE.format(host=urlsplit(self.page.url).hostname)
        try:
            self.page.goto(self._last_site_url, timeout=NAVIGATION_TIMEOUT_MS)
            wait_until_quiet(self.page, SETTLE_MS)
        except PlaywrightError:
            self.page.goto("about:blank")
        return reason

    # --- finding the element ---------------------------------------------------------------

    def _target(self, args: dict, action: Action) -> tuple[Locator, Element]:
        """The one element a call points at, by ref (preferred) or CSS selector."""
        if "ref" in args:
            ref = _int(args, "ref")
            element = next((e for e in self.elements if e.id == ref), None)
            locator = self.page.locator(element.locator) if element else None
            if element is None or locator.count() != 1:
                raise ToolError(f"no element [{args['ref']}]: take a new snapshot for fresh refs")
        elif "selector" in args:
            selector = _text(args, "selector")
            try:
                locator = self.page.locator(selector)
                found = locator.count()
            except PlaywrightError as error:
                raise ToolError(f"invalid selector: {_first_line(error)}") from error
            if found != 1:
                raise ToolError(f"the selector matches {found} elements; it must match exactly one")
            element = Element(id=0, **locator.evaluate(DESCRIBE_JS))
            element.css = selector
        else:
            raise ToolError("give a ref from your latest snapshot, or a selector")
        action.element = element.target()
        return locator, element

    def _focused(self) -> tuple[Locator | None, Element | None]:
        focused = self.page.locator(":focus")
        if focused.count() != 1:
            return None, None
        return focused, Element(id=0, **focused.evaluate(DESCRIBE_JS))

    # --- seeing ----------------------------------------------------------------------------

    def _screenshot(self, args: dict, action: Action) -> ToolResult:
        full = bool(args.get("full_page", False))
        png = self.page.screenshot(full_page=full)
        image, note = self._jpeg(png)
        return ToolResult(f"screenshot of {self.page.url} at {self.viewport}{note}", image=image)

    def _jpeg(self, png: bytes) -> tuple[bytes, str]:
        """The screenshot as a JPEG, at most `screenshot_max_width` wide (and not too tall)."""
        image = Image.open(io.BytesIO(png)).convert("RGB")
        note = ""
        if image.height > MAX_FULL_PAGE_HEIGHT:
            image = image.crop((0, 0, image.width, MAX_FULL_PAGE_HEIGHT))
            note = f" (cut at {MAX_FULL_PAGE_HEIGHT} px tall; scroll to see the rest)"
        width = self.config.screenshot_max_width
        if image.width > width:
            image = image.resize((width, round(image.height * width / image.width)))
            note += f" (scaled to {width} px wide)"
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=self.config.screenshot_quality)
        return out.getvalue(), note

    def _snapshot(self, args: dict, action: Action) -> ToolResult:
        state = read_page(self.page)
        self.elements = state.elements
        try:
            tree = self.page.locator("body").aria_snapshot(timeout=ACTION_TIMEOUT_MS)
        except PlaywrightError:
            tree = "(no accessibility tree)"
        if len(tree) > MAX_TREE:
            tree = tree[:MAX_TREE] + "\n... (cut; scroll or use visible_text for more)"
        elements = "\n".join(e.describe() for e in state.elements) or "(none)"
        messages = "\n".join(f'- "{m.text}"' for m in state.messages) or "(none)"
        return ToolResult(
            f"{state.title} — {state.url} at {self.viewport}\n"
            f"<page_content>\nACCESSIBILITY TREE:\n{self._safe(tree)}\n\n"
            f"INTERACTIVE ELEMENTS ([ref]):\n{self._safe(elements)}\n\n"
            f"MESSAGES:\n{self._safe(messages)}\n</page_content>"
        )

    def _visible_text(self, args: dict, action: Action) -> ToolResult:
        return ToolResult(self._paged("visible text", self._body_text(), _int(args, "offset", 0)))

    # --- measuring -------------------------------------------------------------------------

    def _evaluate_js(self, args: dict, action: Action) -> ToolResult:
        snippet = _text(args, "snippet")
        self._blocked_requests = []
        self._measuring = True
        try:
            raw = self.page.evaluate(MEASURE_JS.replace("/*SNIPPET*/", snippet))
        finally:
            self._measuring = False
        data = {
            "value": raw["value"],
            "error": raw["error"],
            "changed_the_page": raw["mutations"] > 0,
            "blocked_requests": list(self._blocked_requests),
        }
        notes = []
        if data["changed_the_page"]:
            notes.append(
                "WARNING: this snippet changed the page. Measure only; interact with the browser "
                "tools, or replay can't repeat what you did."
            )
        if data["blocked_requests"]:
            notes.append(
                "Requests that send data were blocked: " + ", ".join(data["blocked_requests"])
            )
        text = f"<page_content>\n{self._safe(json.dumps(data)[:MAX_TEXT])}\n</page_content>"
        return ToolResult("\n".join([text, *notes]), data=data)

    def _page_source(self, args: dict, action: Action) -> ToolResult:
        if self._document is None:
            raise ToolError("no page source: this page wasn't loaded from the server")
        html = self._document.text()
        scripts = "\n".join(f"- {url}" for url in self._scripts) or "(none loaded from files)"
        paged = self._paged(f"source of {self._document.url}", html, _int(args, "offset", 0))
        return ToolResult(f"{paged}\nSCRIPTS THIS PAGE LOADED:\n{scripts}")

    def _read_script(self, args: dict, action: Action) -> ToolResult:
        url = urljoin(self.page.url, _text(args, "url"))
        response = self._scripts.get(url)
        if response is None:
            raise ToolError(f"{url} was not loaded by this page (page_source lists what was)")
        return ToolResult(self._paged(f"script {url}", response.text(), _int(args, "offset", 0)))

    def _paged(self, what: str, text: str, offset: int) -> str:
        """`text` from `offset`, at most MAX_TEXT characters, saying where the rest starts."""
        chunk = text[offset : offset + MAX_TEXT]
        end = offset + len(chunk)
        more = f"; more from offset={end}" if end < len(text) else ""
        header = f"{what} (characters {offset}–{end} of {len(text)}{more})"
        return f"{header}\n<page_content>\n{self._safe(chunk)}\n</page_content>"

    # --- evidence --------------------------------------------------------------------------

    def _console(self, args: dict, action: Action) -> ToolResult:
        since = _int(args, "since", 0)
        lines = [text for seq, text in self._logs.console if seq > since][-MAX_EVENTS:]
        body = "\n".join(lines) or "(nothing)"
        return ToolResult(f"<page_content>\n{self._safe(body)}\n</page_content>")

    def _network(self, args: dict, action: Action) -> ToolResult:
        since = _int(args, "since", 0)
        lines = []
        for r in [r for r in self._logs.requests if r.seq > since][-MAX_EVENTS:]:
            status = r.status if r.status is not None else (r.failure or "pending")
            took = f" ({r.ms} ms)" if r.ms is not None else ""
            lines.append(f"#{r.seq} {r.method} {status} {r.kind} {r.url}{took}")
        body = "\n".join(lines) or "(no requests)"
        return ToolResult(f"<page_content>\n{self._safe(body)}\n</page_content>")

    def _on_console(self, message) -> None:
        if message.type not in ("error", "warning"):
            return
        location = message.location
        if from_extension(location, message.text):
            return
        where = f" ({location.get('url')}:{location.get('lineNumber')})" if location else ""
        seq = self._logs.next()
        self._logs.console.append((seq, f"#{seq} [{message.type}] {message.text}{where}"))

    def _on_page_error(self, error) -> None:
        seq = self._logs.next()
        self._logs.console.append((seq, f"#{seq} [uncaught] {error.name}: {error.message}"))

    def _on_request(self, request) -> None:
        entry = _Request(
            self._logs.next(), request.method, request.url, request.resource_type, time.monotonic()
        )
        self._by_request[id(request)] = entry
        self._logs.requests.append(entry)

    def _on_response(self, response) -> None:
        entry = self._by_request.get(id(response.request))
        if entry is not None:
            entry.status = response.status
            entry.ms = round((time.monotonic() - entry.started) * 1000)
        kind = response.request.resource_type
        try:
            main = response.frame == self.page.main_frame
        except PlaywrightError:
            main = False
        if kind == "document" and main:
            self._document, self._scripts = response, {}
        elif kind == "script":
            self._scripts[response.url] = response

    def _on_request_failed(self, request) -> None:
        entry = self._by_request.get(id(request))
        if entry is not None:
            entry.failure = request.failure or "failed"

    def _route(self, route) -> None:
        request = route.request
        if self._measuring and request.method.upper() not in SAFE_METHODS:
            self._blocked_requests.append(f"{request.method} {urlsplit(request.url).path}")
            route.abort("blockedbyclient")
            return
        route.continue_()

    # --- our checks ------------------------------------------------------------------------

    def _run_axe(self, args: dict, action: Action) -> ToolResult:
        violations = run_axe(self.page)
        lines = [
            f"- {v.rule_id} ({v.impact}): {v.help} — elements: {', '.join(v.targets[:10])}"
            for v in violations
        ]
        body = "\n".join(lines) or "(no violations)"
        return ToolResult(
            f"axe at {self.viewport}:\n<page_content>\n{self._safe(body)}\n</page_content>",
            data={"violations": [v.model_dump() for v in violations]},
        )

    def _check_layout(self, args: dict, action: Action) -> ToolResult:
        check = check_layout(self.page)
        if check is None:
            raise ToolError("the page couldn't be measured")
        data = {"problems": check.problems(), **check.model_dump()}
        body = json.dumps(data)[:MAX_TEXT]
        return ToolResult(
            f"layout at {self.viewport}:\n<page_content>\n{self._safe(body)}\n</page_content>",
            data=data,
        )

    def _check_meta(self, args: dict, action: Action) -> ToolResult:
        check = check_meta(self.page, self._image_cache)
        if check is None:
            raise ToolError("the page's metadata couldn't be read")
        data = check.model_dump()
        body = "\n".join(f"- {p}" for p in check.problems) or "(no problems)"
        return ToolResult(f"meta:\n<page_content>\n{self._safe(body)}\n</page_content>", data=data)

    def _keyboard_probe(self, args: dict, action: Action) -> ToolResult:
        target, element = self._target(args, action)
        reason = self._activation_reason("click", element)
        if reason:
            return self._blocked(action, reason)
        snapshot(self.page)
        handle = target.element_handle(timeout=ACTION_TIMEOUT_MS)
        target.click(timeout=ACTION_TIMEOUT_MS)
        wait_until_quiet(self.page, SETTLE_MS)
        kind = opened_by(self.page, handle)
        if kind is None:
            return ToolResult("the click opened no dialog, menu or disclosure to probe")
        failures = probe(self.page, kind, handle)
        data = {"kind": kind, "failures": failures}
        lines = [f"- {f['check']} ({f['severity']}): {f['detail']}" for f in failures]
        body = "\n".join(lines) or "(every check passed)"
        return ToolResult(
            f"the click opened a {kind}; keyboard checks:\n{body}\n"
            "(the probe pressed keys: take a snapshot before acting again)",
            data=data,
        )

    # --- helpers ---------------------------------------------------------------------------

    def _body_text(self) -> str:
        try:
            return self.page.evaluate("() => document.body ? document.body.innerText : ''")
        except PlaywrightError:
            return ""

    def _safe(self, text: str) -> str:
        """Page content on its way to the model: secrets out, the untrusted block kept closed."""
        return fence(redact(self.config.scrub(text)))


def _text(args: dict, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str):
        raise ToolError(f"{key} must be a string")
    return value


def _int(args: dict, key: str, default: int | None = None) -> int:
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
        raise ToolError(f"{key} must be a whole number")
    return value


def _first_line(error: Exception) -> str:
    return str(error).strip().splitlines()[0][:300] if str(error).strip() else type(error).__name__


def _first_line_of(text: str) -> str:
    return text.splitlines()[0][:300] if text else ""
