"""Which model a run uses: the workspace's own (if the run names one) or the worker's default.

The web app has already checked the model belongs to the workspace and passed Test
connection, but the worker checks again: it is the part that spends the key. Every failure
raises ModelConfigError with a reason the user can act on, and the runner marks the run
failed with it before anything is visited.
"""

from collections.abc import Callable
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from worker.config import Settings
from worker.db.models import ModelConfig, Run
from worker.llm import LLMClient
from worker.safety.network import is_public_ip, resolve
from worker.secret_box import SecretBoxError, decrypt_secret, server_key

Resolver = Callable[[str], list[str]]


class ModelConfigError(Exception):
    pass


def client_for_run(
    session: Session,
    run: Run,
    default: LLMClient,
    settings: Settings,
    resolve: Resolver = resolve,
) -> LLMClient:
    if run.model_config_id is None:
        return default
    config = session.get(ModelConfig, run.model_config_id)
    if config is None or config.workspace_id != run.workspace_id:
        raise ModelConfigError("the run's model doesn't belong to this workspace")
    if not (config.probe or {}).get("ok"):
        raise ModelConfigError(
            f"the model “{config.label}” hasn't passed Test connection (Settings → Models)"
        )
    api_key = _decrypt(config, settings)
    if config.provider == "openai-compat":
        _check_endpoint(config.base_url or "", settings, resolve)
        from worker.llm.openai_compat import OpenAICompatClient

        return OpenAICompatClient(
            base_url=config.base_url or "",
            model=config.model,
            api_key=api_key,
            cheap_model=config.cheap_model,
            input_price=config.input_price,
            output_price=config.output_price,
        )
    if config.provider == "claude":
        if not api_key:
            raise ModelConfigError("the Anthropic model has no API key")
        from worker.llm.claude import ClaudeClient

        return ClaudeClient(api_key, config.model, config.cheap_model or config.model)
    raise ModelConfigError(f"unknown provider {config.provider!r}")


def _decrypt(config: ModelConfig, settings: Settings) -> str | None:
    if not config.api_key_ciphertext:
        return None
    try:
        key = server_key(settings.model_keys_secret.get_secret_value())
        return decrypt_secret(config.api_key_ciphertext, str(config.workspace_id), key)
    except SecretBoxError as error:
        raise ModelConfigError(f"the model's API key can't be used: {error}") from error


def _check_endpoint(base_url: str, settings: Settings, resolve: Resolver) -> None:
    """The worker calls this URL from our network: public addresses only, except in dev mode."""
    host = urlsplit(base_url).hostname or ""
    ips = resolve(host)
    if not ips:
        raise ModelConfigError(f"the model's endpoint {host!r} doesn't resolve")
    if not settings.dev_mode and not all(is_public_ip(ip) for ip in ips):
        raise ModelConfigError(f"the model's endpoint {host} resolves to a private address")
