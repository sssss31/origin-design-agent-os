from app.core.logging import REDACTED, redact


def test_sensitive_keys_are_redacted_recursively() -> None:
    data = {
        "api_key": "sk-abcdefghijklmnop",
        "nested": {"Authorization": "Bearer abcdefghijklmnop", "ok": "value"},
        "list": [{"password": "x"}, "plain"],
    }
    out = redact(data)
    assert out["api_key"] == REDACTED
    assert out["nested"]["Authorization"] == REDACTED
    assert out["nested"]["ok"] == "value"
    assert out["list"][0]["password"] == REDACTED
    assert out["list"][1] == "plain"


def test_secret_looking_values_are_redacted_in_free_text() -> None:
    text = "provider failed with key sk-1234567890abcdef and header Bearer abcdefghij.klmnopqrst"
    out = redact(text)
    assert "sk-1234567890abcdef" not in out
    assert "Bearer abcdefghij" not in out
    assert "provider failed" in out
