"""OpenAI provider adapter (spec §12–§13).

- `execute()` runs the agent through the OpenAI Agents SDK runner with only the parameters
  the selected model supports, and retries *retryable* failures (429, 5xx, connection,
  timeout) with bounded exponential backoff — but never after a tool call has already
  happened, so an expensive image generation is not duplicated.
- `test_connection()` performs one authenticated `GET /models`; the key never leaves the
  server and the result carries status metadata only.
- Errors are mapped to `ProviderError` with a sanitized message; details are logged.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.adapters.runners.openai_agents import OpenAIAgentsRunner
from app.core.logging import get_logger, redact
from app.ports.runner import AgentRunner, EventEmitter, RunInput, RunOutcome, RuntimeAgent, ToolInvoker
from app.providers.base import (
    ConnectionTest,
    ModelCapabilities,
    ModelPrice,
    ProviderError,
    UsageEstimate,
    estimate_cost,
    filter_model_settings,
)
from app.providers.openai_models import resolve_capabilities

log = get_logger("provider.openai")

DEFAULT_BASE_URL = "https://api.openai.com/v1"
SAFE_UNAVAILABLE = "Agent temporarily unavailable. Provider connection failed."
KNOWN_MODELS: list[dict[str, Any]] = [
    {"model": "gpt-5", "display_name": "GPT-5"},
    {"model": "gpt-5-mini", "display_name": "GPT-5 mini"},
    {"model": "gpt-4.1", "display_name": "GPT-4.1"},
    {"model": "gpt-4.1-mini", "display_name": "GPT-4.1 mini"},
    {"model": "gpt-4o", "display_name": "GPT-4o"},
    {"model": "o4-mini", "display_name": "o4-mini"},
    {"model": "gpt-image-1", "display_name": "GPT Image 1"},
]


def classify_exception(exc: BaseException) -> ProviderError:
    """Map SDK/HTTP exceptions to a sanitized, retry-aware ProviderError."""
    if isinstance(exc, ProviderError):
        return exc
    try:
        import openai
    except ImportError:  # pragma: no cover - openai extra not installed
        openai = None  # type: ignore[assignment]
    status = getattr(exc, "status_code", None)
    if openai is not None:
        if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
            return ProviderError("provider_auth", "Provider rejected the API key.", status=status)
        if isinstance(exc, openai.RateLimitError):
            return ProviderError(
                "provider_rate_limited", "Provider rate limit reached.", retryable=True, status=429
            )
        if isinstance(exc, openai.APITimeoutError | openai.APIConnectionError):
            return ProviderError("provider_unavailable", SAFE_UNAVAILABLE, retryable=True)
        if isinstance(exc, openai.BadRequestError | openai.UnprocessableEntityError):
            return ProviderError(
                "provider_bad_request", "Provider rejected the request configuration.", status=status
            )
        if isinstance(exc, openai.APIStatusError):
            retry = bool(status and int(status) >= 500)
            return ProviderError(
                "provider_unavailable" if retry else "provider_error",
                SAFE_UNAVAILABLE if retry else "Provider returned an error.",
                retryable=retry,
                status=status,
            )
    if isinstance(exc, httpx.HTTPError | TimeoutError | asyncio.TimeoutError):
        return ProviderError("provider_unavailable", SAFE_UNAVAILABLE, retryable=True)
    name = type(exc).__name__
    if name in {"MaxTurnsExceeded", "ModelBehaviorError", "AgentsException", "UserError"}:
        return ProviderError("agent_runtime_error", f"Agent runtime error: {name}.")
    return ProviderError("provider_error", "Provider request failed.")


class OpenAIProvider:
    provider_type = "openai"
    display_name = "OpenAI"

    def __init__(
        self,
        *,
        trace_include_sensitive_data: bool = False,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
    ) -> None:
        self.runner: AgentRunner = OpenAIAgentsRunner(
            trace_include_sensitive_data=trace_include_sensitive_data
        )
        self.max_attempts = max(1, max_attempts)
        self.backoff_seconds = backoff_seconds

    # ------------------------------------------------------------------ execution
    async def execute(
        self, agent: RuntimeAgent, run_input: RunInput, *, invoke_tool: ToolInvoker, emit: EventEmitter
    ) -> RunOutcome:
        caps = self.model_capabilities(agent.model, agent.model_settings.get("_capabilities"))
        filtered = filter_model_settings(
            {k: v for k, v in agent.model_settings.items() if not k.startswith("_")}, caps
        )
        prepared = RuntimeAgent(
            slug=agent.slug,
            name=agent.name,
            version=agent.version,
            instructions=agent.instructions,
            model=agent.model,
            provider_type=agent.provider_type,
            model_settings=filtered,
            tools=agent.tools if caps.supports_tools else [],
            output_schema=agent.output_schema,
            can_ask_clarification=agent.can_ask_clarification,
            max_steps=agent.max_steps,
            timeout_seconds=agent.timeout_seconds,
            provider_credentials=agent.provider_credentials,
        )
        side_effects = 0

        async def counted_invoke(slug: str, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal side_effects
            side_effects += 1
            return await invoke_tool(slug, args)

        attempt = 0
        while True:
            attempt += 1
            try:
                outcome = await self.runner.run(prepared, run_input, invoke_tool=counted_invoke, emit=emit)
                outcome.usage = {**outcome.usage, "attempts": attempt}
                return outcome
            except Exception as exc:
                error = classify_exception(exc)
                log.warning(
                    "openai_request_failed",
                    code=error.code,
                    status=error.status,
                    attempt=attempt,
                    retryable=error.retryable,
                    side_effects=side_effects,
                    detail=redact(str(exc))[:300],
                )
                if not error.retryable or attempt >= self.max_attempts or side_effects > 0:
                    raise error from exc
                await emit("provider.retry", {"attempt": attempt, "code": error.code})
                await asyncio.sleep(self.backoff_seconds * (2 ** (attempt - 1)))

    # ------------------------------------------------------------------ admin operations
    async def test_connection(self, config: dict[str, Any], api_key: str | None) -> ConnectionTest:
        if not api_key:
            return ConnectionTest(ok=False, message="No API key stored for this provider.")
        url = (config.get("base_url") or DEFAULT_BASE_URL).rstrip("/") + "/models"
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        except httpx.HTTPError as exc:
            log.warning("openai_test_failed", detail=redact(str(exc))[:200])
            return ConnectionTest(
                ok=False, message="Connection failed: the provider endpoint is unreachable."
            )
        latency = int((time.perf_counter() - started) * 1000)
        if res.status_code == 401:
            return ConnectionTest(
                ok=False, message="Authentication failed: the API key was rejected.", latency_ms=latency
            )
        if res.status_code == 403:
            return ConnectionTest(
                ok=False,
                message="The API key is valid but lacks permission to list models.",
                latency_ms=latency,
            )
        if res.status_code == 429:
            return ConnectionTest(
                ok=False, message="Rate limited by the provider; try again shortly.", latency_ms=latency
            )
        if res.status_code != 200:
            return ConnectionTest(
                ok=False, message=f"Provider returned HTTP {res.status_code}.", latency_ms=latency
            )
        try:
            models = sorted(str(m.get("id")) for m in res.json().get("data", []) if m.get("id"))
        except ValueError:
            models = []
        return ConnectionTest(
            ok=True, message=f"Connected; {len(models)} models visible.", latency_ms=latency, models=models
        )

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        base = config.get("base_url")
        if base and not str(base).startswith("https://"):
            problems.append("base_url must use https")
        return problems

    def get_supported_models(self) -> list[dict[str, Any]]:
        return [{**m, "capabilities": resolve_capabilities(m["model"]).as_dict()} for m in KNOWN_MODELS]

    def model_capabilities(self, model: str, overrides: dict[str, Any] | None = None) -> ModelCapabilities:
        return resolve_capabilities(model, overrides)

    def calculate_usage(self, model: str, usage: dict[str, Any], price: ModelPrice | None) -> UsageEstimate:
        return estimate_cost(usage, price)
