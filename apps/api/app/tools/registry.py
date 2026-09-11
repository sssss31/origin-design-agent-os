"""Registry of built-in tools. Each entry is a ToolSpec + async function(args, ToolContext).

Seeding turns every spec into an editable `tools` row (`executor_type=internal_function`);
at run time the executor binds the ToolContext and validates against the *stored* schema so
admins can tighten inputs without touching code.
"""

from __future__ import annotations

from typing import Any

from app.adapters.tools_internal import InternalFunctionExecutor
from app.ports.tools import ToolFunction, ToolSpec
from app.tools.context import ToolContext, ToolFn

_REGISTRY: dict[str, tuple[ToolSpec, ToolFn]] = {}


def register(spec: ToolSpec, fn: ToolFn) -> None:
    _REGISTRY[spec.slug] = (spec, fn)


def get(slug: str) -> tuple[ToolSpec, ToolFn]:
    return _REGISTRY[slug]


def all_specs() -> list[ToolSpec]:
    return [spec for spec, _ in _REGISTRY.values()]


def has(slug: str) -> bool:
    return slug in _REGISTRY


def bound_executor(ctx: ToolContext) -> InternalFunctionExecutor:
    functions: dict[str, ToolFunction] = {slug: _bind(fn, ctx) for slug, (_, fn) in _REGISTRY.items()}
    return InternalFunctionExecutor(functions)


def _bind(fn: ToolFn, ctx: ToolContext) -> ToolFunction:
    async def call(args: dict[str, Any]) -> dict[str, Any]:
        return await fn(args, ctx)

    return call


def load_builtins() -> None:
    """Import tool modules so they register themselves (idempotent)."""
    from app.tools import builtin  # noqa: F401
