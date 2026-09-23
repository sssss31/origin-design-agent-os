"""Offline provider used for tests, demos and the admin sandbox when no key is configured."""

from __future__ import annotations

from typing import Any

from app.adapters.runners.echo import EchoRunner
from app.ports.runner import AgentRunner, EventEmitter, RunInput, RunOutcome, RuntimeAgent, ToolInvoker
from app.providers.base import ConnectionTest, ModelCapabilities, ModelPrice, UsageEstimate, estimate_cost
from app.providers.openai_models import CHAT_TEXT


class EchoProvider:
    provider_type = "echo"
    display_name = "Echo (offline test runner)"

    def __init__(self) -> None:
        self.runner: AgentRunner = EchoRunner()

    async def execute(
        self, agent: RuntimeAgent, run_input: RunInput, *, invoke_tool: ToolInvoker, emit: EventEmitter
    ) -> RunOutcome:
        outcome = await self.runner.run(agent, run_input, invoke_tool=invoke_tool, emit=emit)
        words = len(run_input.user_input.split()) + len(agent.instructions.split())
        outcome.usage = {
            **outcome.usage,
            "input_tokens": outcome.usage.get("input_tokens", words),
            "output_tokens": outcome.usage.get("output_tokens", len(outcome.output_text.split())),
        }
        return outcome

    async def test_connection(self, config: dict[str, Any], api_key: str | None) -> ConnectionTest:
        return ConnectionTest(ok=True, message="echo provider is always available", models=["echo-1"])

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        return []

    def get_supported_models(self) -> list[dict[str, Any]]:
        return [{"model": "echo-1", "display_name": "Echo", "capabilities": CHAT_TEXT.as_dict()}]

    def model_capabilities(self, model: str, overrides: dict[str, Any] | None = None) -> ModelCapabilities:
        return CHAT_TEXT

    def calculate_usage(self, model: str, usage: dict[str, Any], price: ModelPrice | None) -> UsageEstimate:
        return estimate_cost(usage, price)
