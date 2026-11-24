"""Worker settings, read from environment variables and the repo-root .env file.

pydantic-settings maps each field to an env var of the same name (case-insensitive), so
`max_steps` comes from MAX_STEPS. Real environment variables win over .env values.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from worker.deep.config import DEEP_MODELS

REPO_ROOT = Path(__file__).resolve().parents[4]  # apps/worker/src/worker/config.py → repo root

# claude-cli: the owner's local testing only (Pro login, no API key); see llm/claude_cli.py.
PROVIDERS = ("claude", "ollama", "openai-compat", "claude-cli", "fake")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # DATABASE_URL: the admin connection (migrations, tests, maintenance commands like bench).
    # WORKER_DATABASE_URL: the worker's own role, ata_worker (run 5, K3); falls back to
    # DATABASE_URL until the roles exist.
    database_url: str = "postgresql://agent:agent@localhost:5432/agent"
    worker_database_url: str = ""

    # AI provider (see .env.example)
    llm_provider: str = ""
    # SecretStr: printing or logging the settings shows '**********', never the key.
    anthropic_api_key: SecretStr = SecretStr("")
    agent_model: str = "claude-haiku-5-5"  # run 7: the default agent (D91); Sonnet is "thorough"
    cheap_model: str = "claude-haiku-5-5"
    # LLM_PROVIDER=claude-cli (run 6): full model IDs, never an alias like "sonnet", so a result
    # says exactly which model ran. The benchmark refuses to start on an alias.
    claude_cli_model: str = "claude-haiku-5-5"
    claude_cli_cheap_model: str = "claude-haiku-5-5"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3-vl:8b-instruct"
    # Any OpenAI-style chat completions API (OpenAI, Gemini, OpenRouter, Groq, LM Studio, vLLM,
    # Ollama's /v1). Prices are USD per million tokens, for the cost budget; 0 if unknown.
    openai_compat_base_url: str = ""
    openai_compat_api_key: SecretStr = SecretStr("")
    openai_compat_model: str = ""
    openai_compat_cheap_model: str = ""
    openai_compat_input_price: float = 0.0
    openai_compat_output_price: float = 0.0
    # Benchmark judge: the model that matches reports to planted bugs. Empty = the agent's own
    # provider / cheap model, which makes scores of different models hard to compare.
    judge_provider: str = ""
    # Decrypts workspace model API keys (32 random bytes, base64); shared with the web app.
    model_keys_secret: SecretStr = SecretStr("")
    # LLM_PROVIDER=fake only: the agent's tool calls as JSON, [["click", {"element_id": 1}], ...].
    # Lets the end-to-end test run a real worker whose agent acts, without a model.
    fake_script: str = ""
    judge_model: str = ""
    # Reviewer (run 5, K2): a stronger model that decides on flagged steps and on the final list
    # of candidate bugs, while the explorer (LLM_PROVIDER) drives the browser. Both empty = no
    # reviewer; only REVIEWER_MODEL = the explorer's provider with that model.
    reviewer_provider: str = ""
    reviewer_model: str = ""
    # False for a reviewer model that can't read images (qwen3:14b): it gets text only.
    reviewer_vision: bool = True

    # Run 7, M3: a target's specs, embedded locally and retrieved per page (worker/specs.py).
    # Off until the holdout measurement shows specs help (D97); `bench --specs` turns it on.
    use_specs: bool = False
    embedding_model: str = "nomic-embed-text"

    # Run budgets, enforced by the worker
    max_steps: int = 40
    max_run_seconds: int = 480
    max_run_cost_usd: float = 1.00
    max_repeated_actions: int = 3
    # A benchmark stops when its runs' API-equivalent cost reaches this (run 6): a guard against
    # a runaway loop on the owner's plan, not a measurement setting. 0 = no cap.
    bench_max_cost_usd: float = 5.00

    # Deep mode (run 9, worker/deep): quality first. Steps and time bound a run; there is no
    # separate cost cap (customers pay with their own key, D111). DEEP_AUTH=api uses the
    # workspace's (or the worker's) API key; DEEP_AUTH=cli uses this machine's Claude login, for
    # the owner's local evaluation only. Screenshots go to the model as JPEG, at most this wide.
    deep_max_steps: int = 400
    deep_max_seconds: int = 3600
    deep_auth: Literal["api", "cli"] = "api"
    deep_model: str = "claude-sonnet-5-5"
    deep_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    deep_screenshot_max_width: int = 1280
    deep_screenshot_quality: int = Field(default=75, ge=1, le=100)

    @field_validator("deep_model")
    @classmethod
    def _deep_model_known(cls, value: str) -> str:
        if value not in DEEP_MODELS:
            raise ValueError(f"DEEP_MODEL must be one of {DEEP_MODELS}, got {value!r}")
        return value

    # Passive scan
    max_pages: int = 30
    max_depth: int = 5
    review_pages: int = 6  # pages whose screenshot the model reviews for visual problems

    # Targets and storage
    demo_url: str = "http://localhost:5173"
    clean_demo_url: str = "http://localhost:5174"
    # The holdout app (apps/demo2): benchmark only, never used to tune prompts.
    demo2_url: str = "http://localhost:5175"
    clean_demo2_url: str = "http://localhost:5176"

    # Run 8, N4: open-source apps started on this Mac for the real-world benchmark
    # (comma-separated URLs). Only with DEV_MODE=true do they count as our own local apps.
    local_app_urls: str = ""

    def demo_urls(self) -> list[str]:
        """Our own demo apps: the only targets where interactive tests need no verified domain.
        In dev mode, also the local apps of LOCAL_APP_URLS (the real-world benchmark)."""
        urls = [self.demo_url, self.clean_demo_url, self.demo2_url, self.clean_demo2_url]
        if self.dev_mode:
            urls += [u.strip() for u in self.local_app_urls.split(",") if u.strip()]
        return urls

    # Off unless DEV_MODE=true is set explicitly: a deployment that forgets the variable must
    # not let the browser reach localhost (fail safe).
    dev_mode: bool = False
    data_dir: str = "apps/worker/data"
    # Run 4, J6: STORAGE=s3 stores screenshots in an S3-compatible bucket (MinIO, S3, R2).
    storage: str = "local"
    s3_bucket: str = "screenshots"
    s3_region: str = "us-east-1"
    s3_endpoint: str = ""
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")

    def provider(self) -> str:
        """The LLM provider to use: LLM_PROVIDER if set, else claude with a key, else fake."""
        if self.llm_provider:
            if self.llm_provider not in PROVIDERS:
                raise ValueError(
                    f"LLM_PROVIDER must be one of {PROVIDERS}, got {self.llm_provider!r}"
                )
            return self.llm_provider
        return "claude" if self.anthropic_api_key.get_secret_value() else "fake"

    def sqlalchemy_url(self) -> str:
        """The worker's connection (WORKER_DATABASE_URL, else DATABASE_URL) for SQLAlchemy."""
        return _with_driver(self.worker_database_url or self.database_url)

    def admin_sqlalchemy_url(self) -> str:
        """The admin connection (DATABASE_URL): test databases and maintenance commands."""
        return _with_driver(self.database_url)

    def data_path(self) -> Path:
        """Absolute path for screenshots (a relative DATA_DIR is resolved from the repo root)."""
        path = Path(self.data_dir)
        return path if path.is_absolute() else REPO_ROOT / path


def realworld_dir() -> Path:
    """Where the real-world benchmark's apps are cloned (run 8, N4): outside the repo, and never
    reachable by claude-cli (their git history holds the fix commits)."""
    import os

    return Path(os.environ.get("REALWORLD_DIR", Path.home() / "ai-test-agent-realworld"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _with_driver(url: str) -> str:
    """A Postgres URL in the form SQLAlchemy needs: it has to name the driver (psycopg 3)."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url
