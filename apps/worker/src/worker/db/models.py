"""SQLAlchemy mirror of the Prisma schema (apps/web/prisma/schema.prisma).

Prisma owns the schema and its migrations; these classes only describe the existing tables so
Python can read and write them. tests/test_db_models.py fails if the two drift apart.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    STOPPED = "stopped"


class RunMode(StrEnum):
    PASSIVE = "passive"
    INTERACTIVE = "interactive"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BugSource(StrEnum):
    DETERMINISTIC = "deterministic"
    AGENT = "agent"


class BugStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


def _pg_enum(enum: type[StrEnum], name: str) -> ENUM:
    # create_type=False: the type already exists (Prisma's migration created it).
    return ENUM(*[member.value for member in enum], name=name, create_type=False)


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(TIMESTAMP(timezone=True, precision=3), server_default=func.now())


def _timestamp() -> Any:
    return TIMESTAMP(timezone=True, precision=3)


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    monthly_run_quota: Mapped[int] = mapped_column(server_default=text("50"))
    verification_token: Mapped[str] = mapped_column(
        unique=True, server_default=text("replace(gen_random_uuid()::text, '-', '')")
    )
    created_at: Mapped[datetime] = _created_at()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str | None]
    image: Mapped[str | None]
    email_verified: Mapped[datetime | None] = mapped_column(_timestamp())
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    created_at: Mapped[datetime] = _created_at()


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    target_url: Mapped[str]
    mode: Mapped[str] = mapped_column(_pg_enum(RunMode, "run_mode"), server_default="passive")
    focus: Mapped[str | None]
    status: Mapped[str] = mapped_column(_pg_enum(RunStatus, "run_status"), server_default="queued")
    stop_requested: Mapped[bool] = mapped_column(server_default=text("false"))
    claimed_by: Mapped[str | None]
    provider: Mapped[str | None]
    model: Mapped[str | None]
    pages_visited: Mapped[int] = mapped_column(server_default=text("0"))
    step_count: Mapped[int] = mapped_column(server_default=text("0"))
    input_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    cost_usd: Mapped[float] = mapped_column(server_default=text("0"))
    error: Mapped[str | None]
    summary: Mapped[dict | None] = mapped_column(JSONB)
    share_token: Mapped[str | None] = mapped_column(unique=True)
    # The workspace model this run uses; None = the worker's own model.
    model_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_configs.id")
    )
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(_timestamp())
    finished_at: Mapped[datetime | None] = mapped_column(_timestamp())
    heartbeat_at: Mapped[datetime | None] = mapped_column(_timestamp())  # the worker's lease
    # Run 4, J3: budgets a CI caller can lower (never raise above the worker's limits), and the
    # API key that started the run.
    max_steps: Mapped[int | None]
    max_seconds: Mapped[int | None]
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("api_keys.id"))

    steps: Mapped[list["Step"]] = relationship(back_populates="run", order_by="Step.index")
    bugs: Mapped[list["Bug"]] = relationship(back_populates="run")


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[uuid.UUID] = _id()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"))
    index: Mapped[int]
    action: Mapped[str]
    args: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    reasoning: Mapped[str | None]
    url: Mapped[str | None]
    screenshot: Mapped[str | None]
    events: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'"))
    blocked: Mapped[bool] = mapped_column(server_default=text("false"))
    block_reason: Mapped[str | None]
    input_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(server_default=text("0"))
    cost_usd: Mapped[float] = mapped_column(server_default=text("0"))
    created_at: Mapped[datetime] = _created_at()

    run: Mapped[Run] = relationship(back_populates="steps")


class Bug(Base):
    __tablename__ = "bugs"

    id: Mapped[uuid.UUID] = _id()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"))
    title: Mapped[str]
    severity: Mapped[str] = mapped_column(_pg_enum(Severity, "severity"))
    category: Mapped[str]
    page_url: Mapped[str]
    expected: Mapped[str | None]
    actual: Mapped[str | None]
    repro_steps: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'"))
    evidence: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    reasoning: Mapped[str | None]
    screenshot: Mapped[str | None]
    # Prisma creates list columns as nullable (Postgres arrays), so the mirror says so too.
    step_indexes: Mapped[list[int] | None] = mapped_column(
        ARRAY(Integer), server_default=text("'{}'")
    )
    source: Mapped[str] = mapped_column(_pg_enum(BugSource, "bug_source"))
    status: Mapped[str] = mapped_column(
        _pg_enum(BugStatus, "bug_status"), server_default="candidate"
    )
    dismiss_reason: Mapped[str | None]
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created_at()

    run: Mapped[Run] = relationship(back_populates="bugs")


class BenchmarkResult(Base):
    __tablename__ = "benchmark_results"

    id: Mapped[uuid.UUID] = _id()
    provider: Mapped[str]
    model: Mapped[str]
    git_commit: Mapped[str]
    runs_buggy: Mapped[int]
    recall: Mapped[float]
    precision: Mapped[float]
    false_alarms: Mapped[float]
    avg_cost_usd: Mapped[float]
    avg_duration_s: Mapped[float]
    ai_recall: Mapped[float | None]
    holdout_runs_buggy: Mapped[int | None]
    holdout_recall: Mapped[float | None]
    holdout_ai_recall: Mapped[float | None]
    holdout_precision: Mapped[float | None]
    holdout_false_alarms: Mapped[float | None]
    judge: Mapped[str | None]
    rescore_commit: Mapped[str | None]
    details: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    created_at: Mapped[datetime] = _created_at()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String)
    target_url: Mapped[str | None]
    mode: Mapped[str | None] = mapped_column(_pg_enum(RunMode, "run_mode"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default=text("'{}'"))
    created_at: Mapped[datetime] = _created_at()


class Account(Base):
    """Auth.js sign-in accounts. Unused by the worker; mirrored so the drift test is complete."""

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str]
    provider: Mapped[str]
    provider_account_id: Mapped[str]
    refresh_token: Mapped[str | None]
    access_token: Mapped[str | None]
    expires_at: Mapped[int | None]
    token_type: Mapped[str | None]
    scope: Mapped[str | None]
    id_token: Mapped[str | None]
    session_state: Mapped[str | None]


class VerificationToken(Base):
    __tablename__ = "verification_tokens"

    identifier: Mapped[str] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(primary_key=True)
    expires: Mapped[datetime] = mapped_column(_timestamp())


class Domain(Base):
    """A domain a workspace has asked to test interactively; verified_at set once proven."""

    __tablename__ = "domains"

    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    hostname: Mapped[str]
    verified_at: Mapped[datetime | None] = mapped_column(_timestamp())
    method: Mapped[str | None]
    created_at: Mapped[datetime] = _created_at()


class ModelConfig(Base):
    """A workspace's own model (web: lib/model-configs.ts). The key is AES-GCM encrypted."""

    __tablename__ = "model_configs"

    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    label: Mapped[str]
    provider: Mapped[str]
    base_url: Mapped[str | None]
    model: Mapped[str]
    cheap_model: Mapped[str | None]
    api_key_ciphertext: Mapped[str | None]
    api_key_last4: Mapped[str | None]
    input_price: Mapped[float] = mapped_column(server_default=text("0"))
    output_price: Mapped[float] = mapped_column(server_default=text("0"))
    is_default: Mapped[bool] = mapped_column(server_default=text("false"))
    probe: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class LoginSetup(Base):
    """How the worker signs in to a target before the agent starts (web: lib/login-setups.ts).

    A TEST account only. The password and a recorded storage state are AES-GCM encrypted like
    model keys (workspace id as associated data) and never reach the model, logs or reports.
    """

    __tablename__ = "login_setups"

    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    origin: Mapped[str]  # scheme://host[:port] of the target
    kind: Mapped[str]  # "form" or "storage_state"
    login_url: Mapped[str | None]
    username: Mapped[str | None]
    password_ciphertext: Mapped[str | None]
    username_selector: Mapped[str | None]
    password_selector: Mapped[str | None]
    submit_selector: Mapped[str | None]
    success_selector: Mapped[str | None]
    storage_state_ciphertext: Mapped[str | None]
    check_requested_at: Mapped[datetime | None] = mapped_column(_timestamp())
    last_check: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _created_at()


class ApiKey(Base):
    """A workspace's key for the public API (web: lib/api-keys.ts). Only a SHA-256 hash is
    stored; the key is shown once when it's created."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str]
    prefix: Mapped[str]  # the first characters, to tell keys apart ("ata_k8Fz…")
    key_hash: Mapped[str]
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    last_used_at: Mapped[datetime | None] = mapped_column(_timestamp())
    revoked_at: Mapped[datetime | None] = mapped_column(_timestamp())
    created_at: Mapped[datetime] = _created_at()


class ApiRateWindow(Base):
    """Requests per API key per minute (a fixed-window rate limit that works across servers)."""

    __tablename__ = "api_rate_windows"

    api_key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("api_keys.id"), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(_timestamp(), primary_key=True)
    count: Mapped[int] = mapped_column(server_default=text("0"))


class WebhookEndpoint(Base):
    """Where a workspace wants run results POSTed. The signing secret is AES-GCM encrypted
    (the worker needs it to sign), shown once when created."""

    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    url: Mapped[str]
    secret_ciphertext: Mapped[str]
    enabled: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = _created_at()


class WebhookDelivery(Base):
    """One event sent (or being retried) to one endpoint: the delivery log."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = _id()
    endpoint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webhook_endpoints.id"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id"))
    event: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(_timestamp(), server_default=func.now())
    last_status_code: Mapped[int | None]
    last_error: Mapped[str | None]
    delivered_at: Mapped[datetime | None] = mapped_column(_timestamp())
    created_at: Mapped[datetime] = _created_at()
