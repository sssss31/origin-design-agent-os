from tests.conftest import requires_db

pytestmark = requires_db


async def test_login_me_refresh_logout_flow(client, make_user) -> None:  # type: ignore[no-untyped-def]
    actor = await make_user("alice@example.com")
    me = await actor.get("/api/v1/me")
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["memberships"][0]["role"] == "member"
    assert body["capabilities"]["admin_console"] is False
    assert "password" not in str(body)

    # refresh rotates: old token is revoked, new one works
    res = await client.post("/api/v1/auth/refresh", json={"refresh_token": actor.refresh_token})
    assert res.status_code == 200, res.text
    new_pair = res.json()
    assert new_pair["refresh_token"] != actor.refresh_token
    reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": actor.refresh_token})
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "refresh_token_reused"
    # reuse detection revoked the whole family, including the new token
    after = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_pair["refresh_token"]})
    assert after.status_code == 401

    # logout revokes a fresh token
    login = await client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": "Password123!"}
    )
    fresh = login.json()["refresh_token"]
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": fresh})
    assert out.status_code == 204
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": fresh})).status_code == 401


async def test_bad_credentials_do_not_enumerate(client, make_user) -> None:  # type: ignore[no-untyped-def]
    await make_user("bob@example.com")
    wrong = await client.post(
        "/api/v1/auth/login", json={"email": "bob@example.com", "password": "WrongPass123"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "WrongPass123"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "invalid_credentials"


async def test_tampered_token_rejected(client, make_user) -> None:  # type: ignore[no-untyped-def]
    actor = await make_user("carol@example.com")
    res = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {actor.access_token[:-2]}xx"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_token"


async def test_admin_capability(client, make_user) -> None:  # type: ignore[no-untyped-def]
    from app.domain.roles import Role

    admin = await make_user("root@example.com", role=Role.ADMIN)
    assert (await admin.get("/api/v1/me")).json()["capabilities"]["admin_console"] is True
