from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.ports.runner import AgentRunner, EventEmitter, RunInput, RunOutcome, RuntimeAgent, ToolInvoker


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """What a model accepts. Drives both the admin form and the parameters actually sent."""

    supports_temperature: bool = False
    supports_top_p: bool = False
    supports_reasoning: bool = False
    supports_vision: bool = False
    supports_tools: bool = True
    supports_structured_output: bool = True
    supports_image_generation: bool = False
    max_output_tokens_param: str | None = "max_output_tokens"
    context_window: int | None = None
    max_output_tokens: int | None = None
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "supports_temperature": self.supports_temperature,
            "supports_top_p": self.supports_top_p,
            "supports_reasoning": self.supports_reasoning,
            "supports_vision": self.supports_vision,
            "supports_tools": self.supports_tools,
            "supports_structured_output": self.supports_structured_output,
            "supports_image_generation": self.supports_image_generation,
            "max_output_tokens_param": self.max_output_tokens_param,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "notes": self.notes,
        }


@dataclass(slots=True)
class ConnectionTest:
    ok: bool
    message: str
    latency_ms: int = 0
    models: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UsageEstimate:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    image_generations: int = 0
    tool_calls: int = 0
    estimated_cost_usd: float = 0.0
    priced: bool = False


@dataclass(slots=True)
class ModelPrice:
    """Per-million-token prices in USD. Admin-configurable; never hardcoded permanently."""

    input_per_million: float = 0.0
    cached_input_per_million: float = 0.0
    output_per_million: float = 0.0
    image_per_unit: float = 0.0


class ProviderError(Exception):
    """Sanitized provider failure. `retryable` drives bounded backoff; details are logged only."""

    def __init__(
        self, code: str, message: str, *, retryable: bool = False, status: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status = status


@runtime_checkable
class AIProvider(Protocol):
    provider_type: str
    display_name: str
    runner: AgentRunner

    async def execute(
        self,
        agent: RuntimeAgent,
        run_input: RunInput,
        *,
        invoke_tool: ToolInvoker,
        emit: EventEmitter,
    ) -> RunOutcome: ...

    async def test_connection(self, config: dict[str, Any], api_key: str | None) -> ConnectionTest: ...

    def validate_config(self, config: dict[str, Any]) -> list[str]: ...

    def get_supported_models(self) -> list[dict[str, Any]]: ...

    def model_capabilities(
        self, model: str, overrides: dict[str, Any] | None = None
    ) -> ModelCapabilities: ...

    def calculate_usage(
        self, model: str, usage: dict[str, Any], price: ModelPrice | None
    ) -> UsageEstimate: ...


def filter_model_settings(settings: dict[str, Any], caps: ModelCapabilities) -> dict[str, Any]:
    """Keep only the parameters the selected model supports (spec §12: never copy blindly)."""
    out: dict[str, Any] = {}
    for key, value in settings.items():
        if value is None:
            continue
        if key == "temperature" and caps.supports_temperature:
            out[key] = value
        elif key == "top_p" and caps.supports_top_p:
            out[key] = value
        elif key in ("reasoning", "reasoning_effort") and caps.supports_reasoning:
            out["reasoning"] = value if isinstance(value, dict) else {"effort": str(value)}
        elif key in ("max_output_tokens", "max_tokens") and caps.max_output_tokens_param:
            out["max_tokens"] = int(value)
        elif key in ("tool_choice", "parallel_tool_calls", "truncation"):
            out[key] = value
    return out


def estimate_cost(usage: dict[str, Any], price: ModelPrice | None) -> UsageEstimate:
    est = UsageEstimate(
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        cached_input_tokens=int(usage.get("cached_input_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        reasoning_tokens=int(usage.get("reasoning_tokens", 0) or 0),
        image_generations=int(usage.get("image_generations", 0) or 0),
        tool_calls=int(usage.get("tool_calls", 0) or 0),
    )
    if price is None:
        return est
    uncached = max(0, est.input_tokens - est.cached_input_tokens)
    cost = (
        uncached / 1_000_000 * price.input_per_million
        + est.cached_input_tokens / 1_000_000 * price.cached_input_per_million
        + est.output_tokens / 1_000_000 * price.output_per_million
        + est.image_generations * price.image_per_unit
    )
    est.estimated_cost_usd = round(cost, 6)
    est.priced = True
    return est
