#!/usr/bin/env sh
# Runs migrations before the API (or worker) starts. Fails loudly instead of serving a stale schema.
set -eu
if [ "${SKIP_MIGRATIONS:-false}" != "true" ]; then
  echo "[entrypoint] applying database migrations"
  python -m alembic upgrade head
fi
if [ "${STORAGE_BACKEND:-local}" = "s3" ] && [ "${ENSURE_BUCKET:-true}" = "true" ]; then
  python - <<'PY'
import asyncio
from app.adapters.registry import build_storage
from app.core.config import get_settings
s = build_storage(get_settings())
ensure = getattr(s, "ensure_bucket", None)
if ensure:
    asyncio.run(ensure())
    print("[entrypoint] bucket ready")
PY
fi
exec "$@"
