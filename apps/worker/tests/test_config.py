import pytest

from worker.config import Settings


def settings(**fields) -> Settings:
    return Settings(_env_file=None, **fields)  # ignore the developer's .env in tests


def test_provider_is_claude_when_a_key_is_set():
    assert settings(anthropic_api_key="sk-test").provider() == "claude"


def test_provider_is_fake_without_a_key():
    assert settings(anthropic_api_key="").provider() == "fake"


def test_explicit_provider_wins():
    assert settings(llm_provider="ollama", anthropic_api_key="sk-test").provider() == "ollama"


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        settings(llm_provider="gpt").provider()


def test_sqlalchemy_url_names_the_driver():
    url = settings(database_url="postgresql://a:b@localhost:5433/agent").sqlalchemy_url()
    assert url == "postgresql+psycopg://a:b@localhost:5433/agent"


def test_api_key_never_appears_in_repr():
    assert "sk-secret" not in repr(settings(anthropic_api_key="sk-secret"))


def test_haiku_is_the_default_agent_model_and_sonnet_is_not():
    # Run 7, the owner's decision from run 6's benchmark (DECISIONS D91).
    from worker.llm.claude_cli import ClaudeCliClient

    settings = Settings(_env_file=None)
    assert settings.agent_model == "claude-haiku-5-5"
    assert settings.claude_cli_model == "claude-haiku-5-5"
    assert settings.cheap_model == settings.claude_cli_cheap_model == "claude-haiku-5-5"
    assert ClaudeCliClient().agent_model == "claude-haiku-5-5"


def test_specs_are_off_by_default_until_measured_and_bench_specs_turns_them_on():
    # Run 7, D97: the owner's rule keeps specs on by default only once the holdout shows they help.
    from types import SimpleNamespace

    from worker.main import settings_for

    settings = Settings(_env_file=None)
    assert settings.use_specs is False
    on = settings_for(settings, SimpleNamespace(command="bench", specs=True))
    assert on.use_specs is True and settings.use_specs is False  # a copy, not a change
    assert settings_for(settings, SimpleNamespace(command="bench", specs=False)).use_specs is False
    assert settings_for(settings, SimpleNamespace(command="run")).use_specs is False


def test_local_apps_count_as_our_own_only_in_dev_mode():
    """Run 8, N4: open-source apps started on this Mac for the real-world benchmark."""
    urls = "http://localhost:5301, http://localhost:5302"
    dev = settings(dev_mode=True, local_app_urls=urls)
    assert "http://localhost:5301" in dev.demo_urls()
    assert "http://localhost:5302" in dev.demo_urls()
    production = settings(dev_mode=False, local_app_urls=urls)
    assert "http://localhost:5301" not in production.demo_urls()


def test_no_local_apps_by_default():
    assert settings(dev_mode=True).demo_urls() == [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
    ]
