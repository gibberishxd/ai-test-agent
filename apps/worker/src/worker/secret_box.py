"""Decrypting a workspace's model API key, stored by the web app (apps/web/lib/secret-box.ts).

AES-256-GCM with the server key MODEL_KEYS_SECRET and the workspace id as associated data,
stored as "v1:" + base64(nonce ‖ ciphertext ‖ tag). The worker only ever decrypts, right
before building the model client, and keeps the result out of logs (SecretStr).
"""

import base64

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = "v1:"
NONCE_BYTES = 12


class SecretBoxError(Exception):
    pass


def server_key(raw_base64: str) -> bytes:
    try:
        key = base64.b64decode(raw_base64 or "", validate=True)
    except ValueError:
        key = b""
    if len(key) != 32:
        raise SecretBoxError("MODEL_KEYS_SECRET must be 32 random bytes in base64")
    return key


def decrypt_secret(stored: str, workspace_id: str, key: bytes) -> str:
    if not stored.startswith(VERSION):
        raise SecretBoxError("unknown secret format")
    data = base64.b64decode(stored[len(VERSION) :])
    nonce, body = data[:NONCE_BYTES], data[NONCE_BYTES:]  # body = ciphertext ‖ tag
    try:
        plain = AESGCM(key).decrypt(nonce, body, workspace_id.encode("utf-8"))
    except InvalidTag as error:
        raise SecretBoxError(
            "the key can't be decrypted here (wrong workspace or server key)"
        ) from error
    return plain.decode("utf-8")
