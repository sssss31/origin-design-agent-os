import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_development_defaults_are_permissive() -> None:
    s = Settings(app_env="development", _env_file=None)
    assert s.storage_backend == "local"
    assert s.queue_backend == "inline"
    assert "http://localhost:3000" in s.cors_origins


def test_production_refuses_insecure_defaults() -> None:
    # explicit values: the test process itself exports a valid JWT_SECRET for the API tests
    with pytest.raises(ValidationError) as exc:
        Settings(app_env="production", jwt_secret="dev-only-not-for-production", _env_file=None)
    msg = exc.value.errors()[0]["msg"]
    assert "JWT_SECRET" in msg
    assert "STORAGE_BACKEND=local" in msg
    assert "QUEUE_BACKEND=inline" in msg


def test_production_accepts_hardened_config() -> None:
    s = Settings(
        app_env="production",
        jwt_secret="x" * 48,
        encryption_key="8xrgG-Bh_ScC5uVo4VaiD1D9xLbzfTQbgtS7pl2xOmU=",
        storage_backend="s3",
        queue_backend="redis",
        event_bus_backend="redis",
        redis_url="redis://redis:6379/0",
        allowed_origins="https://app.example.com",
        _env_file=None,
    )
    assert s.is_production_like
    assert s.cors_origins == ["https://app.example.com"]


def test_production_refuses_wildcard_cors_and_env_bootstrap() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="staging",
            jwt_secret="x" * 48,
            encryption_key="8xrgG-Bh_ScC5uVo4VaiD1D9xLbzfTQbgtS7pl2xOmU=",
            storage_backend="s3",
            queue_backend="redis",
            event_bus_backend="redis",
            allowed_origins="*",
            bootstrap_admin_password="hunter22",
            _env_file=None,
        )
    msg = exc.value.errors()[0]["msg"]
    assert "ALLOWED_ORIGINS" in msg
    assert "BOOTSTRAP_ADMIN_PASSWORD" in msg


def test_invalid_fernet_key_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(encryption_key="not-a-key", _env_file=None)
