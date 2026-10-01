"""ChatGPT Workspace Agents — API trigger (documented contract).

Contract used (https://developers.openai.com/workspace-agents/trigger-runs):
- POST https://api.chatgpt.com/v1/workspace_agents/{agtch_id}/trigger
  body {"input": str, "conversation_key": str}; header `OpenAI-Beta: workspace_agent_runs=v1`
  makes the response carry `agent_trigger_run_id` (apirun_…) next to `conversation_url`.
- GET  https://api.chatgpt.com/v1/workspace_agents/{agtch_id}/runs/{apirun_id}
  → {"status": queued|in_progress|suspended|completed|failed, "conversation_url", "error"}.
- Auth: a Workspace Agent access token (ChatGPT Admin → Access tokens), NOT a platform API key.

Limitation stated by the docs: "The agent's response cannot currently be retrieved through the
API." So this adapter triggers the run, follows its status, and returns a status message with the
ChatGPT conversation link; the agent's answer lives in ChatGPT / its configured destination.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from typing import Any

import httpx

from app.core.logging import get_logger
from app.providers.base import ConnectionTest
from app.providers.existing.base import (
    AgentCallError,
    AgentConnection,
    AgentFile,
    AgentReply,
    OnDelta,
    OnPreview,
)

log = get_logger("existing.chatgpt_workspace")
DEFAULT_BASE = "https://api.chatgpt.com/v1"
TRIGGER_RE = re.compile(r"^(?P<base>https?://[^/]+(?:/v1)?)/workspace_agents/(?P<id>agtch_[A-Za-z0-9_-]+)")
TERMINAL = {"completed", "failed"}


def credential_problem(key: str | None) -> str | None:
    """A pasted value that can never be a Workspace Agent access token, explained (never echoes it)."""
    key = (key or "").strip()
    if key.startswith("token_"):
        return (
            "this is the token's ID (token_…) from the Access tokens list, not the token itself. "
            "The access token is shown once, when it is created, and starts with “at-”. "
            "Create a new token with the “Workspace Agents” scope and paste that value."
        )
    if key.startswith("sk-"):
        return (
            "this looks like an OpenAI Platform API key (sk-…). Workspace Agents need a Workspace Agent "
            "access token from ChatGPT → Admin → Access tokens (scope: Workspace Agents)."
        )
    return None


def _token_hint(conn: AgentConnection, upstream: str = "") -> str:
    """Why ChatGPT refused the credential, in words an admin can act on (never echoes the token)."""
    key = conn.api_key or ""
    said = f' ChatGPT said: "{upstream}".' if upstream else ""
    problem = credential_problem(key)
    if problem:
        return "the access token was rejected — " + problem + said
    return (
        "the access token was rejected. Create a token in ChatGPT → Admin → Access tokens with the "
        "“Workspace Agents” scope, in the same workspace as the agent, and paste only that token." + said
    )


class ChatGPTWorkspaceAgent:
    connection_type = "chatgpt_workspace"
    display_name = "ChatGPT Workspace Agent (API trigger)"
    supports_native_session = True

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 30.0) -> None:
        self.transport = transport
        self.timeout = timeout

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _parse(conn: AgentConnection) -> tuple[str, str]:
        """Accepts the trigger URL from the ChatGPT UI, or a bare agtch_… id."""
        ep = (conn.endpoint or "").strip()
        m = TRIGGER_RE.match(ep)
        if m:
            return m.group("base").rstrip("/"), m.group("id")
        if ep.startswith("agtch_"):
            return DEFAULT_BASE, ep
        raise AgentCallError(
            "agent_not_configured",
            f"{conn.agent_name}: the endpoint must be the agent's trigger URL "
            "(https://api.chatgpt.com/v1/workspace_agents/agtch_…/trigger).",
        )

    def validate_config(self, conn: AgentConnection) -> list[str]:
        problems: list[str] = []
        if not conn.api_key:
            problems.append("a Workspace Agent access token is required")
        elif (problem := credential_problem(conn.api_key)) is not None:
            problems.append(problem)
        try:
            self._parse(conn)
        except AgentCallError as exc:
            problems.append(exc.message)
        return problems

    @staticmethod
    def _headers(conn: AgentConnection) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {conn.api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "workspace_agent_runs=v1",
        }

    @staticmethod
    def _raise_for(res: httpx.Response, conn: AgentConnection) -> None:
        if res.status_code < 400:
            return
        detail = ""
        try:
            detail = str(res.json().get("error", {}).get("message", ""))[:200]
        except ValueError:
            pass
        name = conn.agent_name
        if res.status_code == 401:
            raise AgentCallError("agent_auth", f"{name}: {_token_hint(conn, detail)}")
        if res.status_code == 403:
            raise AgentCallError("agent_auth", f"{name}: this token is not allowed to run the agent.")
        if res.status_code == 404:
            raise AgentCallError("agent_not_found", f"{name}: the trigger id was not found.")
        if res.status_code == 409:
            raise AgentCallError(
                "agent_unavailable", f"{name}: the agent is not runnable right now.", retryable=True
            )
        if res.status_code == 429:
            raise AgentCallError(
                "agent_rate_limited", f"{name}: rate limited by ChatGPT. Retry.", retryable=True
            )
        raise AgentCallError(
            "agent_unavailable",
            f"{name}: ChatGPT returned HTTP {res.status_code}. {detail}".strip(),
            retryable=True,
        )

    # ------------------------------------------------------------------ protocol
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
        on_preview: OnPreview | None = None,
    ) -> AgentReply:
        base, agent_id = self._parse(conn)
        # one ChatGPT conversation per Origin chat: follow-ups continue the same agent thread
        conversation_key = session_id or f"origin-{conversation_id}"
        poll_seconds = int(conn.config.get("poll_seconds") or 90)
        body: dict[str, Any] = {"input": message, "conversation_key": conversation_key}
        if files:
            body["input"] = message + "\n\nAttached file names: " + ", ".join(f.name for f in files)
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                res = await client.post(
                    f"{base}/workspace_agents/{agent_id}/trigger",
                    headers=self._headers(conn),
                    json=body,
                )
                self._raise_for(res, conn)
                data: dict[str, Any] = {}
                if res.content:
                    try:
                        data = res.json()
                    except ValueError:
                        data = {}
                url = str(data.get("conversation_url") or "")
                run_id = str(data.get("agent_trigger_run_id") or "")
                status = "queued"
                await on_delta(f"Triggered {conn.agent_name} in ChatGPT (run {run_id or 'queued'}).\n")
                deadline = time.monotonic() + poll_seconds
                if run_id:
                    while time.monotonic() < deadline:
                        await asyncio.sleep(2)
                        poll = await client.get(
                            f"{base}/workspace_agents/{agent_id}/runs/{run_id}", headers=self._headers(conn)
                        )
                        self._raise_for(poll, conn)
                        info = poll.json()
                        new_status = str(info.get("status") or status)
                        url = str(info.get("conversation_url") or url)
                        if new_status != status:
                            status = new_status
                            await on_delta(f"Status: {status}\n")
                        if status in TERMINAL:
                            if status == "failed":
                                err = info.get("error") or {}
                                raise AgentCallError(
                                    "agent_failed",
                                    f"{conn.agent_name} failed in ChatGPT: "
                                    f"{str(err.get('message') or err)[:200]}",
                                )
                            break
        except httpx.HTTPError as exc:
            log.warning("chatgpt_workspace_transport_error", error=type(exc).__name__)
            raise AgentCallError(
                "agent_unavailable", f"{conn.agent_name} is unreachable. Retry.", retryable=True
            ) from exc
        link = f"[Open in ChatGPT]({url})" if url else "Open the agent in ChatGPT to see the result."
        if status == "completed":
            text = (
                f"✅ **{conn.agent_name} finished the run in ChatGPT.** {link}\n\n"
                "The result (text and any images) is in that ChatGPT conversation — the Workspace Agents API "
                "does not return it here. For images that render inside this chat, connect the agent as an "
                "OpenAI GPT agent (Responses API)."
            )
        elif status in ("queued", "in_progress", "suspended"):
            text = (
                f"⏳ **{conn.agent_name} is still working in ChatGPT** (status: {status}). {link}\n\n"
                "Workspace Agents deliver their answer inside ChatGPT or the agent's configured destination; "
                "the API does not return the reply text."
            )
        else:
            text = f"{conn.agent_name}: run status {status}. {link}"
        return AgentReply(text=text, session_id=conversation_key, status=res.status_code)

    async def test_connection(self, conn: AgentConnection) -> ConnectionTest:
        problems = self.validate_config(conn)
        if problems:
            return ConnectionTest(ok=False, message="; ".join(problems))
        base, agent_id = self._parse(conn)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=15, transport=self.transport) as client:
                # a GET on a non-existent run validates the token without triggering the agent
                res = await client.get(
                    f"{base}/workspace_agents/{agent_id}/runs/apirun_connection_test",
                    headers=self._headers(conn),
                )
        except httpx.HTTPError:
            return ConnectionTest(ok=False, message="api.chatgpt.com is unreachable.")
        latency = int((time.perf_counter() - started) * 1000)
        if res.status_code == 401:
            upstream = ""
            with contextlib.suppress(ValueError):
                upstream = str(res.json().get("error", {}).get("message", ""))[:200]
            return ConnectionTest(
                ok=False, message="Authentication failed: " + _token_hint(conn, upstream), latency_ms=latency
            )
        if res.status_code == 403:
            return ConnectionTest(
                ok=False, message="The token is valid but may not run this agent (403).", latency_ms=latency
            )
        if res.status_code in (200, 404):
            return ConnectionTest(
                ok=True,
                message="Access token accepted. Messages will trigger runs in ChatGPT; replies appear there.",
                latency_ms=latency,
            )
        return ConnectionTest(
            ok=False, message=f"ChatGPT returned HTTP {res.status_code}.", latency_ms=latency
        )
