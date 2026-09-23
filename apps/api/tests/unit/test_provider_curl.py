import pytest
from app.domain.provider_curl import looks_like_curl, parse_provider_curl

RESPONSES = """curl https://api.openai.com/v1/responses \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer sk-proj-REALKEY0123456789abcdef7Xk2" \\
  -d '{
    "model": "gpt-5",
    "instructions": "You are the Master Design Agent. Create premium healthcare posters.",
    "input": "Create a premium healthcare poster",
    "reasoning": {"effort": "medium"},
    "max_output_tokens": 2000,
    "text": {"format": {"type": "json_schema", "name": "design", "schema": {"type": "object"}}},
    "tools": [{"type": "function", "name": "image_generate"}]
  }'"""
CHAT = """curl https://api.openai.com/v1/chat/completions -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" -d '{"model":"gpt-4.1","temperature":0.4,"messages":[{"role":"system","content":"You resize designs."},{"role":"user","content":"resize to 4:5"}]}'"""


def test_responses_curl_yields_key_model_instructions_and_settings() -> None:
    d = parse_provider_curl(RESPONSES)
    assert (
        d.provider_type == "openai"
        and d.base_url == "https://api.openai.com/v1"
        and d.endpoint_kind == "responses"
    )
    assert d.api_key == "sk-proj-REALKEY0123456789abcdef7Xk2" and not d.key_placeholder
    assert d.model == "gpt-5" and d.instructions.startswith("You are the Master Design Agent")
    assert d.sample_input == "Create a premium healthcare poster"
    assert d.model_settings == {"max_output_tokens": 2000, "reasoning_effort": "medium"}
    assert d.output_schema == {"type": "object"} and d.tools == ["image_generate"]
    assert d.summary()["auth"] == "Secret detected"


def test_chat_curl_with_placeholder_key() -> None:
    d = parse_provider_curl(CHAT)
    assert d.endpoint_kind == "chat" and d.model == "gpt-4.1" and d.api_key is None and d.key_placeholder
    assert d.instructions == "You resize designs." and d.model_settings == {"temperature": 0.4}
    assert any("placeholder" in w for w in d.warnings)


def test_compatible_proxy_and_non_provider() -> None:
    proxy = parse_provider_curl(
        "curl https://llm.internal.example/openai/v1/chat/completions -H 'Authorization: Bearer k-1234567890' -d '{\"model\":\"gpt-4o\"}'"
    )
    assert proxy.provider_type == "openai" and proxy.base_url == "https://llm.internal.example/openai/v1"
    other = parse_provider_curl(
        "curl https://svg.example.com/v1/generate -H 'X-Api-Key: abc123456' -d '{\"prompt\":\"x\"}'"
    )
    assert other.provider_type == "custom" and any("Custom REST" in w for w in other.warnings)
    with pytest.raises(ValueError):
        parse_provider_curl("curl -H 'x: y'")


def test_looks_like_curl() -> None:
    assert looks_like_curl(RESPONSES) and looks_like_curl("curl https://x")
    assert not looks_like_curl("sk-proj-abcdefghijklmnop")
