"""Provider adapter layer: capability matrix, parameter filtering, cost, retries, error mapping."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from app.ports.runner import RunInput, RunOutcome, RuntimeAgent
from app.ports.secrets import key_preview
from app.providers.base import ModelPrice, ProviderError, estimate_cost, filter_model_settings
from app.providers.openai_models import resolve_capabilities
from app.providers.openai_provider import OpenAIProvider, classify_exception


def test_key_preview_masks_everything_but_prefix_and_tail() -> None:
    assert key_preview("sk-proj-abcdefghijklmnopqrstuvwxyz7Xk2") == "sk-proj-••••••••7Xk2"
    assert key_preview("sk-abcdefghijklmnop1234") == "sk-••••••••1234"
    assert key_preview("short") == "••••••••"
    assert "abcdefghijklmnop" not in key_preview("sk-abcdefghijklmnop1234")


@pytest.mark.parametrize(
    ("model", "temperature", "reasoning", "vision", "image"),
    [
        ("gpt-5", False, True, True, False),
        ("o4-mini", False, True, True, False),
        ("gpt-4.1-mini", True, False, True, False),
        ("gpt-4o", True, False, True, False),
        ("gpt-image-1", False, False, False, True),
        ("something-new", False, False, False, False),
    ],
)
def test_capability_matrix(model: str, temperature: bool, reasoning: bool, vision: bool, image: bool) -> None:
    caps = resolve_capabilities(model)
    assert caps.supports_temperature is temperature
    assert caps.supports_reasoning is reasoning
    assert caps.supports_vision is vision
    assert caps.supports_image_generation is image


def test_admin_overrides_take_precedence() -> None:
    caps = resolve_capabilities("something-new", {"supports_temperature": True, "context_window": 128000})
    assert caps.supports_temperature and caps.context_window == 128000
    legacy = resolve_capabilities("gpt-3.5-turbo", {"vision": True})
    assert legacy.supports_vision


def test_filter_model_settings_sends_only_supported_params() -> None:
    settings = {
        "temperature": 0.4,
        "top_p": 0.9,
        "reasoning_effort": "high",
        "max_output_tokens": 2000,
        "tool_choice": "auto",
    }
    reasoning = filter_model_settings(settings, resolve_capabilities("gpt-5"))
    assert reasoning == {"reasoning": {"effort": "high"}, "max_tokens": 2000, "tool_choice": "auto"}
    chat = filter_model_settings(settings, resolve_capabilities("gpt-4.1"))
    assert chat == {"temperature": 0.4, "top_p": 0.9, "max_tokens": 2000, "tool_choice": "auto"}
    assert filter_model_settings({"temperature": None}, resolve_capabilities("gpt-4.1")) == {}


def test_estimate_cost_uses_cached_discount_and_images() -> None:
    price = ModelPrice(
        input_per_million=2.0, cached_input_per_million=0.5, output_per_million=8.0, image_per_unit=0.04
    )
    est = estimate_cost(
        {
            "input_tokens": 1_000_000,
            "cached_input_tokens": 500_000,
            "output_tokens": 250_000,
            "image_generations": 2,
        },
        price,
    )
    assert est.priced and est.estimated_cost_usd == pytest.approx(1.0 + 0.25 + 2.0 + 0.08)
    assert estimate_cost({"input_tokens": 10}, None).priced is False


def test_classify_exception_is_sanitized() -> None:
    err = classify_exception(httpx.ConnectError("connect to api.openai.com sk-live-secret failed"))
    assert err.code == "provider_unavailable" and err.retryable and "sk-live" not in err.message
    assert classify_exception(ValueError("boom")).retryable is False


def _agent(**settings: Any) -> RuntimeAgent:
    return RuntimeAgent(
        slug="master",
        name="Master",
        version=1,
        instructions="x",
        model="gpt-5",
        provider_type="openai",
        model_settings=settings,
        provider_credentials={"api_key": "sk-test"},
    )


class FakeRunner:
    name = "fake"

    def __init__(self, failures: list[BaseException], *, call_tool: bool = False) -> None:
        self.failures = failures
        self.calls = 0
        self.seen_settings: list[dict[str, Any]] = []
        self.call_tool = call_tool

    async def run(
        self, agent: RuntimeAgent, run_input: RunInput, *, invoke_tool: Any, emit: Any
    ) -> RunOutcome:
        self.calls += 1
        self.seen_settings.append(dict(agent.model_settings))
        if self.call_tool:
            await invoke_tool("image.generate", {})
        if self.failures:
            raise self.failures.pop(0)
        return RunOutcome(output_text="ok", usage={"input_tokens": 3, "output_tokens": 2})


async def _noop_tool(slug: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True}


async def test_openai_provider_retries_retryable_errors_with_backoff_then_succeeds() -> None:
    provider = OpenAIProvider(max_attempts=3, backoff_seconds=0.0)
    fake = FakeRunner([httpx.ReadTimeout("t"), ProviderError("provider_unavailable", "x", retryable=True)])
    provider.runner = fake  # type: ignore[assignment]
    retries: list[dict[str, Any]] = []

    async def emit(event: str, payload: dict[str, Any]) -> None:
        retries.append(payload)

    outcome = await provider.execute(
        _agent(temperature=0.2, reasoning_effort="low"),
        RunInput(user_input="hi"),
        invoke_tool=_noop_tool,
        emit=emit,
    )
    assert outcome.output_text == "ok" and outcome.usage["attempts"] == 3 and fake.calls == 3
    assert [r["attempt"] for r in retries] == [1, 2]
    # gpt-5 is a reasoning model: temperature dropped, reasoning kept
    assert fake.seen_settings[0] == {"reasoning": {"effort": "low"}}


async def test_openai_provider_does_not_retry_non_retryable_or_after_side_effects() -> None:
    provider = OpenAIProvider(max_attempts=3, backoff_seconds=0.0)
    fake = FakeRunner([ValueError("bad")])
    provider.runner = fake  # type: ignore[assignment]

    async def emit(event: str, payload: dict[str, Any]) -> None:
        return None

    with pytest.raises(ProviderError) as exc:
        await provider.execute(_agent(), RunInput(user_input="hi"), invoke_tool=_noop_tool, emit=emit)
    assert exc.value.code == "provider_error" and fake.calls == 1

    # a retryable error after an image-generation tool call must not be retried (no duplicate images)
    fake2 = FakeRunner([httpx.ReadTimeout("t")], call_tool=True)
    provider.runner = fake2  # type: ignore[assignment]
    with pytest.raises(ProviderError) as exc2:
        await provider.execute(_agent(), RunInput(user_input="hi"), invoke_tool=_noop_tool, emit=emit)
    assert exc2.value.retryable and fake2.calls == 1


async def test_openai_provider_bounded_attempts() -> None:
    provider = OpenAIProvider(max_attempts=2, backoff_seconds=0.0)
    fake = FakeRunner([httpx.ReadTimeout("1"), httpx.ReadTimeout("2"), httpx.ReadTimeout("3")])
    provider.runner = fake  # type: ignore[assignment]

    async def emit(event: str, payload: dict[str, Any]) -> None:
        return None

    with pytest.raises(ProviderError):
        await provider.execute(_agent(), RunInput(user_input="hi"), invoke_tool=_noop_tool, emit=emit)
    assert fake.calls == 2


async def test_openai_test_connection_never_returns_key(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIProvider()
    seen: dict[str, str] = {}

    class FakeClient:
        def __init__(self, *a: Any, **k: Any) -> None: ...

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *a: Any) -> None: ...

        async def get(self, url: str, headers: dict[str, str]) -> httpx.Response:
            seen["auth"] = headers["Authorization"]
            return httpx.Response(
                200, json={"data": [{"id": "gpt-5"}, {"id": "gpt-4.1"}]}, request=httpx.Request("GET", url)
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    res = await provider.test_connection({}, "sk-test-1234567890")
    assert res.ok and res.models == ["gpt-4.1", "gpt-5"] and seen["auth"] == "Bearer sk-test-1234567890"
    assert "sk-test" not in res.message
    missing = await provider.test_connection({}, None)
    assert not missing.ok and "No API key" in missing.message
    await asyncio.sleep(0)
