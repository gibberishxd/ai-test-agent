"""The generic QA checklist deep mode plans from. Nothing here is about any one site: a guard
test checks it (and the prompts and tools) against the benchmark apps' names and bugs.

Each area is something a careful manual tester covers on any web app. The plan must cover every
area with at least one item, or say why an area doesn't apply; layout must be planned at every
viewport in VIEWPORTS.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Area:
    key: str
    title: str
    what: str  # what to check, in a tester's words
    can_skip: bool = True  # may the plan mark it "not applicable" (with a reason)?


VIEWPORTS = ("390x844", "768x1024", "1440x900")  # a phone, a tablet, a laptop

AREAS = (
    Area(
        "flows",
        "Core flows and forms",
        "Each main flow from start to end. Every form: valid input, empty and invalid input, "
        "boundaries (zero, negative, very long, special characters), what happens on submit and "
        "whether a request is actually sent, success and error messages and where they appear, "
        "and what survives a reload or going back.",
    ),
    Area(
        "navigation",
        "Links and navigation",
        "Every link, menu and button that navigates goes where it says; back and forward work; "
        "direct links to inner pages load; unknown pages show a proper not-found page; the "
        "current page is marked in menus.",
    ),
    Area(
        "layout",
        "Layout at each viewport",
        f"At {', '.join(VIEWPORTS)}: look at screenshots of each page. No horizontal overflow, "
        "overlapping or cut-off content, hidden controls, unreadable text or targets too small to "
        "tap; sticky and fixed elements don't cover content.",
        can_skip=False,
    ),
    Area(
        "visual",
        "Visual consistency",
        "The same element in the same role looks the same everywhere: buttons, links, headings, "
        "cards, prices, icons, spacing and alignment. Note anything that looks unfinished: "
        "placeholder text or images, broken images, wrong or mixed fonts.",
    ),
    Area(
        "accessibility",
        "Accessibility",
        "Text contrast; every control has an accessible name; everything works with the keyboard "
        "alone, in a sensible order, with a visible focus; dialogs and menus take focus, keep it "
        "and close with Escape; images have useful alternative text; headings and landmarks.",
    ),
    Area(
        "meta",
        "Meta and SEO",
        "Page titles and descriptions, the language attribute, Open Graph and social tags, "
        "canonical links, icons, one main heading per page.",
    ),
    Area(
        "console_network",
        "Console and network",
        "Errors and warnings in the console; failed, slow or repeated requests; error responses "
        "behind a success message; requests that should happen but don't.",
    ),
    Area(
        "promises",
        "What the page promises",
        "What the app's own text promises exists and works: features, links, numbers, counts, "
        "totals, dates, policies and help text. A total must add up; a count must match the "
        "list; a promised option must be there.",
    ),
)

AREA_KEYS = tuple(area.key for area in AREAS)


def checklist_text() -> str:
    """The checklist as the model reads it when it writes its plan."""
    lines = []
    for area in AREAS:
        rule = "" if area.can_skip else " (required at every viewport; can't be skipped)"
        lines.append(f"- {area.key}: {area.title}{rule}. {area.what}")
    return "\n".join(lines)
