"""Default capability matrix for OpenAI models.

These are *defaults*: the admin can override any flag per model in the provider's model
allowlist (`provider_models.capabilities`), which takes precedence. Unknown models get the
conservative profile (no temperature/top_p) so a request is never rejected for an
unsupported parameter; the admin can then enable flags explicitly.
"""

from __future__ import annotations

from typing import Any

from app.providers.base import ModelCapabilities

REASONING = ModelCapabilities(
    supports_reasoning=True,
    supports_vision=True,
    supports_tools=True,
    notes="Reasoning model: temperature/top_p are not accepted; use reasoning.effort.",
)
CHAT = ModelCapabilities(
    supports_temperature=True,
    supports_top_p=True,
    supports_vision=True,
    supports_tools=True,
    notes="Chat model: temperature and top_p accepted.",
)
CHAT_TEXT = ModelCapabilities(
    supports_temperature=True,
    supports_top_p=True,
    supports_vision=False,
    supports_tools=True,
)
IMAGE = ModelCapabilities(
    supports_tools=False,
    supports_structured_output=False,
    supports_image_generation=True,
    max_output_tokens_param=None,
    notes="Image model: used by the image.generate tool, not as an agent model.",
)
UNKNOWN = ModelCapabilities(notes="Unknown model: only universally supported parameters are sent.")

# Ordered prefix rules; first match wins.
_RULES: list[tuple[str, ModelCapabilities]] = [
    ("gpt-image", IMAGE),
    ("dall-e", IMAGE),
    ("gpt-5", REASONING),
    ("o1", REASONING),
    ("o3", REASONING),
    ("o4", REASONING),
    ("gpt-4o", CHAT),
    ("gpt-4.1", CHAT),
    ("gpt-4", CHAT),
    ("chatgpt", CHAT),
    ("gpt-3.5", CHAT_TEXT),
    ("echo", CHAT_TEXT),
]

_OVERRIDE_KEYS = {
    "supports_temperature",
    "supports_top_p",
    "supports_reasoning",
    "supports_vision",
    "supports_tools",
    "supports_structured_output",
    "supports_image_generation",
    "max_output_tokens_param",
    "context_window",
    "max_output_tokens",
    "notes",
}


def default_capabilities(model: str) -> ModelCapabilities:
    m = model.lower().strip()
    for prefix, caps in _RULES:
        if m.startswith(prefix):
            return caps
    return UNKNOWN


def resolve_capabilities(model: str, overrides: dict[str, Any] | None = None) -> ModelCapabilities:
    base = default_capabilities(model)
    if not overrides:
        return base
    data = base.as_dict()
    for k, v in overrides.items():
        if k in _OVERRIDE_KEYS and v is not None:
            data[k] = v
    # legacy allowlist flags used before the matrix existed
    if overrides.get("vision") is True:
        data["supports_vision"] = True
    if overrides.get("image_generation") is True:
        data["supports_image_generation"] = True
    return ModelCapabilities(**data)


def is_agent_model(model: str, overrides: dict[str, Any] | None = None) -> bool:
    return not resolve_capabilities(model, overrides).supports_image_generation
