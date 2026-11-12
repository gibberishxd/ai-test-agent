"""Signed webhooks when a run finishes (run 4, J3), tested against a local receiver only."""

import base64
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from worker.config import Settings
from worker.db.models import Run, WebhookDelivery, WebhookEndpoint
from worker.llm import FakeClient
from worker.runner import process_next
from worker.webhooks import (
    BACKOFF_S,
    MAX_ATTEMPTS,
    deliver_due,
    signature_header,
    verify_signature,
)

KEY = os.urandom(32)
SECRET = "whsec_test_secret"


def encrypt(plain: str, workspace_id: str) -> str:
    nonce = os.urandom(12)
    return (
        "v1:"
        + base64.b64encode(
            nonce + AESGCM(KEY).encrypt(nonce, plain.encode(), workspace_id.encode())
        ).decode()
    )


# --- signatures --------------------------------------------------------------------------------


def test_the_signature_covers_the_timestamp_and_the_body():
    header = signature_header(SECRET, 1_700_000_000, b'{"a":1}')
    assert header.startswith("t=1700000000,v1=") and len(header.split("v1=")[1]) == 64
    assert verify_signature(SECRET, header, b'{"a":1}', now=1_700_000_010)
    assert not verify_signature(SECRET, header, b'{"a":2}', now=1_700_000_010)  # body changed
    assert not verify_signature("other", header, b'{"a":1}', now=1_700_000_010)  # wrong secret
    assert not verify_signature(
        SECRET, header, b'{"a":1}', now=1_700_000_000 + 301
    )  # replayed late


def test_retries_back_off_and_give_up():
    assert BACKOFF_S == [30, 120, 480, 1920, 7680]
    assert MAX_ATTEMPTS == len(BACKOFF_S) + 1


# --- a local receiver --------------------------------------------------------------------------


class Receiver:
    def __init__(self):
        self.requests: list[dict] = []
        self.status = 200
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                receiver.requests.append({"headers": dict(self.headers), "body": body})
                self.send_response(receiver.status)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/hooks/ata"
        self.allowed = {("127.0.0.1", self.server.server_port)}


@pytest.fixture
def receiver():
    r = Receiver()
    yield r
    r.server.shutdown()


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None, model_keys_secret=base64.b64encode(KEY).decode(), data_dir=str(tmp_path)
    )


def finished_run_with_endpoint(sessions, workspace, url) -> str:
    with sessions() as session:
        session.add(
            WebhookEndpoint(
                workspace_id=workspace.id,
                url=url,
                secret_ciphertext=encrypt(SECRET, str(workspace.id)),
            )
        )
        run = Run(workspace_id=workspace.id, target_url="http://localhost:5173/", mode="passive")
        session.add(run)
        session.commit()
        run_id = run.id
    process_next(sessions, FakeClient())  # noop execute: the run is done
    return run_id


def test_a_finished_run_is_posted_signed_to_the_workspace_endpoint(
    sessions, worker_sessions, workspace, settings, receiver
):
    run_id = finished_run_with_endpoint(sessions, workspace, receiver.url)
    assert deliver_due(worker_sessions, settings, allowed_local=receiver.allowed) == 1

    [request] = receiver.requests
    payload = json.loads(request["body"])
    assert payload["event"] == "run.finished"
    assert payload["data"]["id"] == str(run_id) and payload["data"]["status"] == "done"
    assert request["headers"]["X-ATA-Event"] == "run.finished"
    assert verify_signature(
        SECRET,
        request["headers"]["X-ATA-Signature"],
        request["body"],
        now=datetime.now(UTC).timestamp(),
    )
    with sessions() as session:
        delivery = session.query(WebhookDelivery).one()
        assert (delivery.status, delivery.attempts, delivery.last_status_code) == (
            "delivered",
            1,
            200,
        )
    assert (
        deliver_due(worker_sessions, settings, allowed_local=receiver.allowed) == 0
    )  # nothing left


def test_a_failing_receiver_is_retried_later_then_given_up(
    sessions, worker_sessions, workspace, settings, receiver
):
    receiver.status = 500
    finished_run_with_endpoint(sessions, workspace, receiver.url)
    deliver_due(worker_sessions, settings, allowed_local=receiver.allowed)
    with sessions() as session:
        delivery = session.query(WebhookDelivery).one()
        assert (delivery.status, delivery.attempts, delivery.last_status_code) == (
            "pending",
            1,
            500,
        )
        wait = delivery.next_attempt_at - datetime.now(UTC)
        assert timedelta(seconds=20) < wait <= timedelta(seconds=30)
        delivery.attempts = MAX_ATTEMPTS - 1
        delivery.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    deliver_due(worker_sessions, settings, allowed_local=receiver.allowed)
    with sessions() as session:
        assert session.query(WebhookDelivery).one().status == "failed"


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://127.0.0.1:5432/",
        "http://10.0.0.5/hook",
        "ftp://example.com/",
    ],
)
def test_internal_addresses_are_refused_without_retrying(
    sessions, worker_sessions, workspace, settings, url
):
    finished_run_with_endpoint(sessions, workspace, url)
    deliver_due(worker_sessions, settings)
    with sessions() as session:
        delivery = session.query(WebhookDelivery).one()
        assert delivery.status == "failed" and "blocked" in delivery.last_error


def test_disabled_endpoints_get_nothing(sessions, worker_sessions, workspace, settings, receiver):
    with sessions() as session:
        session.add(
            WebhookEndpoint(
                workspace_id=workspace.id,
                url=receiver.url,
                secret_ciphertext=encrypt(SECRET, str(workspace.id)),
                enabled=False,
            )
        )
        session.add(Run(workspace_id=workspace.id, target_url="http://x/", mode="passive"))
        session.commit()
    process_next(sessions, FakeClient())
    assert deliver_due(worker_sessions, settings, allowed_local=receiver.allowed) == 0
