"""Slash-command parsing (spec §3, §12 step 1).

A command is the first whitespace-delimited token when it starts with `/` and matches
`/[a-z][a-z0-9_-]*`. Anything else is a plain message that the Manager Agent routes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_COMMAND_RE = re.compile(r"^/([a-z][a-z0-9_-]{0,39})$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ParsedMessage:
    command: str | None
    body: str
    raw: str

    @property
    def is_explicit(self) -> bool:
        return self.command is not None


def normalize_command(value: str) -> str:
    v = value.strip().lower()
    return v if v.startswith("/") else f"/{v}"


def is_valid_command(value: str) -> bool:
    return bool(_COMMAND_RE.match(normalize_command(value)))


def parse_message(text: str) -> ParsedMessage:
    raw = text
    stripped = text.lstrip()
    if not stripped.startswith("/"):
        return ParsedMessage(command=None, body=text.strip(), raw=raw)
    first, _, rest = stripped.partition(" ")
    first = first.split("\n", 1)[0]
    match = _COMMAND_RE.match(first)
    if not match:
        return ParsedMessage(command=None, body=text.strip(), raw=raw)
    remainder = stripped[len(first) :].strip()
    return ParsedMessage(command=f"/{match.group(1).lower()}", body=remainder, raw=raw)
