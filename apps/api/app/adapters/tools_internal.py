"""ToolExecutor for `internal_function` tools: schema-validated, timed, redacted."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import jsonschema

from app.core.logging import redact
from app.ports.tools import ExecutorType, ToolCall, ToolFunction, ToolResult


class InternalFunctionExecutor:
    executor_type = ExecutorType.INTERNAL_FUNCTION

    def __init__(self, functions: dict[str, ToolFunction]) -> None:
        self._functions = functions

    async def execute(self, call: ToolCall) -> ToolResult:
        started = time.perf_counter()
        fn = self._functions.get(call.tool.slug)
        if fn is None:
            return ToolResult(ok=False, error_code="tool_not_registered", error_message=call.tool.slug)
        try:
            jsonschema.validate(call.arguments, call.tool.input_schema)
        except jsonschema.ValidationError as exc:
            return ToolResult(ok=False, error_code="invalid_input", error_message=exc.message)
        try:
            output: dict[str, Any] = await asyncio.wait_for(
                fn(call.arguments), timeout=call.tool.timeout_seconds
            )
        except TimeoutError:
            return ToolResult(
                ok=False, error_code="timeout", error_message=f"exceeded {call.tool.timeout_seconds}s"
            )
        except Exception as exc:
            return ToolResult(ok=False, error_code="tool_error", error_message=redact(str(exc)))
        files = list(output.pop("files", []) or []) if isinstance(output, dict) else []
        if call.tool.output_schema:
            try:
                jsonschema.validate(output, call.tool.output_schema)
            except jsonschema.ValidationError as exc:
                return ToolResult(ok=False, error_code="invalid_output", error_message=exc.message)
        return ToolResult(
            ok=True,
            output=redact(output),
            duration_ms=int((time.perf_counter() - started) * 1000),
            files=files,
        )
