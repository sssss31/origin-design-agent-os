"""Structured logging with secret redaction.

Every log line passes through `redact()` so that keys such as `api_key`, `authorization`
or `password`, and values that look like bearer tokens or `sk-…` keys, never reach stdout,
a log aggregator or a trace.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

from app.core.config import Settings

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "api_key",
    "apikey",
    "secret",
    "secret_key",
    "secret_value",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "set-cookie",
    "encryption_key",
    "jwt_secret",
    "ciphertext",
}
SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
)
REDACTED = "[REDACTED]"


def redact(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact sensitive keys and secret-looking strings."""
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, dict):
        return {k: redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(redact(v) for v in value)
    if isinstance(value, str):
        out = value
        for pattern in SECRET_VALUE_PATTERNS:
            out = pattern.sub(REDACTED, out)
        return out
    return value


def _redact_processor(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    return dict(redact(dict(event_dict)))


def configure_logging(settings: Settings) -> None:
    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
    renderer: Any
    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=False,
    )
    logging.basicConfig(
        level=level, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout, force=True
    )
    for noisy in ("uvicorn.access", "botocore", "boto3", "httpx"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
