from tests.conftest import requires_db

pytestmark = requires_db


async def test_healthz_root_and_prefixed(client) -> None:  # type: ignore[no-untyped-def]
    for path in ("/healthz", "/api/v1/healthz"):
        res = await client.get(path)
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert res.headers["x-request-id"]


async def test_readyz_reports_checks(client) -> None:  # type: ignore[no-untyped-def]
    res = await client.get("/readyz")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] is True
    assert body["checks"]["storage"] is True


async def test_error_envelope_and_request_id_propagation(client) -> None:  # type: ignore[no-untyped-def]
    res = await client.get("/api/v1/me", headers={"X-Request-Id": "abc123"})
    assert res.status_code == 401
    body = res.json()["error"]
    assert body["code"] == "missing_token"
    assert body["request_id"] == "abc123"
    assert res.headers["x-request-id"] == "abc123"
    assert res.headers["www-authenticate"] == "Bearer"


async def test_validation_error_envelope(client) -> None:  # type: ignore[no-untyped-def]
    res = await client.post("/api/v1/auth/login", json={"email": "nope", "password": "short"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_failed"
