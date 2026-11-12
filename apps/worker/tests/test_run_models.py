"""A run that names a workspace model gets that model, or fails before starting with the reason."""

import base64
import logging
import os

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from worker.config import Settings
from worker.db.models import ModelConfig, Run, RunStatus, Workspace
from worker.llm import FakeClient
from worker.model_configs import client_for_run
from worker.runner import process_next

SERVER_KEY = bytes(range(32))
KEY = "sk-live-ABCD1234wxyz"
PASSED = {"ok": True, "answers": True, "tools": True, "vision": True, "error": None}


def encrypt(plain: str, workspace_id: str) -> str:
    """What the web app stores (lib/secret-box.ts)."""
    nonce = os.urandom(12)
    body = AESGCM(SERVER_KEY).encrypt(nonce, plain.encode(), workspace_id.encode())
    return "v1:" + base64.b64encode(nonce + body).decode()


def settings(**fields) -> Settings:
    base = dict(_env_file=None, model_keys_secret=base64.b64encode(SERVER_KEY).decode())
    return Settings(**{**base, **fields})


def add_config(session, workspace, probe=PASSED, **fields) -> ModelConfig:
    config = ModelConfig(
        workspace_id=workspace.id,
        label="OpenRouter",
        provider="openai-compat",
        base_url="https://openrouter.ai/api/v1",
        model="google/gemini-3-flash",
        api_key_ciphertext=encrypt(KEY, str(workspace.id)),
        api_key_last4="wxyz",
        probe=probe,
        **fields,
    )
    session.add(config)
    session.commit()
    return config


def queue(session, workspace, config) -> Run:
    run = Run(
        workspace_id=workspace.id, target_url="http://localhost:5173/", model_config_id=config.id
    )
    session.add(run)
    session.commit()
    return run


@pytest.fixture
def other_workspace(sessions):
    with sessions() as session:
        ws = Workspace(name="Other", slug="other")
        session.add(ws)
        session.commit()
        return ws


def resolve_ok(host):
    return ["93.184.215.14"]


def test_the_run_gets_its_workspace_model_with_the_decrypted_key(sessions, workspace, caplog):
    caplog.set_level(logging.DEBUG)
    with sessions() as session:
        config = add_config(session, workspace)
        run = queue(session, workspace, config)
        client = client_for_run(session, run, FakeClient(), settings(), resolve=resolve_ok)
    assert (client.provider, client.agent_model) == ("openai-compat", "google/gemini-3-flash")
    assert client._key.get_secret_value() == KEY  # decrypted right, kept as a secret
    assert KEY not in caplog.text and KEY not in repr(client)


def test_without_a_model_the_run_uses_the_servers_model(sessions, workspace):
    default = FakeClient()
    with sessions() as session:
        run = Run(workspace_id=workspace.id, target_url="http://localhost:5173/")
        session.add(run)
        session.commit()
        assert client_for_run(session, run, default, settings(), resolve=resolve_ok) is default


def process(sessions, s):
    executed = []
    process_next(
        sessions,
        FakeClient(),
        lambda session, run, llm: executed.append(llm),
        client_for=lambda session, run, default: client_for_run(
            session, run, default, s, resolve=resolve_ok
        ),
    )
    return executed


def test_a_model_from_another_workspace_fails_the_run_before_it_starts(
    sessions, workspace, other_workspace
):
    with sessions() as session:
        foreign = add_config(session, other_workspace)
        run = queue(session, workspace, foreign)
    assert process(sessions, settings()) == []
    with sessions() as session:
        stored = session.get(Run, run.id)
        assert stored.status == RunStatus.FAILED
        assert "doesn't belong to this workspace" in stored.error


def test_a_key_copied_into_another_workspace_doesnt_decrypt(sessions, workspace, other_workspace):
    with sessions() as session:
        config = add_config(session, workspace)
        config.api_key_ciphertext = encrypt(KEY, str(other_workspace.id))  # someone else's
        session.commit()
        run = queue(session, workspace, config)
    assert process(sessions, settings()) == []
    with sessions() as session:
        assert "can't be decrypted" in session.get(Run, run.id).error


def test_an_untested_model_fails_the_run_with_the_reason(sessions, workspace):
    with sessions() as session:
        run = queue(session, workspace, add_config(session, workspace, probe=None))
    process(sessions, settings())
    with sessions() as session:
        assert "hasn't passed Test connection" in session.get(Run, run.id).error


def test_a_private_endpoint_is_refused_outside_dev_mode(sessions, workspace):
    with sessions() as session:
        config = add_config(session, workspace)
        run = queue(session, workspace, config)
        with pytest.raises(Exception, match="private"):
            client_for_run(
                session, run, FakeClient(), settings(dev_mode=False), resolve=lambda h: ["10.0.0.5"]
            )


def test_the_run_records_the_workspace_model(sessions, workspace):
    with sessions() as session:
        run = queue(session, workspace, add_config(session, workspace))
    executed = process(sessions, settings())
    assert executed[0].provider == "openai-compat"
    with sessions() as session:
        stored = session.get(Run, run.id)
        assert (stored.provider, stored.model) == ("openai-compat", "google/gemini-3-flash")
