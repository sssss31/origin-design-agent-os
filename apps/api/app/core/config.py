"""Application settings.

Everything operational comes from environment variables (or a local `.env`). Everything
that an admin tunes at runtime (agents, skills, providers, tools, workflows) lives in the
database instead, so it can change without a redeploy.

Production-like profiles (`staging`, `production`) are validated strictly: default
secrets, wildcard CORS, local storage and the inline queue are refused at startup.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRETS = {"", "change-me", "replace-with-a-long-random-secret", "dev-only-not-for-production"}

_HERE = Path(__file__).resolve()
_ENV_FILES = (
    str(_HERE.parents[2] / ".env"),  # apps/api/.env
    str(_HERE.parents[4] / ".env"),  # origin-design-agent-os/.env
)

AppEnv = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    # --- identity of the deployment -------------------------------------------------
    app_env: AppEnv = "development"
    app_name: str = "Origin Design Agent OS"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        description="Comma-separated CORS allowlist. '*' is refused in production.",
    )

    # --- data stores -----------------------------------------------------------------
    database_url: str = "postgresql+psycopg://origin:origin@localhost:5432/origin"
    database_pool_size: int = 10
    database_echo: bool = False
    redis_url: str | None = None

    # --- pluggable adapters (see app/adapters/registry.py) ---------------------------
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: str = ".data/storage"
    object_storage_endpoint: str | None = None
    object_storage_public_endpoint: str | None = None
    object_storage_bucket: str = "origin-assets"
    object_storage_access_key: str | None = None
    object_storage_secret_key: str | None = None
    object_storage_region: str = "auto"
    secret_backend: Literal["fernet", "env"] = "fernet"
    queue_backend: Literal["inline", "redis"] = "inline"
    event_bus_backend: Literal["memory", "redis"] = "memory"
    workflow_scheduler: Literal["sequential", "dag"] = "sequential"
    embeddings_backend: Literal["none", "openai"] = "none"

    # --- security --------------------------------------------------------------------
    jwt_secret: str = "dev-only-not-for-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    encryption_key: str = Field(default="", description="Fernet key used by the fernet secret backend.")
    signed_url_ttl_seconds: int = 300
    max_upload_mb: int = 50

    # --- providers (single-provider V0 convenience; admin-managed providers override) -
    openai_api_key: str | None = None
    openai_agents_trace_include_sensitive_data: bool = False

    # --- observability ---------------------------------------------------------------
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    # --- first-run bootstrap (development only; use the CLI elsewhere) ---------------
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_organization_name: str = "Origin"

    # --------------------------------------------------------------------------------
    @property
    def is_production_like(self) -> bool:
        return self.app_env in {"staging", "production"}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Alembic runs migrations on the async driver too; kept for tooling that needs sync."""
        return self.database_url.replace("+psycopg", "+psycopg")

    @model_validator(mode="after")
    def _validate_profile(self) -> Settings:
        if self.encryption_key:
            try:
                Fernet(self.encryption_key.encode())
            except Exception as exc:  # pragma: no cover - message matters, not the type
                raise ValueError("ENCRYPTION_KEY must be a urlsafe base64 32-byte Fernet key") from exc
        if not self.is_production_like:
            return self
        problems: list[str] = []
        if self.jwt_secret in INSECURE_SECRETS or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be set to a random value of at least 32 characters")
        if self.secret_backend == "fernet" and not self.encryption_key:
            problems.append("ENCRYPTION_KEY is required for the fernet secret backend")
        if self.storage_backend == "local":
            problems.append("STORAGE_BACKEND=local is not allowed; use s3")
        if self.queue_backend == "inline":
            problems.append("QUEUE_BACKEND=inline is not allowed; use redis")
        if self.event_bus_backend == "memory":
            problems.append("EVENT_BUS_BACKEND=memory is not allowed with multiple API replicas; use redis")
        if "*" in self.cors_origins:
            problems.append("ALLOWED_ORIGINS must not contain '*'")
        if self.bootstrap_admin_password:
            problems.append("BOOTSTRAP_ADMIN_PASSWORD must not be set; use `origin-cli bootstrap-admin`")
        if problems:
            raise ValueError(f"Invalid {self.app_env} configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests that change environment variables."""
    get_settings.cache_clear()
