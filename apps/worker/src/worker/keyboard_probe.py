"""The keyboard probe: do the dialogs, menus and toggles the agent opened work from a keyboard?

How it works, in two halves:
1. While the agent explores, every click is bracketed by two cheap measurements: which elements
   are on screen just before it, and which ones appeared because of it. What appeared is
   classified (`OPENED_JS`):
   - a **dialog**: something with role=dialog / alertdialog or an open <dialog>, or a
     fixed-position layer covering more than half the screen;
   - a **menu**: a button showed two or more new links or buttons;
   - a **disclosure**: a button showed content that was already in the page, hidden.
   Clicks that load a new page, and <summary> (the browser's own disclosure, which reports its
   state to assistive technology by itself), are skipped.
2. After the agent finishes, each control (at most MAX_PROBES) is opened again in a fresh tab
   by replaying the agent's steps, and probed with real key presses:
   - dialog: exposed as role=dialog with aria-modal, focus moves into it, Tab keeps focus
     inside it, Escape closes it (WAI-ARIA Authoring Practices, Dialog (Modal) pattern; WCAG
     2.4.3 Focus Order, 4.1.2 Name, Role, Value);
   - menu: Escape closes it, the button has an accessible name and aria-expanded (APG
     Disclosure and Menu Button patterns);
   - disclosure: the button exposes aria-expanded.
   Probing in a fresh tab leaves the agent's own tab alone: pressing Escape there would close
   what the agent just opened.

Severity (the owner's call): focus not moving into or staying in a dialog, and Escape not
closing a dialog or menu, are `medium`; a missing role, aria-modal, aria-expanded or name is
`low`. One finding per failing control, at the severity of its worst failure.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from playwright.sync_api import BrowserContext, ElementHandle, Page
from playwright.sync_api import Error as PlaywrightError

from worker.report import BugReport
from worker.safety.secrets import redact
from worker.verify import (
    ReplayError,
    ReplayStep,
    find_target,
    replay,
    size_or_desktop,
    wait_until_drawn,
)

MAX_PROBES = 8  # controls probed per run
MAX_SCANNED = 20000  # elements looked at per snapshot
OVERLAY_SHARE = 0.5  # "covers most of the screen": more than half of the viewport's area
MAX_TABS = 20

MEDIUM, LOW = "medium", "low"

# Which elements are on screen now (kept in the page for OPENED_JS to compare against).
SNAPSHOT_JS = """(max) => {
  const onScreen = (el) => {
    if (!el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0
      && r.top < innerHeight && r.left < innerWidth;
  };
  const shown = new WeakSet(), texts = new WeakMap();
  let n = 0;
  for (const el of document.body ? document.body.querySelectorAll('*') : []) {
    if (n++ > max) break;
    if (onScreen(el)) shown.add(el);
    texts.set(el, (el.textContent || '').trim());
  }
  window.__ataBefore = { shown, texts };
}"""

# What the click on `control` opened, compared with SNAPSHOT_JS: a dialog, a menu, a
# disclosure, or nothing. Keeps the opened elements in the page for the probe.
OPENED_JS = """([control, max, share]) => {
  const before = window.__ataBefore;
  window.__ataOpened = null;
  if (!before || !document.body) return null;
  const onScreen = (el) => {
    if (!el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0
      && r.top < innerHeight && r.left < innerWidth;
  };
  const fresh = new Set();
  let n = 0;
  for (const el of document.body.querySelectorAll('*')) {
    if (n++ > max) break;
    if (!before.shown.has(el) && onScreen(el)) fresh.add(el);
  }
  const roots = [...fresh].filter((el) => !fresh.has(el.parentElement));
  if (!roots.length) return null;
  const DIALOG = '[role=dialog], [role=alertdialog], dialog[open]';
  let dialog = null;
  for (const root of roots) {
    dialog = root.matches(DIALOG) ? root : (root.querySelector(DIALOG) || root.closest(DIALOG));
    if (dialog && onScreen(dialog)) break;
    dialog = null;
  }
  if (!dialog) {
    const area = innerWidth * innerHeight;
    const covered = (el) => {
      const r = el.getBoundingClientRect();
      const w = Math.min(r.right, innerWidth) - Math.max(r.left, 0);
      const h = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
      return w > 0 && h > 0 ? (w * h) / area : 0;
    };
    const layers = roots.filter((el) => getComputedStyle(el).position === 'fixed'
      && covered(el) > share);
    dialog = layers.sort((a, b) => covered(b) - covered(a))[0] || null;
  }
  const tag = control ? control.tagName.toLowerCase() : '';
  const isButton = control && (tag === 'button' || control.getAttribute('role') === 'button'
    || (tag === 'input' && ['button'].includes(control.type)));
  const submits = control && control.form && (tag === 'button' ? control.type === 'submit'
    : control.type === 'submit');
  let kind = null;
  if (dialog) kind = 'dialog';
  else if (isButton && !submits && tag !== 'summary') {
    const INTERACTIVE = 'a[href], button, [role=menuitem], [role=link], [role=button], input';
    const controls = roots.reduce((sum, root) => sum
      + (root.matches(INTERACTIVE) ? 1 : 0) + root.querySelectorAll(INTERACTIVE).length, 0);
    // Content that was in the page, hidden, with the same text: revealed, not newly written
    // (a status message like "Saved." is new text, a response rather than a disclosure).
    const revealed = roots.some((root) => {
      const was = before.texts.get(root);
      return !!was && was === (root.textContent || '').trim();
    });
    if (controls >= 2) kind = 'menu';
    else if (revealed) kind = 'disclosure';
  }
  if (!kind) return null;
  window.__ataOpened = { kind, dialog, roots, control };
  return kind;
}"""

ACCESSIBLE_NAME_JS = """(el) => {
  const byIds = (el.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean)
    .map((id) => document.getElementById(id)).filter(Boolean)
    .map((n) => n.textContent.trim()).join(' ');
  const images = Array.from(el.querySelectorAll('img[alt], svg title'))
    .map((n) => (n.getAttribute('alt') || n.textContent || '').trim()).join(' ');
  return (byIds || el.getAttribute('aria-label') || el.innerText || el.value
    || el.getAttribute('title') || images || '').trim();
}"""

DIALOG_STATE_JS = """() => {
  const { dialog } = window.__ataOpened;
  const DIALOG = '[role=dialog], [role=alertdialog], dialog';
  const target = dialog.matches(DIALOG) ? dialog : (dialog.querySelector(DIALOG) || dialog);
  const active = document.activeElement;
  const TABBABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), '
    + 'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  const tabbable = Array.from(dialog.querySelectorAll(TABBABLE)).filter((el) =>
    el.checkVisibility({ visibilityProperty: true }) && el.getBoundingClientRect().width > 0);
  return {
    role: target.matches(DIALOG),
    modal: target.getAttribute('aria-modal') === 'true' || target.matches(':modal'),
    focus_inside: !!active && active !== document.body && dialog.contains(active),
    tabbable: tabbable.length,
  };
}"""

FOCUS_FIRST_JS = """() => {
  const { dialog } = window.__ataOpened;
  const TABBABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), '
    + 'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  const first = Array.from(dialog.querySelectorAll(TABBABLE)).find((el) =>
    el.checkVisibility({ visibilityProperty: true }) && el.getBoundingClientRect().width > 0);
  if (first) first.focus();
  return !!first && document.activeElement === first;
}"""

FOCUS_INSIDE_JS = """() => {
  const { dialog } = window.__ataOpened;
  const active = document.activeElement;
  return !!active && active !== document.body && dialog.contains(active);
}"""

STILL_OPEN_JS = """() => {
  const { kind, dialog, roots } = window.__ataOpened;
  const shown = (el) => el.isConnected
    && el.checkVisibility({ opacityProperty: true, visibilityProperty: true })
    && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
  return kind === 'dialog' ? shown(dialog) : roots.some(shown);
}"""


@dataclass
class Opened:
    """A control the agent's click opened something with (recorded during the loop)."""

    step: int  # the agent's step (1-based, within its loop)
    kind: str  # "dialog", "menu" or "disclosure"
    element: dict  # role, name, css... of the control, for replay


@dataclass
class ProbeResult:
    kind: str
    control: dict
    url: str
    failures: list[dict] = field(default_factory=list)  # {check, severity, detail}

    @property
    def severity(self) -> str:
        return MEDIUM if any(f["severity"] == MEDIUM for f in self.failures) else LOW


def snapshot(page: Page) -> None:
    """Remember what is on screen now (call just before a click)."""
    try:
        page.evaluate(SNAPSHOT_JS, MAX_SCANNED)
    except PlaywrightError:
        pass


def opened_by(page: Page, control: ElementHandle | None) -> str | None:
    """What the click on `control` opened since `snapshot`: "dialog", "menu", "disclosure"."""
    try:
        return page.evaluate(OPENED_JS, [control, MAX_SCANNED, OVERLAY_SHARE])
    except PlaywrightError:
        return None


def probe(page: Page, kind: str, control: ElementHandle) -> list[dict]:
    """Probe what is open now (found by `opened_by`) with the keyboard; returns failures."""
    if kind == "dialog":
        return _probe_dialog(page)
    failures = _aria_expanded(control)
    if kind == "menu":
        if not control.evaluate(ACCESSIBLE_NAME_JS):
            failures.append(_fail("name", LOW, "The button that opens it has no accessible name."))
        if _still_open_after_escape(page):
            failures.append(_fail("escape", MEDIUM, "Escape doesn't close it."))
    return failures


def _probe_dialog(page: Page) -> list[dict]:
    failures = []
    state = page.evaluate(DIALOG_STATE_JS)
    if not state["role"]:
        failures.append(_fail("role", LOW, "It isn't exposed as role=dialog."))
    if not state["modal"]:
        failures.append(_fail("aria-modal", LOW, "It doesn't say it's modal (aria-modal)."))
    if not state["focus_inside"]:
        failures.append(_fail("focus-in", MEDIUM, "Focus doesn't move into it when it opens."))
    if state["tabbable"] and page.evaluate(FOCUS_FIRST_JS):
        presses = min(2 * state["tabbable"] + 1, MAX_TABS)
        for _ in range(presses):
            page.keyboard.press("Tab")
            if not page.evaluate(FOCUS_INSIDE_JS):
                failures.append(
                    _fail("focus-trap", MEDIUM, "Tab moves focus out of it, to the page behind.")
                )
                break
    if _still_open_after_escape(page):
        failures.append(_fail("escape", MEDIUM, "Escape doesn't close it."))
    return failures


def _aria_expanded(control: ElementHandle) -> list[dict]:
    value = control.get_attribute("aria-expanded")
    if value is None:
        return [_fail("aria-expanded", LOW, "The button has no aria-expanded.")]
    if value != "true":
        return [_fail("aria-expanded", LOW, f'aria-expanded is "{value}" while it is open.')]
    return []


def _still_open_after_escape(page: Page) -> bool:
    page.keyboard.press("Escape")
    wait_until_drawn(page)  # a closing animation
    return bool(page.evaluate(STILL_OPEN_JS))


def _fail(check: str, severity: str, detail: str) -> dict:
    return {"check": check, "severity": severity, "detail": detail}


def probe_opened(
    context: BrowserContext,
    plans: list[tuple[str, list[ReplayStep]]],
    kind: str,
    viewport: str,
) -> ProbeResult | None:
    """Open the control again by replaying one of `plans` (each ends with the click), then
    probe it. None if no plan opens the same kind of thing again."""
    for start_url, steps in plans:
        page = context.new_page()
        try:
            page.set_viewport_size(size_or_desktop(viewport))
            try:
                replay(page, start_url, steps, before_last=lambda _step, p=page: snapshot(p))
            except ReplayError:
                continue
            element = steps[-1].element or {}
            try:
                control = find_target(page, element).element_handle()
            except (ReplayError, PlaywrightError):
                continue
            if opened_by(page, control) != kind:
                continue
            failures = probe(page, kind, control)
            return ProbeResult(kind=kind, control=element, url=page.url, failures=failures)
        except PlaywrightError:
            continue
        finally:
            page.close()
    return None


def probe_finding(result: ProbeResult, scrub: Callable[[str], str] = lambda t: t) -> BugReport:
    """One finding for a control that failed at least one check."""
    control = result.control
    role = control.get("role") or "control"
    name = scrub(str(control.get("name") or "")).strip()[:80]
    label = f'{role} "{name}"' if name else f"{role} ({control.get('css') or 'unnamed'})"
    noun = {"dialog": "dialog", "menu": "menu", "disclosure": "expandable section"}[result.kind]
    details = " ".join(f["detail"] for f in result.failures)
    return BugReport(
        title=f"Keyboard and screen reader: the {noun} opened by {label}",
        severity=result.severity,
        category="accessibility",
        page_url=result.url,
        expected=_expected(result.kind),
        actual=redact(details),
        repro_steps=[f"Open {result.url}", f"Click {label}", "Use Tab and Escape"],
        evidence={
            "check": "keyboard",
            "kind": result.kind,
            "control": {k: control.get(k) for k in ("role", "name", "css")},
            "failures": result.failures,
            "pages": [result.url],
        },
        source="deterministic",
        status="confirmed",
    )


def _expected(kind: str) -> str:
    if kind == "dialog":
        return (
            "A modal dialog is exposed as role=dialog with aria-modal, takes the focus when it "
            "opens, keeps Tab inside it, and closes on Escape."
        )
    if kind == "menu":
        return "A menu button has a name and aria-expanded, and Escape closes the menu."
    return "A button that shows and hides content exposes aria-expanded."
