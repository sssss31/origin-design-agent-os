"""Existing agents built on the OpenAI Responses API (documented contract).

Contract used (https://platform.openai.com/docs/api-reference/responses):
- POST {base}/responses  with `model` (or a stored `prompt: {id, version}`), `input` items,
  `previous_response_id` to continue the agent's native context, `stream: true` for SSE.
- SSE events: `response.output_text.delta` (text chunks), `response.completed` (final object
  with `id`, `output[]`, `usage`), `error` / `response.failed`.
- Files: images as `input_image` (data URL), PDFs as `input_file` (`file_data` data URL).
Nothing else is assumed. No extra system prompt is injected (V0 §8).
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

import httpx

from app.core.logging import get_logger, redact
from app.ports.runner import ProducedFile
from app.providers.base import ConnectionTest
from app.providers.existing.base import AgentCallError, AgentConnection, AgentFile, AgentReply, OnDelta

log = get_logger("existing.openai")
DEFAULT_BASE = "https://api.openai.com/v1"
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
TEXT_TYPES = {"text/plain", "text/markdown", "text/csv", "application/json", "image/svg+xml"}


class OpenAIResponsesAgent:
    connection_type = "openai_responses"
    display_name = "OpenAI Responses API (GPT agent)"
    supports_native_session = True

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 180.0) -> None:
        self.transport = transport
        self.timeout = timeout

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _base(conn: AgentConnection) -> str:
        ep = (conn.endpoint or "").strip()
        if not ep:
            return DEFAULT_BASE
        ep = ep.rstrip("/")
        return ep[: -len("/responses")] if ep.endswith("/responses") else ep

    def validate_config(self, conn: AgentConnection) -> list[str]:
        problems: list[str] = []
        if not conn.api_key:
            problems.append("API key is required")
        if not conn.config.get("model") and not conn.config.get("prompt_id"):
            problems.append("set a model (e.g. gpt-5) or a stored prompt id")
        return problems

    @staticmethod
    def _content_items(message: str, files: list[AgentFile], warnings: list[str]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = [{"type": "input_text", "text": message}]
        for f in files:
            if f.mime_type in IMAGE_TYPES:
                b64 = base64.b64encode(f.content).decode()
                items.append(
                    {"type": "input_image", "image_url": f"data:{f.mime_type};base64,{b64}", "detail": "auto"}
                )
            elif f.mime_type == "application/pdf":
                b64 = base64.b64encode(f.content).decode()
                items.append(
                    {
                        "type": "input_file",
                        "filename": f.name,
                        "file_data": f"data:application/pdf;base64,{b64}",
                    }
                )
            elif f.mime_type in TEXT_TYPES:
                items.append(
                    {
                        "type": "input_text",
                        "text": f"[file {f.name}]\n{f.content.decode(errors='replace')[:20000]}",
                    }
                )
            else:
                warnings.append(
                    f"{f.name}: {f.mime_type} cannot be sent to this agent (images, PDFs and text only)"
                )
        return items

    def _body(
        self,
        conn: AgentConnection,
        message: str,
        *,
        history: list[dict[str, str]],
        files: list[AgentFile],
        session_id: str | None,
    ) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        cfg = conn.config
        body: dict[str, Any] = {"stream": True, "store": cfg.get("store", True)}
        if cfg.get("prompt_id"):
            body["prompt"] = {
                "id": cfg["prompt_id"],
                **({"version": str(cfg["prompt_version"])} if cfg.get("prompt_version") else {}),
            }
        if cfg.get("model"):
            body["model"] = cfg["model"]
        input_items: list[dict[str, Any]] = []
        if session_id:
            body["previous_response_id"] = session_id  # the agent continues its own context
        else:
            for h in history:  # Origin-kept context only when the native session is absent
                input_items.append(
                    {
                        "role": h["role"],
                        "content": [
                            {
                                "type": "input_text" if h["role"] == "user" else "output_text",
                                "text": h["content"],
                            }
                        ],
                    }
                )
        input_items.append({"role": "user", "content": self._content_items(message, files, warnings)})
        body["input"] = input_items
        for key in (
            "temperature",
            "max_output_tokens",
            "reasoning",
            "text",
            "tools",
            "tool_choice",
            "metadata",
        ):
            if key in cfg and cfg[key] is not None:
                body[key] = cfg[key]
        return body, warnings

    # ------------------------------------------------------------------ calls
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
        if not conn.api_key:
            raise AgentCallError("agent_not_configured", f"{conn.agent_name} has no API key configured.")
        body, warnings = self._body(conn, message, history=history, files=files, session_id=session_id)
        url = f"{self._base(conn)}/responses"
        headers = {
            "Authorization": f"Bearer {conn.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        text_parts: list[str] = []
        final: dict[str, Any] | None = None
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                async with client.stream("POST", url, headers=headers, json=body) as res:
                    if res.status_code >= 400:
                        raw = (await res.aread()).decode(errors="replace")
                        raise self._http_error(conn, res.status_code, raw, session_id)
                    async for line in res.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload or payload == "[DONE]":
                            continue
                        try:
                            event = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        etype = event.get("type", "")
                        if etype == "response.output_text.delta":
                            delta = str(event.get("delta", ""))
                            text_parts.append(delta)
                            await on_delta(delta)
                        elif etype in ("response.completed", "response.incomplete"):
                            final = event.get("response") or {}
                        elif etype in ("response.failed", "error"):
                            err = (event.get("response") or {}).get("error") or event.get("error") or {}
                            raise AgentCallError(
                                "agent_failed",
                                f"{conn.agent_name} reported an error: "
                                f"{redact(str(err.get('message', 'unknown')))[:200]}",
                                retryable=True,
                            )
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
        text = "".join(text_parts)
        produced: list[ProducedFile] = []
        usage: dict[str, Any] = {"duration_ms": duration}
        new_session = session_id
        if final:
            new_session = final.get("id") or session_id
            u = final.get("usage") or {}
            usage.update(
                {
                    "input_tokens": int(u.get("input_tokens", 0) or 0),
                    "output_tokens": int(u.get("output_tokens", 0) or 0),
                    "cached_input_tokens": int(
                        ((u.get("input_tokens_details") or {}).get("cached_tokens", 0)) or 0
                    ),
                    "reasoning_tokens": int(
                        ((u.get("output_tokens_details") or {}).get("reasoning_tokens", 0)) or 0
                    ),
                }
            )
            if not text:  # non-streamed text (e.g. stored prompt without streaming deltas)
                for item in final.get("output") or []:
                    if item.get("type") == "message":
                        for c in item.get("content") or []:
                            if c.get("type") == "output_text":
                                text += str(c.get("text", ""))
            for item in final.get("output") or []:
                if item.get("type") == "image_generation_call" and item.get("result"):
                    produced.append(
                        ProducedFile(
                            filename=f"{conn.agent_slug}-{uuid.uuid4().hex[:8]}.png",
                            content=base64.b64decode(item["result"]),
                            mime_type="image/png",
                            artifact_type="image",
                            metadata={"agent": conn.agent_slug, "source": "image_generation_call"},
                        )
                    )
        if warnings:
            usage["warnings"] = warnings
        return AgentReply(text=text, session_id=new_session, files=produced, usage=usage, status=200)

    @staticmethod
    def _http_error(conn: AgentConnection, status: int, raw: str, session_id: str | None) -> AgentCallError:
        detail = ""
        try:
            detail = str(((json.loads(raw) or {}).get("error") or {}).get("message", ""))[:200]
        except (ValueError, AttributeError):
            detail = ""
        if status == 401:
            return AgentCallError("agent_auth", f"{conn.agent_name}: the API key was rejected.")
        if status == 404 and session_id and "previous_response" in detail.lower():
            return AgentCallError(
                "agent_session_lost",
                f"{conn.agent_name}: the previous session expired; starting a new one.",
                retryable=True,
            )
        if status == 429:
            return AgentCallError(
                "agent_rate_limited", f"{conn.agent_name} is rate limited; try again shortly.", retryable=True
            )
        if status >= 500:
            return AgentCallError(
                "agent_unavailable", f"{conn.agent_name} is temporarily unavailable.", retryable=True
            )
        return AgentCallError(
            "agent_bad_request",
            f"{conn.agent_name} rejected the request: {redact(detail) or f'HTTP {status}'}",
        )

    async def test_connection(self, conn: AgentConnection) -> ConnectionTest:
        problems = self.validate_config(conn)
        if problems:
            return ConnectionTest(ok=False, message="; ".join(problems))
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=15, transport=self.transport) as client:
                res = await client.get(
                    f"{self._base(conn)}/models", headers={"Authorization": f"Bearer {conn.api_key}"}
                )
        except httpx.HTTPError:
            return ConnectionTest(ok=False, message="The agent endpoint is unreachable.")
        latency = int((time.perf_counter() - started) * 1000)
        if res.status_code == 401:
            return ConnectionTest(
                ok=False, message="Authentication failed: the API key was rejected.", latency_ms=latency
            )
        if res.status_code != 200:
            return ConnectionTest(
                ok=False, message=f"Endpoint returned HTTP {res.status_code}.", latency_ms=latency
            )
        models: list[str] = []
        try:
            models = sorted(str(m.get("id")) for m in res.json().get("data", []) if m.get("id"))
        except ValueError:
            pass
        wanted = conn.config.get("model")
        if wanted and models and wanted not in models:
            return ConnectionTest(
                ok=False,
                message=f"Connected, but model '{wanted}' is not available to this key.",
                latency_ms=latency,
                models=models,
            )
        return ConnectionTest(
            ok=True,
            message="Connected." + (f" Model {wanted} available." if wanted else ""),
            latency_ms=latency,
            models=models,
        )
