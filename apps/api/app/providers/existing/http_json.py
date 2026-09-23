"""Existing agents behind a plain HTTP JSON endpoint (configurable request/response mapping).

Nothing is assumed about the remote contract: the admin describes it in `connection_config`:
- method (POST), headers_template, body_template with placeholders {{message}},
  {{session_id}}, {{conversation_id}}, {{history}} (JSON list), {{files}} (JSON list of
  {name, mime_type, size, url})
- response_text_path (dotted, default: first of text/reply/message/output/content),
  session_id_path (default session_id), files_path (list of {url|data, name, mime_type})
Outbound URLs go through the SSRF guard; responses are size- and time-bounded.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger, redact
from app.core.ssrf import OutboundBlocked, validate_outbound_url
from app.domain.templates import render, render_mapping
from app.ports.runner import ProducedFile
from app.providers.base import ConnectionTest
from app.providers.existing.base import AgentCallError, AgentConnection, AgentFile, AgentReply, OnDelta

log = get_logger("existing.http")
DEFAULT_BODY = (
    '{"message": "{{message}}", "session_id": "{{session_id}}", '
    '"conversation_id": "{{conversation_id}}", "history": {{history}}, "files": {{files}}}'
)
TEXT_CANDIDATES = ("text", "reply", "message", "output", "content", "response", "answer")
FILE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "application/pdf": "pdf",
}


def _path(data: Any, path: str | None) -> Any:
    if not path:
        return None
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


class HttpJsonAgent:
    connection_type = "http"
    display_name = "HTTP JSON endpoint"
    supports_native_session = True  # when the endpoint returns a session id

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    def validate_config(self, conn: AgentConnection) -> list[str]:
        problems: list[str] = []
        if not conn.endpoint:
            problems.append("API endpoint is required")
        else:
            try:
                validate_outbound_url(conn.endpoint, self.settings)
            except OutboundBlocked as exc:
                problems.append(str(exc))
        return problems

    def _request(
        self,
        conn: AgentConnection,
        message: str,
        *,
        history: list[dict[str, str]],
        files: list[AgentFile],
        session_id: str | None,
        conversation_id: str,
    ) -> tuple[str, dict[str, str], bytes]:
        cfg = conn.config
        secrets = {"api_key": conn.api_key or ""}
        variables = {
            "message": message,
            "session_id": session_id or "",
            "conversation_id": conversation_id,
            "history": history,
            "files": [
                {"name": f.name, "mime_type": f.mime_type, "size": len(f.content), "url": f.url or ""}
                for f in files
            ],
            "agent": conn.agent_slug,
        }
        headers_tpl = dict(cfg.get("headers_template") or {})
        if (
            conn.api_key
            and not any(k.lower() == "authorization" for k in headers_tpl)
            and not cfg.get("api_key_header")
        ):
            headers_tpl["Authorization"] = "Bearer {{secrets.api_key}}"
        if cfg.get("api_key_header") and conn.api_key:
            headers_tpl[str(cfg["api_key_header"])] = "{{secrets.api_key}}"
        headers = render_mapping(headers_tpl, variables=variables, secrets=secrets, strict_secrets=False)
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("Accept", "application/json")
        body = render(
            str(cfg.get("body_template") or DEFAULT_BODY),
            variables=variables,
            secrets=secrets,
            json_mode=True,
            strict_secrets=False,
        )
        return str(conn.endpoint), headers, body.encode()

    async def send_message(
        self,
        conn: AgentConnection,
        message: str,
        *,
        history: list[dict[str, str]],
        files: list[AgentFile],
        session_id: str | None,
        conversation_id: str,
        on_delta: OnDelta,
    ) -> AgentReply:
        problems = self.validate_config(conn)
        if problems:
            raise AgentCallError("agent_not_configured", f"{conn.agent_name}: {'; '.join(problems)}")
        url, headers, payload = self._request(
            conn,
            message,
            history=history,
            files=files,
            session_id=session_id,
            conversation_id=conversation_id,
        )
        method = str(conn.config.get("method") or "POST").upper()
        timeout = float(conn.config.get("timeout_seconds") or 120)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False, transport=self.transport
            ) as client:
                res = await client.request(method, url, headers=headers, content=payload)
        except httpx.TimeoutException as exc:
            raise AgentCallError(
                "agent_timeout", f"{conn.agent_name} did not answer in time.", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            log.warning("existing_agent_unreachable", agent=conn.agent_slug, detail=redact(str(exc))[:200])
            raise AgentCallError(
                "agent_unreachable", f"{conn.agent_name} could not be reached.", retryable=True
            ) from exc
        duration = int((time.perf_counter() - started) * 1000)
        if len(res.content) > self.settings.outbound_max_response_bytes:
            raise AgentCallError(
                "agent_response_too_large", f"{conn.agent_name} returned a response that is too large."
            )
        if res.status_code == 401 or res.status_code == 403:
            raise AgentCallError("agent_auth", f"{conn.agent_name}: the API credential was rejected.")
        if res.status_code == 429:
            raise AgentCallError(
                "agent_rate_limited", f"{conn.agent_name} is rate limited; try again shortly.", retryable=True
            )
        if res.status_code >= 500:
            raise AgentCallError(
                "agent_unavailable", f"{conn.agent_name} is temporarily unavailable.", retryable=True
            )
        if res.status_code >= 400:
            raise AgentCallError(
                "agent_bad_request", f"{conn.agent_name} rejected the request (HTTP {res.status_code})."
            )
        ctype = (res.headers.get("content-type") or "").split(";")[0].strip().lower()
        produced: list[ProducedFile] = []
        text = ""
        new_session = session_id
        if ctype in FILE_TYPES:
            produced.append(
                ProducedFile(
                    filename=f"{conn.agent_slug}-{uuid.uuid4().hex[:8]}.{FILE_TYPES[ctype]}",
                    content=res.content,
                    mime_type=ctype,
                    artifact_type="image"
                    if ctype.startswith("image/") and ctype != "image/svg+xml"
                    else "svg"
                    if ctype == "image/svg+xml"
                    else "pdf",
                )
            )
            text = f"{conn.agent_name} returned a file."
        else:
            try:
                data = res.json()
            except ValueError:
                data = None
            if isinstance(data, dict | list):
                cfg = conn.config
                value = _path(data, cfg.get("response_text_path")) if cfg.get("response_text_path") else None
                if value is None and isinstance(data, dict):
                    for key in TEXT_CANDIDATES:
                        if isinstance(data.get(key), str):
                            value = data[key]
                            break
                text = value if isinstance(value, str) else json.dumps(data, ensure_ascii=False)[:20000]
                sid = _path(data, str(cfg.get("session_id_path") or "session_id"))
                if isinstance(sid, str | int) and str(sid):
                    new_session = str(sid)
                for f in _path(data, str(cfg.get("files_path") or "files")) or []:
                    if not isinstance(f, dict):
                        continue
                    mime = str(f.get("mime_type") or f.get("type") or "")
                    name = str(f.get("name") or f"{conn.agent_slug}-{uuid.uuid4().hex[:8]}")
                    content: bytes | None = None
                    if isinstance(f.get("data"), str):
                        try:
                            content = base64.b64decode(f["data"])
                        except ValueError:
                            content = None
                    elif isinstance(f.get("url"), str):
                        try:
                            validate_outbound_url(f["url"], self.settings)
                            async with httpx.AsyncClient(
                                timeout=60, follow_redirects=False, transport=self.transport
                            ) as client:
                                dl = await client.get(f["url"])
                            if (
                                dl.status_code == 200
                                and len(dl.content) <= self.settings.outbound_max_response_bytes
                            ):
                                content = dl.content
                                mime = mime or (dl.headers.get("content-type") or "").split(";")[0]
                        except (OutboundBlocked, httpx.HTTPError):
                            content = None
                    if content is not None and mime in FILE_TYPES:
                        produced.append(
                            ProducedFile(
                                filename=name if "." in name else f"{name}.{FILE_TYPES[mime]}",
                                content=content,
                                mime_type=mime,
                                artifact_type="image"
                                if mime.startswith("image/") and mime != "image/svg+xml"
                                else "svg"
                                if mime == "image/svg+xml"
                                else "pdf",
                            )
                        )
            else:
                text = res.text[:20000]
        if text:
            await on_delta(text)
        return AgentReply(
            text=text,
            session_id=new_session,
            files=produced,
            usage={"duration_ms": duration},
            status=res.status_code,
        )

    async def test_connection(self, conn: AgentConnection) -> ConnectionTest:
        problems = self.validate_config(conn)
        if problems:
            return ConnectionTest(ok=False, message="; ".join(problems))
        cfg = conn.config
        test_message = str(cfg.get("test_message") or "ping")
        started = time.perf_counter()
        try:
            reply = await self.send_message(
                conn,
                test_message,
                history=[],
                files=[],
                session_id=None,
                conversation_id="test",
                on_delta=_noop,
            )
        except AgentCallError as exc:
            return ConnectionTest(
                ok=False, message=exc.message, latency_ms=int((time.perf_counter() - started) * 1000)
            )
        latency = int((time.perf_counter() - started) * 1000)
        return ConnectionTest(
            ok=True,
            message=f"Connected (HTTP {reply.status}); reply {len(reply.text)} chars.",
            latency_ms=latency,
        )


async def _noop(_: str) -> None:
    return None
