"""Bounded agent memory: trim a provider transcript so it fits the model's context window.

Items are the Responses-style input list the SDK produces (`role` messages, function calls
and their outputs). Trimming always cuts at a *user-message boundary* so a function call is
never separated from its output, which the API rejects.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_CONTEXT_TOKENS = 128_000
CHARS_PER_TOKEN = 3.2
RESERVE_RATIO = 0.35  # leave room for instructions, context summary and the reply
MAX_TURNS = 40


def item_chars(item: dict[str, Any]) -> int:
    try:
        return len(json.dumps(item, ensure_ascii=False))
    except (TypeError, ValueError):
        return len(str(item))


def budget_chars(context_window_tokens: int | None) -> int:
    tokens = context_window_tokens or DEFAULT_CONTEXT_TOKENS
    return int(tokens * CHARS_PER_TOKEN * (1 - RESERVE_RATIO))


def _is_user(item: dict[str, Any]) -> bool:
    return item.get("role") == "user" and item.get("type") in (None, "message")


def trim_input_list(
    items: list[dict[str, Any]], *, max_chars: int, max_turns: int = MAX_TURNS
) -> list[dict[str, Any]]:
    """Keep the most recent complete turns that fit in `max_chars` (and at most `max_turns`)."""
    if not items:
        return []
    boundaries = [i for i, it in enumerate(items) if _is_user(it)]
    if not boundaries:
        boundaries = [0]
    sizes = [item_chars(it) for it in items]
    total = sum(sizes)
    start = boundaries[0]
    turns = len(boundaries)
    for idx, b in enumerate(boundaries):
        remaining_turns = turns - idx
        if total <= max_chars and remaining_turns <= max_turns:
            start = b
            break
        total -= sum(sizes[b : boundaries[idx + 1]] if idx + 1 < len(boundaries) else sizes[b:])
        start = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(items)
    return list(items[start:])


def count_turns(items: list[dict[str, Any]]) -> int:
    return sum(1 for it in items if _is_user(it))
