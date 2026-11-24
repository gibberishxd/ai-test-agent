"""Deep mode's settings and limits (run 9): the defaults, which models it may use, and how a
workspace's and a run's limits combine."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from worker.config import Settings
from worker.deep.config import DEEP_MODELS, deep_limits, deep_model


def settings(**fields) -> Settings:
    return Settings(_env_file=None, **fields)  # ignore the developer's .env in tests


def workspace(steps=None, seconds=None):
    return SimpleNamespace(deep_max_steps=steps, deep_max_seconds=seconds)


def run(steps=None, seconds=None, model=None):
    return SimpleNamespace(max_steps=steps, max_seconds=seconds, engine_model=model)


def test_product_defaults_are_400_steps_and_60_minutes():
    s = settings()
    assert (s.deep_max_steps, s.deep_max_seconds) == (400, 3600)


def test_defaults_are_sonnet_at_high_effort_with_small_jpeg_screenshots():
    s = settings()
    assert (s.deep_model, s.deep_effort) == ("claude-sonnet-5-5", "high")
    assert s.deep_screenshot_max_width == 1280
    assert 1 <= s.deep_screenshot_quality <= 100


def test_customers_use_their_own_api_key_by_default():
    assert settings().deep_auth == "api"


def test_only_sonnet_and_opus_can_drive_deep_mode():
    assert DEEP_MODELS == ("claude-sonnet-5-5", "claude-opus-5-5")


@pytest.mark.parametrize(
    "field, value",
    [("deep_auth", "pro"), ("deep_effort", "extreme"), ("deep_model", "claude-haiku-5-5")],
)
def test_unknown_deep_settings_are_refused(field, value):
    with pytest.raises(ValidationError):
        settings(**{field: value})


def test_without_workspace_or_run_limits_the_product_defaults_apply():
    assert deep_limits(settings(), workspace(), run()) == (400, 3600)


def test_a_workspace_sets_its_own_limits_higher_or_lower():
    assert deep_limits(settings(), workspace(800, 7200), run()) == (800, 7200)
    assert deep_limits(settings(), workspace(100, 600), run()) == (100, 600)


def test_a_run_can_lower_the_workspace_limits():
    assert deep_limits(settings(), workspace(800, 7200), run(50, 300)) == (50, 300)


def test_a_run_can_never_raise_them():
    assert deep_limits(settings(), workspace(), run(1000, 9000)) == (400, 3600)
    assert deep_limits(settings(), workspace(100, 600), run(400, 3600)) == (100, 600)


def test_a_run_uses_the_default_model_unless_it_names_one():
    assert deep_model(settings(), run()) == "claude-sonnet-5-5"
    assert deep_model(settings(), run(model="claude-opus-5-5")) == "claude-opus-5-5"


def test_a_run_naming_another_model_is_refused():
    with pytest.raises(ValueError):
        deep_model(settings(), run(model="claude-haiku-5-5"))
