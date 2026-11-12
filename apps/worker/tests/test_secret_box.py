"""The worker decrypts what the web app encrypted (same vector as lib/secret-box.test.ts)."""

import json
from pathlib import Path

import pytest

from worker.secret_box import SecretBoxError, decrypt_secret, server_key

VECTOR = json.loads((Path(__file__).parent / "fixtures" / "secret_box_vector.json").read_text())
KEY = server_key(VECTOR["key_base64"])


def test_decrypts_the_web_apps_vector():
    assert decrypt_secret(VECTOR["stored"], VECTOR["workspace_id"], KEY) == VECTOR["plaintext"]


def test_refuses_another_workspace():
    with pytest.raises(SecretBoxError, match="workspace"):
        decrypt_secret(VECTOR["stored"], "22222222-2222-4222-8222-222222222222", KEY)


def test_refuses_a_missing_or_short_server_key():
    with pytest.raises(SecretBoxError, match="MODEL_KEYS_SECRET"):
        server_key("")
    with pytest.raises(SecretBoxError, match="MODEL_KEYS_SECRET"):
        server_key("c2hvcnQ=")
