import json

import pytest
from app.core.config import Settings
from app.core.ssrf import OutboundBlocked, host_allowed, validate_outbound_url
from app.domain.curl_parser import CurlParseError, parse_curl, redact_curl
from app.domain.templates import (
    MissingSecret,
    input_schema_for,
    mask_secrets,
    render,
    secrets_in,
    variables_in,
)

CURL = """curl https://api.example.com/v1/process \\
  -H "Authorization: Bearer sk-live-SECRET123456" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "example",
    "api_key": "inline-secret-value"
  }'"""


def test_parse_curl_extracts_method_url_headers_body_and_secrets() -> None:
    parsed = parse_curl(CURL)
    assert parsed.method == "POST" and parsed.url == "https://api.example.com/v1/process"
    assert parsed.headers["Authorization"] == "Bearer {{secrets.api_key}}"
    assert parsed.headers["Content-Type"] == "application/json"
    assert parsed.body_kind == "json"
    body = json.loads(parsed.body or "{}")
    assert body["prompt"] == "example" and body["api_key"] == "{{secrets.api_key}}"
    names = {(s.name, s.location, s.value) for s in parsed.secrets}
    assert ("api_key", "header", "sk-live-SECRET123456") in names
    assert ("api_key", "body", "inline-secret-value") in names
    assert "SECRET123456" not in json.dumps(parsed.headers) and "inline-secret-value" not in (
        parsed.body or ""
    )
    assert parsed.summary() == {
        "method": "POST",
        "endpoint": "/v1/process",
        "host": "api.example.com",
        "auth": "Secret configured",
        "body": "JSON",
        "status": "Ready",
    }
    assert "SECRET123456" not in redact_curl(CURL, parsed.secrets)


def test_parse_curl_variants() -> None:
    q = parse_curl("curl 'https://maps.example.com/geocode?address=Delhi&key=AIzaSECRET' -X GET")
    assert (
        q.method == "GET"
        and q.query == {"address": "Delhi", "key": "{{secrets.key}}"}
        and q.secrets[0].value == "AIzaSECRET"
    )
    basic = parse_curl("curl -u alice:hunter2 https://svc.example.com/x -d 'a=1&b=2'")
    assert (
        basic.headers["Authorization"] == "Basic {{secrets.basic_auth}}"
        and basic.body_kind == "form"
        and basic.method == "POST"
    )
    hdr = parse_curl('curl -X PUT https://svc.example.com/x -H "X-Api-Key: abc123def" --json \'{"a":1}\'')
    assert (
        hdr.method == "PUT"
        and hdr.headers["X-Api-Key"] == "{{secrets.x_api_key}}"
        and hdr.headers["Accept"] == "application/json"
    )
    get = parse_curl("curl -G https://svc.example.com/search -d q=poster")
    assert (
        get.method == "GET"
        and get.url == "https://svc.example.com/search"
        and get.query == {"q": "poster"}
        and get.body is None
    )
    plain = parse_curl("curl svc.example.com/health")
    assert plain.url == "https://svc.example.com/health" and any("no credential" in w for w in plain.warnings)
    with pytest.raises(CurlParseError):
        parse_curl("curl -H 'Only: header'")


def test_templates_render_and_escape() -> None:
    body = '{"prompt": "{{prompt}}", "workspace_id": "{{workspace_id}}", "meta": {{meta}}}'
    out = render(
        body,
        variables={"prompt": 'say "hi"\nnow', "workspace_id": "ws1", "meta": {"a": 1}},
        secrets={},
        json_mode=True,
    )
    assert json.loads(out) == {"prompt": 'say "hi"\nnow', "workspace_id": "ws1", "meta": {"a": 1}}
    assert variables_in(body, "Bearer {{secrets.api_key}}") == ["prompt", "workspace_id", "meta"]
    assert secrets_in("Bearer {{secrets.api_key}}", "{{secrets.other}}") == ["api_key", "other"]
    assert render("Bearer {{secrets.api_key}}", variables={}, secrets={"api_key": "K1"}) == "Bearer K1"
    with pytest.raises(MissingSecret):
        render("{{secrets.nope}}", variables={}, secrets={})
    assert (
        mask_secrets("Authorization: Bearer K1234567", {"k": "K1234567"}) == "Authorization: Bearer ••••••••"
    )
    assert input_schema_for(["prompt", "asset.url"])["properties"].keys() == {"prompt", "asset"}


def _settings(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[arg-type]


def test_ssrf_guard_blocks_private_and_allows_public() -> None:
    public = lambda host: ["93.184.216.34"]  # noqa: E731
    private = lambda host: ["10.0.0.5"]  # noqa: E731
    assert (
        validate_outbound_url("https://api.example.com/v1", _settings(), resolver=public) == "api.example.com"
    )
    for bad in (
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/x",
        "https://user:pw@api.example.com/x",
        "ftp://api.example.com/x",
        "https://svc.internal/x",
    ):
        with pytest.raises(OutboundBlocked):
            validate_outbound_url(bad, _settings(), resolver=public)
    with pytest.raises(OutboundBlocked):
        validate_outbound_url("https://evil.example.com/x", _settings(), resolver=private)
    with pytest.raises(OutboundBlocked):
        validate_outbound_url(
            "http://api.example.com/x", _settings(outbound_allow_http=False), resolver=public
        )
    assert validate_outbound_url(
        "http://api.example.com/x", _settings(outbound_allow_http=True), resolver=public
    )
    allow = _settings(outbound_allowed_hosts="example.com, svc.internal-api.net")
    assert validate_outbound_url("https://api.example.com/x", allow, resolver=public)
    with pytest.raises(OutboundBlocked):
        validate_outbound_url("https://api.other.com/x", allow, resolver=public)
    assert host_allowed("a.b.example.com", ["example.com"]) and not host_allowed(
        "example.com.evil", ["example.com"]
    )
