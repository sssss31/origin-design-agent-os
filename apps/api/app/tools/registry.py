from __future__ import annotations

from app.ports.tools import ToolFunction, ToolSpec

_REGISTRY: dict[str, tuple[ToolSpec, ToolFunction]] = {}


def register(spec: ToolSpec, fn: ToolFunction) -> None:
    _REGISTRY[spec.slug] = (spec, fn)


def get(slug: str) -> tuple[ToolSpec, ToolFunction]:
    return _REGISTRY[slug]


def all_specs() -> list[ToolSpec]:
    return [spec for spec, _ in _REGISTRY.values()]
