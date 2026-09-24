"""Application settings.

Everything operational comes from environment variables (or a local `.env`). Everything
that an admin tunes at runtime (agents, skills, providers, tools, workflows) lives in the
database instead, so it can change without a redeploy.

Production-like profiles (`staging`, `production`) are validated strictly: default
secrets, wildcard CORS, local storage and the inline queue are refused at startup.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field, field_validator, model_validator
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
    serverless: bool = Field(
        default=False,
        description="Hosted as serverless functions (Vercel): no background work after a response, "
        "no connection pool, ephemeral disk. Runs execute inside the SSE request; migrations run "
        "on first request under an advisory lock.",
    )
    auto_migrate: bool | None = Field(
        default=None, description="Run alembic on startup. Defaults to true when SERVERLESS=true."
    )
    single_instance: bool = Field(
        default=False,
        description="Hosted on exactly one API instance (Render/Railway/Fly starter): allows the "
        "inline queue, in-memory event bus and local storage in production.",
    )
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
    default_runs_per_day: int = Field(
        default=500, description="Per-organization run quota (0 = unlimited); org settings override."
    )
    default_max_revisions: int = 1
    stale_run_seconds: int = 900
    rate_limit_per_minute: int = Field(default=240, description="Per-user API rate limit (0 = off).")

    # --- providers (single-provider V0 convenience; admin-managed providers override) -
    openai_api_key: str | None = None
    openai_agents_trace_include_sensitive_data: bool = False
    # --- outbound HTTP (custom REST integrations) --------------------------------------
    outbound_allow_http: bool = Field(
        default=False, description="Allow plain http endpoints for custom integrations (never in production)."
    )
    outbound_allowed_hosts: str = Field(
        default="", description="Comma-separated host allowlist; empty = any public host."
    )
    outbound_max_response_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)
    outbound_default_timeout_seconds: int = Field(default=30, ge=1, le=300)
    provider_retry_attempts: int = Field(
        default=3, ge=1, le=6, description="Bounded retries for retryable provider errors."
    )
    provider_retry_backoff_seconds: float = Field(default=0.5, ge=0.0, le=10.0)

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
    def outbound_allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.outbound_allowed_hosts.split(",") if h.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def migrate_on_startup(self) -> bool:
        return self.serverless if self.auto_migrate is None else self.auto_migrate

    @property
    def fernet_key(self) -> str:
        """ENCRYPTION_KEY may be a real Fernet key or any secret of at least 32 characters (hosting
        platforms generate random strings, not Fernet keys); the latter is derived via SHA-256."""
        raw = self.encryption_key.strip()
        if not raw:
            return ""
        try:
            Fernet(raw.encode())
            return raw
        except Exception:  # noqa: BLE001 - not a Fernet key: derive one deterministically
            return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()).decode()

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        """Managed Postgres (Render, Railway, Neon…) hands out postgres:// URLs; SQLAlchemy needs
        the psycopg driver spelled out."""
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @property
    def sync_database_url(self) -> str:
        """Alembic runs migrations on the async driver too; kept for tooling that needs sync."""
        return self.database_url.replace("+psycopg", "+psycopg")

    @model_validator(mode="after")
    def _serverless_defaults(self) -> Settings:
        if self.serverless and self.local_storage_path == ".data/storage":
            self.local_storage_path = "/tmp/origin-storage"  # noqa: S108  # nosec B108 - only writable path on Vercel
        return self

    @model_validator(mode="after")
    def _validate_profile(self) -> Settings:
        if self.encryption_key and not self.fernet_key == self.encryption_key.strip():
            if len(self.encryption_key.strip()) < 32:
                raise ValueError(
                    "ENCRYPTION_KEY must be a Fernet key or a random secret of at least 32 characters"
                )
        if not self.is_production_like:
            return self
        problems: list[str] = []
        if self.jwt_secret in INSECURE_SECRETS or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be set to a random value of at least 32 characters")
        if self.secret_backend == "fernet" and not self.encryption_key:
            problems.append("ENCRYPTION_KEY is required for the fernet secret backend")
        if not (self.single_instance or self.serverless):
            if self.storage_backend == "local":
                problems.append("STORAGE_BACKEND=local is not allowed; use s3 (or SINGLE_INSTANCE=true)")
            if self.queue_backend == "inline":
                problems.append("QUEUE_BACKEND=inline is not allowed; use redis (or SINGLE_INSTANCE=true)")
            if self.event_bus_backend == "memory":
                problems.append(
                    "EVENT_BUS_BACKEND=memory is not allowed with multiple API replicas; use redis "
                    "(or SINGLE_INSTANCE=true)"
                )
        if "*" in self.cors_origins:
            problems.append("ALLOWED_ORIGINS must not contain '*'")
        if self.outbound_allow_http:
            problems.append("OUTBOUND_ALLOW_HTTP must be false; custom integrations must use https")
        if self.bootstrap_admin_password and len(self.bootstrap_admin_password) < 16:
            problems.append(
                "BOOTSTRAP_ADMIN_PASSWORD must be at least 16 characters (it only creates the first "
                "admin; change it after the first login) or unset — use `origin-cli bootstrap-admin`"
            )
        if problems:
            raise ValueError(f"Invalid {self.app_env} configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests that change environment variables."""
    get_settings.cache_clear()
