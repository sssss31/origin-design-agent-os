"""STORAGE_BACKEND=db: uploads survive on serverless hosts (no per-instance /tmp)."""

from __future__ import annotations

from app.adapters.storage.db import DbStorage
from app.core.config import Settings

from tests.conftest import requires_db

pytestmark = requires_db


def test_serverless_defaults_to_database_storage() -> None:
    s = Settings(serverless=True, _env_file=None)
    assert s.storage_backend == "db"
    assert Settings(serverless=True, storage_backend="s3", _env_file=None).storage_backend == "s3"


async def test_db_storage_round_trip_and_signed_download(app, client) -> None:  # type: ignore[no-untyped-def]
    storage = DbStorage(
        app.state.session_factory, signing_key="test-signing-key-1234", public_base_url="/api/v1"
    )
    key = "org/o1/projects/p1/assets/abc-design.png"
    obj = await storage.put(key, b"\x89PNG\r\n\x1a\nhello", content_type="image/png")
    assert obj.size == 13 and await storage.exists(key)
    assert await storage.get(key) == b"\x89PNG\r\n\x1a\nhello"
    # overwrite keeps one row
    await storage.put(key, b"v2", content_type="image/png")
    assert await storage.get(key) == b"v2"

    url = await storage.presign_download(key, expires_in=60, filename="design.png")
    original = app.state.adapters.storage
    app.state.adapters.storage = storage
    try:
        res = await client.get(url)
        assert res.status_code == 200 and res.content == b"v2"
        assert res.headers["content-type"].startswith("image/png")
        assert 'filename="design.png"' in res.headers["content-disposition"]
        tampered = url.replace("signature=", "signature=x")
        assert (await client.get(tampered)).status_code == 403
    finally:
        app.state.adapters.storage = original
    await storage.delete(key)
    assert not await storage.exists(key)
    try:
        await storage.get(key)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass
