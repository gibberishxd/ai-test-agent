"""Signed webhooks: tell a workspace's endpoint when a run finishes (run 4, J3).

- When a run reaches a final status, `enqueue_run_finished` adds one delivery per enabled
  endpoint of its workspace (the payload is fixed at that moment).
- `deliver_due` sends the deliveries whose time has come, claimed with FOR UPDATE SKIP LOCKED
  so several workers never send the same one.
- Signature: `X-ATA-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>.<body>")>`.
  The receiver recomputes it with its secret and rejects old timestamps (5 minutes), so a
  captured request can't be replayed later and a changed body doesn't verify.
- SSRF: the URL is checked like every browser request (no private, internal or metadata
  addresses) and the POST goes through the same guard proxy, which connects only to the
  address it checked (no DNS rebinding). A blocked URL fails at once: retrying can't help.
- Retries: a non-2xx answer or a network error is retried after 30 s, 2 min, 8 min, 32 min and
  ~2 h; after 6 attempts the delivery is marked failed. Every attempt is in the delivery log.
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from worker.config import Settings
from worker.db.models import Bug, Run, WebhookDelivery, WebhookEndpoint
from worker.safety.network import NetworkGuard
from worker.safety.proxy import GuardProxy
from worker.secret_box import decrypt_secret, server_key

log = logging.getLogger(__name__)

BACKOFF_S = [30, 120, 480, 1920, 7680]
MAX_ATTEMPTS = len(BACKOFF_S) + 1
TIMEOUT_S = 10
TOLERANCE_S = 300
BATCH = 10
SEVERITIES = ["critical", "high", "medium", "low"]


def signature_header(secret: str, timestamp: int, body: bytes) -> str:
    signed = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify_signature(
    secret: str, header: str, body: bytes, now: float | None = None, tolerance_s: int = TOLERANCE_S
) -> bool:
    """What a receiver does (docs/API.md has it in TypeScript too)."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs((now if now is not None else time.time()) - timestamp) > tolerance_s:
        return False
    expected = signature_header(secret, timestamp, body).split("v1=")[1]
    return hmac.compare_digest(expected, parts.get("v1", ""))


def run_payload(session: Session, run: Run) -> dict:
    """The run as the API's status shows it, plus counts of what it reports."""
    reported = [
        b
        for b in session.scalars(select(Bug).where(Bug.run_id == run.id))
        if b.status != "dismissed" and not b.suppressed
    ]
    duration = (
        round((run.finished_at - run.started_at).total_seconds())
        if run.started_at and run.finished_at
        else None
    )
    return {
        "id": str(run.id),
        "status": str(run.status),
        "target_url": run.target_url,
        "mode": str(run.mode),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_s": duration,
        "counts": {s: sum(1 for b in reported if str(b.severity) == s) for s in SEVERITIES},
        "error": run.error,
    }


def enqueue_run_finished(session: Session, run: Run) -> int:
    """One delivery per enabled endpoint of the run's workspace. Returns how many."""
    endpoints = session.scalars(
        select(WebhookEndpoint).where(
            WebhookEndpoint.workspace_id == run.workspace_id, WebhookEndpoint.enabled.is_(True)
        )
    ).all()
    data = run_payload(session, run) if endpoints else None
    for endpoint in endpoints:
        session.add(
            WebhookDelivery(
                endpoint_id=endpoint.id,
                run_id=run.id,
                event="run.finished",
                payload={
                    "event": "run.finished",
                    "created_at": datetime.now(UTC).isoformat(),
                    "data": data,
                },
            )
        )
    session.commit()
    return len(endpoints)


def deliver_due(
    sessions: sessionmaker[Session],
    settings: Settings,
    allowed_local: set[tuple[str, int]] | None = None,
) -> int:
    """Send the deliveries that are due. Returns how many were attempted.

    `allowed_local`: (host, port) pairs exempt from the private-address rule; only tests (a
    local receiver) pass it. Production sends to public addresses only."""
    with sessions() as session:
        due = session.scalars(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status == "pending",
                WebhookDelivery.next_attempt_at <= datetime.now(UTC),
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(BATCH)
            .with_for_update(skip_locked=True)
        ).all()
        if not due:
            return 0
        guard = NetworkGuard(allowed_local=set(allowed_local or ()))
        key = server_key(settings.model_keys_secret.get_secret_value())
        with (
            GuardProxy(guard) as proxy,
            httpx.Client(proxy=proxy.url, timeout=TIMEOUT_S, follow_redirects=False) as http,
        ):
            for delivery in due:
                _attempt(session, http, guard, key, delivery)
        session.commit()
        return len(due)


def _attempt(session, http: httpx.Client, guard: NetworkGuard, key: bytes, delivery) -> None:
    endpoint = session.get(WebhookEndpoint, delivery.endpoint_id)
    delivery.attempts += 1
    blocked = guard.check(endpoint.url)
    if blocked:
        delivery.status, delivery.last_error = "failed", f"blocked: {blocked}"
        return
    body = json.dumps({"id": str(delivery.id), **delivery.payload}, separators=(",", ":")).encode()
    secret = decrypt_secret(endpoint.secret_ciphertext, str(endpoint.workspace_id), key)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AI-Test-Agent-Webhooks/1",
        "X-ATA-Event": delivery.event,
        "X-ATA-Delivery": str(delivery.id),
        "X-ATA-Signature": signature_header(secret, int(time.time()), body),
    }
    try:
        response = http.post(endpoint.url, content=body, headers=headers)
        delivery.last_status_code = response.status_code
        ok = 200 <= response.status_code < 300
        delivery.last_error = None if ok else f"HTTP {response.status_code}"
    except httpx.HTTPError as error:
        ok, delivery.last_error = False, f"{type(error).__name__}: {str(error)[:200]}"
    if ok:
        delivery.status, delivery.delivered_at = "delivered", datetime.now(UTC)
    elif delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = "failed"
    else:
        wait = BACKOFF_S[delivery.attempts - 1]
        delivery.next_attempt_at = datetime.now(UTC) + timedelta(seconds=wait)
