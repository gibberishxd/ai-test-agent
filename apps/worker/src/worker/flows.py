"""Critical flows (run 7, M4; roadmap item 2).

A team writes the journeys that must never break in plain language ("add an item to the cart,
check out and place the order"). Each run covers them first:

- A journey with a saved script is **replayed without a model**: the same steps on the same
  elements (verify.replay, which finds an element by role and name, then nearby text, CSS path
  and position), then its checks (texts that showed it worked) must be on the page.
- A journey without a script, or whose replay broke (an element gone, a page changed), is given to
  the agent as a short episode: complete this journey, then finish with "PASSED: ..." quoting what
  showed it worked, or "FAILED: ...". A passing episode's steps become the (new) script; a failing
  one becomes a finding.

So the model is only paid for when something changed, and a run on an unchanged app checks its
journeys for the price of a browser.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext

from worker.verify import ReplayError, ReplayStep, replay

MAX_FLOW_STEPS = 15  # one journey; the rest of the run's steps are for exploring
SCRIPT_ACTIONS = (
    "click",
    "double_click",
    "type",
    "select",
    "navigate",
    "go_back",
    "reload",
    "set_viewport",
)
QUOTED = re.compile(r"[\"“'‘]([^\"”'’]{2,80})[\"”'’]")
MAX_CHECKS = 3

# The demo shop's critical flows for the measurements (run 7, M4 and M6): plain product journeys
# written for the shop's pages, not taken from its bug list.
DEMO_SHOP_FLOWS = [
    (
        "Sign in",
        "Open the login page, sign in with the demo account the page offers, and check that you "
        "are signed in.",
    ),
    (
        "Add to cart and check out",
        "Open a product, add it to the cart, go to the cart, check out with the test details and "
        "place the order.",
    ),
    (
        "Change profile",
        "Open your profile, change your display name, save it, and check that the new name is "
        "shown.",
    ),
]


@dataclass
class FlowOutcome:
    """What happened to one journey in one run (stored as a flow_results row)."""

    status: str  # passed | replayed | repaired | failed | skipped
    detail: str
    replayed: bool = False
    model_calls: int = 0
    estimated_cost_usd: float = 0.0
    script: dict | None = None  # the new script, when one was saved or repaired
    steps: list = field(default_factory=list)  # the episode's StepRecords (for a finding)
    last_url: str | None = None
    first_step: int = 0  # the run step index of the episode's first step


def flow_task(name: str, goal: str) -> str:
    """The focus line for a journey episode: complete it, then say how it went, in a form the
    worker can read (and save as checks)."""
    return (
        f'CRITICAL FLOW "{name}": {goal}\n'
        "Complete this journey like a real user, step by step, and nothing else. Then call finish "
        'with a summary that starts with "PASSED:" and quotes the text on the page that shows it '
        'worked (for example PASSED: "Order confirmed"), or with "FAILED:", what went wrong, and '
        'the text you expected to see but didn\'t, in quotes (FAILED: no "Profile saved" after '
        "Save). If the site is wrong along the way, report_bug first, then finish with FAILED."
    )


def parse_finish(summary: str | None) -> tuple[bool | None, list[str], str]:
    """(passed?, check texts, detail) from an episode's finish summary. None: it didn't say."""
    text = (summary or "").strip()
    head = text.upper()
    passed = True if head.startswith("PASSED") else False if head.startswith("FAILED") else None
    detail = re.sub(r"^(PASSED|FAILED)\s*:?\s*", "", text, flags=re.I).strip()
    # PASSED: the texts that showed it worked. FAILED: the texts it expected and didn't see.
    checks = (
        [q.strip() for q in QUOTED.findall(detail) if q.strip()][:MAX_CHECKS]
        if passed is not None
        else []
    )
    return passed, checks, detail[:500]


def script_from_steps(
    start_url: str, steps: list, checks: list[str], failing: bool = False
) -> dict | None:
    """The replayable form of an episode: its effective actions, the elements they acted on, and
    the checks. `failing`: a journey the agent couldn't complete, saved with the texts it expected
    (the next run replays it without a model: still missing = the same failure, there = fixed).
    None when there is nothing to replay."""
    kept = []
    for step in steps:
        result = str(step.result or "")
        if step.action not in SCRIPT_ACTIONS or step.blocked or result.startswith("error:"):
            continue
        args = {
            k: v for k, v in (step.args or {}).items() if k in ("text", "option", "url", "size")
        }
        kept.append({"action": step.action, "args": args, "element": step.element, "url": step.url})
    if not kept:
        return None
    end = steps[-1].url if steps else start_url
    return {
        "start_url": start_url,
        "steps": kept,
        "checks": checks,
        "end_path": urlsplit(end).path or "/",
        "failing": failing,
    }


def replay_steps(script: dict) -> list[ReplayStep]:
    return [
        ReplayStep(s["action"], s.get("args") or {}, s.get("element"), s.get("url"))
        for s in script.get("steps", [])
    ]


def replay_flow(context: BrowserContext, script: dict) -> tuple[str, str]:
    """Replay a saved journey in a new tab, no model. ("ok" | "broken" | "checks_failed", detail):
    broken = a step couldn't be repeated (the page changed); checks_failed = every step ran but
    the page doesn't show what it should."""
    page = context.new_page()
    try:
        try:
            replay(page, script["start_url"], replay_steps(script))
        except ReplayError as error:
            return "broken", f"replay broke at step {error.step} ({error.action}): {error}"
        body = page.evaluate("() => document.body.innerText") or ""
        missing = [c for c in script.get("checks", []) if c.lower() not in body.lower()]
        if missing:
            shown = ", ".join(f'"{m}"' for m in missing)
            return "checks_failed", f"replayed every step, but the page doesn't show {shown}"
        expected_path = script.get("end_path")
        if not script.get("checks") and expected_path and urlsplit(page.url).path != expected_path:
            ended = urlsplit(page.url).path
            return (
                "checks_failed",
                f"replayed every step, but ended on {ended}, not {expected_path}",
            )
        return "ok", "replayed: every step and check passed"
    finally:
        page.close()
