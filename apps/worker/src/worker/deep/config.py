"""Deep mode's choices that come from settings, the workspace and the run: which model drives
it and how many steps and seconds it may take.

Limits: the product defaults are DEEP_MAX_STEPS / DEEP_MAX_SECONDS (400 steps, 60 minutes); a
workspace may set its own, higher or lower; a run (an API caller, the dashboard) may only lower
the workspace's, the same rule as the current loop's per-run budgets (run 4, J3).
"""

from typing import TYPE_CHECKING, NamedTuple, Protocol

if TYPE_CHECKING:
    from worker.config import Settings

# Pinned IDs only (never an alias like "sonnet"), so a result says exactly which model ran.
# Sonnet is the default (the owner's decision, run 9); Opus can be chosen per run.
DEEP_MODELS = ("claude-sonnet-5-5", "claude-opus-5-5")


class WorkspaceLimits(Protocol):
    deep_max_steps: int | None
    deep_max_seconds: int | None


class RunChoices(Protocol):
    max_steps: int | None
    max_seconds: int | None
    engine_model: str | None


class DeepLimits(NamedTuple):
    steps: int
    seconds: int


def deep_limits(settings: "Settings", workspace: WorkspaceLimits, run: RunChoices) -> DeepLimits:
    """The steps and seconds a deep run may use: the workspace's limits (else the product
    defaults), lowered by the run's own if it set smaller ones."""
    steps = workspace.deep_max_steps or settings.deep_max_steps
    seconds = workspace.deep_max_seconds or settings.deep_max_seconds
    return DeepLimits(min(steps, run.max_steps or steps), min(seconds, run.max_seconds or seconds))


def deep_model(settings: "Settings", run: RunChoices) -> str:
    """The model that drives this deep run: the run's choice, else DEEP_MODEL."""
    model = run.engine_model or settings.deep_model
    if model not in DEEP_MODELS:
        raise ValueError(f"deep mode runs on {', '.join(DEEP_MODELS)}, not {model!r}")
    return model
