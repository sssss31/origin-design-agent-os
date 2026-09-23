"""Understand a pasted *provider* cURL (OpenAI Responses / Chat Completions, or a compatible
proxy) so one paste can configure the provider key, base URL, model and even an agent.

This is different from `curl_parser` (generic REST integrations): here we know the shape of
the request and pull out the pieces Origin's own agents need.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.domain.curl_parser import CurlParseError, parse_curl

PLACEHOLDER = re.compile(
    r"^\$?\{?\s*[A-Z_]*API_KEY\s*\}?$|^(YOUR|MY)[_-]?API[_-]?KEY$|^<.*>$|^\$\(.*\)$|^\$[A-Za-z_]+$", re.I
)
OPENAI_HOSTS = {"api.openai.com"}
KNOWN_ENDPOINTS = {
    "/responses": "responses",
    "/chat/completions": "chat",
    "/images/generations": "images",
    "/assistants": "assistants",
    "/embeddings": "embeddings",
    "/models": "models",
}


@dataclass(slots=True)
class ProviderCurl:
    provider_type: str
    base_url: str
    endpoint_kind: str
    api_key: str | None
    key_placeholder: bool
    model: str | None
    instructions: str | None
    sample_input: str | None
    model_settings: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    prompt_id: str | None = None
    tools: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "provider": self.provider_type,
            "base_url": self.base_url,
            "endpoint": self.endpoint_kind,
            "model": self.model or "—",
            "auth": "placeholder — paste your real key"
            if self.key_placeholder
            else ("Secret detected" if self.api_key else "None"),
            "instructions": "found" if self.instructions else "none",
        }


def looks_like_curl(text: str) -> bool:
    t = text.strip()
    return t.lower().startswith("curl ") or ("\n" in t and " -H " in t) or (" --header " in t and "http" in t)


def _text_of(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = [
            str(c["text"]) for c in content if isinstance(c, dict) and isinstance(c.get("text"), str)
        ]
        return "\n".join(parts) if parts else None
    return None


def parse_provider_curl(text: str) -> ProviderCurl:
    try:
        parsed = parse_curl(text)
    except CurlParseError as exc:
        raise ValueError(str(exc)) from exc
    parts = urlsplit(parsed.url)
    host = (parts.hostname or "").lower()
    path = parts.path.rstrip("/")
    kind = next((k for suffix, k in KNOWN_ENDPOINTS.items() if path.endswith(suffix)), "unknown")
    # base_url = everything up to and including the version segment (…/v1)
    m = re.match(r"^(.*?/v\d+)(/|$)", path)
    base_path = m.group(1) if m else path.rsplit("/", 1)[0] if kind != "unknown" else path
    base_url = f"{parts.scheme}://{parts.netloc}{base_path}"

    api_key: str | None = None
    placeholder = False
    for s in parsed.secrets:
        if s.name in ("api_key", "authorization", "x_api_key", "openai_api_key"):
            if PLACEHOLDER.match(s.value.strip()):
                placeholder = True
            else:
                api_key = s.value.strip()
            break
    warnings: list[str] = []
    if placeholder:
        warnings.append(
            "the cURL contains a key placeholder (e.g. $OPENAI_API_KEY); paste your real key separately"
        )
    if not api_key and not placeholder:
        warnings.append("no Authorization header found in the cURL")

    provider_type = "openai"
    if host not in OPENAI_HOSTS and kind not in (
        "responses",
        "chat",
        "models",
        "images",
        "embeddings",
        "assistants",
    ):
        provider_type = "custom"
        warnings.append(f"{host} is not an OpenAI-compatible endpoint; use Custom REST APIs for it")
    elif host not in OPENAI_HOSTS:
        warnings.append(f"OpenAI-compatible endpoint on {host}; the provider base URL is set to {base_url}")

    body: dict[str, Any] = {}
    if parsed.body:
        try:
            loaded = json.loads(parsed.body)
            if isinstance(loaded, dict):
                body = loaded
        except json.JSONDecodeError:
            warnings.append("request body is not JSON; model and instructions were not extracted")

    model = body.get("model") if isinstance(body.get("model"), str) else None
    instructions: str | None = None
    sample: str | None = None
    if kind == "responses":
        instructions = body.get("instructions") if isinstance(body.get("instructions"), str) else None
        inp = body.get("input")
        if isinstance(inp, str):
            sample = inp
        elif isinstance(inp, list):
            for item in inp:
                if isinstance(item, dict):
                    role = item.get("role")
                    txt = _text_of(item.get("content"))
                    if role in ("system", "developer") and txt and not instructions:
                        instructions = txt
                    elif role == "user" and txt and not sample:
                        sample = txt
    elif kind == "chat":
        for msg in body.get("messages") or []:
            if not isinstance(msg, dict):
                continue
            txt = _text_of(msg.get("content"))
            if msg.get("role") in ("system", "developer") and txt and not instructions:
                instructions = txt
            elif msg.get("role") == "user" and txt and not sample:
                sample = txt
    prompt = body.get("prompt")
    prompt_id = prompt.get("id") if isinstance(prompt, dict) and isinstance(prompt.get("id"), str) else None
    if prompt_id and not instructions:
        warnings.append(
            "the cURL references a stored prompt id; copy its instructions into the agent "
            "(stored prompts are not exposed by the API)"
        )

    settings: dict[str, Any] = {}
    for key in ("temperature", "top_p"):
        if isinstance(body.get(key), int | float):
            settings[key] = body[key]
    for key in ("max_output_tokens", "max_tokens", "max_completion_tokens"):
        if isinstance(body.get(key), int):
            settings["max_output_tokens"] = body[key]
            break
    reasoning = body.get("reasoning")
    if isinstance(reasoning, dict) and isinstance(reasoning.get("effort"), str):
        settings["reasoning_effort"] = reasoning["effort"]
    elif isinstance(body.get("reasoning_effort"), str):
        settings["reasoning_effort"] = body["reasoning_effort"]

    output_schema: dict[str, Any] | None = None
    fmt = (
        (body.get("text") or {}).get("format")
        if isinstance(body.get("text"), dict)
        else body.get("response_format")
    )
    if isinstance(fmt, dict):
        schema = fmt.get("schema") or (fmt.get("json_schema") or {}).get("schema")
        if isinstance(schema, dict):
            output_schema = schema

    tools: list[str] = []
    for t in body.get("tools") or []:
        if isinstance(t, dict):
            tools.append(
                str(t.get("name") or (t.get("function") or {}).get("name") or t.get("type") or "tool")
            )
    if tools:
        warnings.append(
            f"tools in the cURL ({', '.join(tools)}) are not imported; bind Origin tools to the agent instead"
        )

    return ProviderCurl(
        provider_type=provider_type,
        base_url=base_url,
        endpoint_kind=kind,
        api_key=api_key,
        key_placeholder=placeholder,
        model=model,
        instructions=instructions,
        sample_input=sample,
        model_settings=settings,
        output_schema=output_schema,
        prompt_id=prompt_id,
        tools=tools,
        warnings=warnings,
    )
