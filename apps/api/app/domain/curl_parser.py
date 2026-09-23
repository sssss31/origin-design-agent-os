"""Parse a pasted cURL command into method / URL / headers / body and detected credentials.

Credentials found in headers, query strings, `-u user:pass` or common JSON body fields are
returned separately so the caller can move them into encrypted secret storage; the
returned templates only contain `{{secrets.<name>}}` references (spec §8).
"""

from __future__ import annotations

import base64
import json
import re
import shlex
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "apikey",
    "x-apikey",
    "x-auth-token",
    "x-access-token",
    "x-token",
    "x-secret",
    "x-secret-key",
    "x-auth",
    "cookie",
    "ocp-apim-subscription-key",
    "x-goog-api-key",
    "anthropic-api-key",
    "openai-api-key",
}
SECRET_NAME_HINT = re.compile(r"(api[-_]?key|token|secret|password|passwd|auth|credential|signature)", re.I)
SECRET_QUERY_KEYS = {
    "key",
    "api_key",
    "apikey",
    "apiKey",
    "token",
    "access_token",
    "secret",
    "password",
    "auth",
    "sig",
    "signature",
}
DATA_FLAGS = {"-d", "--data", "--data-raw", "--data-binary", "--data-ascii", "--json", "--data-urlencode"}
IGNORED_FLAGS_NO_VALUE = {
    "-s",
    "--silent",
    "-S",
    "--show-error",
    "-L",
    "--location",
    "-k",
    "--insecure",
    "--compressed",
    "-i",
    "--include",
    "-v",
    "--verbose",
    "-f",
    "--fail",
    "-G",
    "--get",
    "-N",
    "--no-buffer",
    "--http1.1",
    "--http2",
    "-#",
    "--progress-bar",
    "--tlsv1.2",
    "--tlsv1.3",
}
IGNORED_FLAGS_WITH_VALUE = {
    "-o",
    "--output",
    "-w",
    "--write-out",
    "--max-time",
    "-m",
    "--connect-timeout",
    "--retry",
    "-x",
    "--proxy",
    "--cacert",
    "--cert",
    "--key",
    "-e",
    "--referer",
    "--resolve",
    "-A",
    "--user-agent",
    "-r",
    "--range",
    "--limit-rate",
}


@dataclass(slots=True)
class DetectedSecret:
    name: str
    value: str
    location: str  # header | query | basic | body | cookie
    hint: str = ""


@dataclass(slots=True)
class ParsedCurl:
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    content_type: str = "application/json"
    body_kind: str = "none"  # none | json | form | raw
    secrets: list[DetectedSecret] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, str]:
        parts = urlsplit(self.url)
        return {
            "method": self.method,
            "endpoint": parts.path or "/",
            "host": parts.netloc,
            "auth": "Secret configured" if self.secrets else "None detected",
            "body": {"json": "JSON", "form": "Form", "raw": "Raw", "none": "None"}[self.body_kind],
            "status": "Ready" if self.url else "Missing URL",
        }


class CurlParseError(ValueError):
    pass


def _tokens(text: str) -> list[str]:
    cleaned = re.sub(r"\\\r?\n", " ", text.strip())
    cleaned = re.sub(r"\^\r?\n", " ", cleaned)  # Windows cmd continuation
    try:
        toks = shlex.split(cleaned, posix=True)
    except ValueError as exc:
        raise CurlParseError(f"could not tokenize cURL: {exc}") from exc
    if not toks:
        raise CurlParseError("empty command")
    if toks[0].lower() in {"curl", "curl.exe"}:
        toks = toks[1:]
    return toks


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "secret"


def parse_curl(text: str) -> ParsedCurl:
    toks = _tokens(text)
    out = ParsedCurl()
    method_explicit: str | None = None
    data_parts: list[str] = []
    urlencode_parts: list[str] = []
    basic: str | None = None
    is_get_with_data = False
    i = 0
    while i < len(toks):
        t = toks[i]

        def value(flag: str = t) -> str:
            nonlocal i
            if i + 1 >= len(toks):
                raise CurlParseError(f"flag {flag} expects a value")
            i += 1
            return toks[i]

        if t in ("-X", "--request"):
            method_explicit = value().upper()
        elif t.startswith("-X") and len(t) > 2:
            method_explicit = t[2:].upper()
        elif t in ("-H", "--header"):
            raw = value()
            if ":" in raw:
                k, v = raw.split(":", 1)
                out.headers[k.strip()] = v.strip()
            elif raw.endswith(";"):
                out.headers[raw[:-1].strip()] = ""
        elif t in DATA_FLAGS:
            v = value()
            if t == "--json":
                out.headers.setdefault("Content-Type", "application/json")
                out.headers.setdefault("Accept", "application/json")
            if t == "--data-urlencode":
                urlencode_parts.append(v)
            else:
                data_parts.append(v[1:] if v.startswith("@") and t == "--data-binary" else v)
        elif t in ("-u", "--user"):
            basic = value()
        elif t == "--url":
            out.url = value()
        elif t in ("-F", "--form", "--form-string"):
            v = value()
            out.body_kind = "form"
            data_parts.append(v)
            out.warnings.append("multipart form fields are stored as raw body; adjust the template if needed")
        elif t in ("-b", "--cookie"):
            out.headers["Cookie"] = value()
        elif t in ("-G", "--get"):
            is_get_with_data = True
        elif t in IGNORED_FLAGS_NO_VALUE:
            pass
        elif t in IGNORED_FLAGS_WITH_VALUE:
            value()
        elif t.startswith("-") and len(t) > 1:
            out.warnings.append(f"ignored unsupported flag {t}")
            if (
                i + 1 < len(toks)
                and not toks[i + 1].startswith("-")
                and not re.match(r"^https?://", toks[i + 1])
            ):
                i += 1
        else:
            if re.match(r"^https?://", t) or not out.url:
                out.url = t
        i += 1

    if not out.url:
        raise CurlParseError("no URL found in the cURL command")
    if not re.match(r"^https?://", out.url):
        out.url = "https://" + out.url

    # body
    body: str | None = None
    if urlencode_parts and not data_parts:
        body = "&".join(urlencode_parts)
        out.body_kind = "form"
        out.headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif data_parts:
        body = (
            "&".join(data_parts)
            if out.body_kind == "form"
            or all("=" in d and not d.strip().startswith(("{", "[")) for d in data_parts)
            and len(data_parts) > 1
            else data_parts[0]
            if len(data_parts) == 1
            else "&".join(data_parts)
        )
    if is_get_with_data and body:
        parts = urlsplit(out.url)
        q = dict(parse_qsl(parts.query, keep_blank_values=True))
        q.update(dict(parse_qsl(body, keep_blank_values=True)))
        out.url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))
        body = None
        method_explicit = method_explicit or "GET"

    out.method = method_explicit or ("POST" if body is not None else "GET")
    ctype = next((v for k, v in out.headers.items() if k.lower() == "content-type"), None)
    if body is not None:
        stripped = body.strip()
        if stripped.startswith(("{", "[")):
            try:
                json.loads(stripped)
                out.body_kind = "json"
                ctype = ctype or "application/json"
            except json.JSONDecodeError:
                out.body_kind = "raw"
        elif out.body_kind != "form":
            out.body_kind = "form" if "=" in stripped and "\n" not in stripped else "raw"
            if out.body_kind == "form":
                ctype = ctype or "application/x-www-form-urlencoded"
        out.body = body
    out.content_type = ctype or (
        "application/json"
        if out.body_kind == "json"
        else "text/plain"
        if out.body_kind == "raw"
        else "application/json"
    )
    if ctype is None and body is not None:
        out.headers["Content-Type"] = out.content_type

    # basic auth → header + secret
    if basic:
        user, _, password = basic.partition(":")
        token = base64.b64encode(basic.encode()).decode()
        out.headers["Authorization"] = "Basic {{secrets.basic_auth}}"
        out.secrets.append(
            DetectedSecret(
                "basic_auth", token, "basic", f"user {user}" + (" with password" if password else "")
            )
        )

    # header secrets
    for name, val in list(out.headers.items()):
        lname = name.lower()
        if "{{secrets." in val:
            continue
        if lname in SECRET_HEADER_NAMES or SECRET_NAME_HINT.search(lname):
            if lname == "authorization":
                scheme, _, credential = val.partition(" ")
                if credential and scheme.lower() in {
                    "bearer",
                    "token",
                    "basic",
                    "apikey",
                    "api-key",
                    "digest",
                }:
                    out.headers[name] = f"{scheme} {{{{secrets.api_key}}}}"
                    out.secrets.append(DetectedSecret("api_key", credential, "header", f"{name}: {scheme}"))
                elif val:
                    out.headers[name] = "{{secrets.api_key}}"
                    out.secrets.append(DetectedSecret("api_key", val, "header", name))
            elif lname == "cookie":
                out.headers[name] = "{{secrets.cookie}}"
                out.secrets.append(DetectedSecret("cookie", val, "cookie", name))
            elif val:
                sname = _slug(name)
                out.headers[name] = f"{{{{secrets.{sname}}}}}"
                out.secrets.append(DetectedSecret(sname, val, "header", name))

    # query secrets
    parts = urlsplit(out.url)
    if parts.query:
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        new_pairs = []
        for k, v in pairs:
            if (k in SECRET_QUERY_KEYS or SECRET_NAME_HINT.search(k)) and v and not v.startswith("{{"):
                sname = _slug(k)
                out.secrets.append(DetectedSecret(sname, v, "query", k))
                new_pairs.append((k, f"{{{{secrets.{sname}}}}}"))
            else:
                new_pairs.append((k, v))
        out.query = dict(new_pairs)
        out.url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    else:
        out.url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))

    # JSON body secrets (top-level fields only)
    if out.body_kind == "json" and out.body:
        try:
            data = json.loads(out.body)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            changed = False
            for k, v in data.items():
                if isinstance(v, str) and v and SECRET_NAME_HINT.search(k) and not v.startswith("{{"):
                    sname = _slug(k)
                    out.secrets.append(DetectedSecret(sname, v, "body", k))
                    data[k] = f"{{{{secrets.{sname}}}}}"
                    changed = True
            if changed:
                out.body = json.dumps(data, indent=2, ensure_ascii=False)
    if not out.secrets:
        out.warnings.append(
            "no credential detected; add one under Secrets if the API requires authentication"
        )
    return out


def redact_curl(text: str, secrets: list[DetectedSecret]) -> str:
    """Return the pasted command with every detected secret value masked (for audit rows)."""
    for s in secrets:
        if s.value:
            text = text.replace(s.value, "••••••••")
    return text
