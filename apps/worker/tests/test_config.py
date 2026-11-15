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
