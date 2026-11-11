"""Worker settings, read from environment variables and the repo-root .env file.

pydantic-settings maps each field to an env var of the same name (case-insensitive), so
`max_steps` comes from MAX_STEPS. Real environment variables win over .env values.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]  # apps/worker/src/worker/config.py → repo root

# claude-cli: the owner's local testing only (Pro login, no API key); see llm/claude_cli.py.
PROVIDERS = ("claude", "ollama", "openai-compat", "claude-cli", "fake")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql://agent:agent@localhost:5432/agent"

    # AI provider (see .env.example)
    llm_provider: str = ""
    # SecretStr: printing or logging the settings shows '**********', never the key.
    anthropic_api_key: SecretStr = SecretStr("")
    agent_model: str = "claude-sonnet-5-5"
    cheap_model: str = "claude-haiku-5-5"
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

    # Run budgets, enforced by the worker
    max_steps: int = 40
    max_run_seconds: int = 480
    max_run_cost_usd: float = 1.00
    max_repeated_actions: int = 3

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

    def demo_urls(self) -> list[str]:
        """Our own demo apps: the only targets where interactive tests need no verified domain."""
        return [self.demo_url, self.clean_demo_url, self.demo2_url, self.clean_demo2_url]

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
        """DATABASE_URL in the form SQLAlchemy needs: it has to name the driver (psycopg 3)."""
        for prefix in ("postgresql://", "postgres://"):
            if self.database_url.startswith(prefix):
                return "postgresql+psycopg://" + self.database_url[len(prefix) :]
        return self.database_url

    def data_path(self) -> Path:
        """Absolute path for screenshots (a relative DATA_DIR is resolved from the repo root)."""
        path = Path(self.data_dir)
        return path if path.is_absolute() else REPO_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
