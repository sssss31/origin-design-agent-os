import time

import pytest
from app.core.config import Settings
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse battery staple")
    assert not verify_password(h, "wrong")
    assert not verify_password("garbage", "wrong")


def test_access_token_roundtrip_and_type_check() -> None:
    s = Settings(jwt_secret="unit-test-secret-with-at-least-32-characters", _env_file=None)
    token = create_access_token(subject="user-1", settings=s)
    payload = decode_access_token(token, s)
    assert payload["sub"] == "user-1"
    assert payload["typ"] == "access"
    with pytest.raises(TokenError):
        decode_access_token(
            token, Settings(jwt_secret="other-secret-with-at-least-32-characters-x", _env_file=None)
        )


def test_expired_token_rejected() -> None:
    s = Settings(
        jwt_secret="unit-test-secret-with-at-least-32-characters", access_token_ttl_minutes=0, _env_file=None
    )
    token = create_access_token(subject="u", settings=s)
    time.sleep(1.1)
    with pytest.raises(TokenError):
        decode_access_token(token, s)


def test_refresh_tokens_are_random_and_hashed() -> None:
    a, b = generate_refresh_token(), generate_refresh_token()
    assert a != b and len(a) >= 60
    assert hash_token(a) != a and len(hash_token(a)) == 64
