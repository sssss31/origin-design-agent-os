"""Request templates for custom REST integrations.

Placeholders:
- `{{variable}}` / `{{nested.path}}`  → run-time variables (prompt, workspace_id, asset_url…)
- `{{secrets.name}}`                  → resolved server-side from encrypted secret references

Secret values are never stored inside templates; only the reference name is. In JSON mode
variable values are escaped so a prompt containing quotes cannot break the document.
"""

from __future__ import annotations

import json
import re
from typing import Any

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.\-]*)\s*\}\}")
SECRET_PREFIX = "secrets."


class MissingSecret(KeyError):
    pass


def placeholders(template: str | None) -> list[str]:
    return list(dict.fromkeys(PLACEHOLDER.findall(template or "")))


def variables_in(*templates: str | None) -> list[str]:
    out: list[str] = []
    for t in templates:
        for name in placeholders(t):
            if not name.startswith(SECRET_PREFIX) and name not in out:
                out.append(name)
    return out


def secrets_in(*templates: str | None) -> list[str]:
    out: list[str] = []
    for t in templates:
        for name in placeholders(t):
            if name.startswith(SECRET_PREFIX):
                short = name[len(SECRET_PREFIX) :]
                if short not in out:
                    out.append(short)
    return out


def _lookup(variables: dict[str, Any], path: str) -> Any:
    cur: Any = variables
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def render(
    template: str | None,
    *,
    variables: dict[str, Any],
    secrets: dict[str, str],
    json_mode: bool = False,
    strict_secrets: bool = True,
) -> str:
    if not template:
        return ""

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name.startswith(SECRET_PREFIX):
            key = name[len(SECRET_PREFIX) :]
            if key not in secrets:
                if strict_secrets:
                    raise MissingSecret(key)
                return ""
            value: Any = secrets[key]
        else:
            value = _lookup(variables, name)
            if value is None:
                value = ""
        if isinstance(value, dict | list):
            text = json.dumps(value, ensure_ascii=False)
            return text if json_mode else text
        text = str(value)
        if json_mode:
            return json.dumps(text, ensure_ascii=False)[1:-1]
        return text

    return PLACEHOLDER.sub(sub, template)


def render_mapping(
    mapping: dict[str, str],
    *,
    variables: dict[str, Any],
    secrets: dict[str, str],
    strict_secrets: bool = True,
) -> dict[str, str]:
    return {
        k: render(v, variables=variables, secrets=secrets, strict_secrets=strict_secrets)
        for k, v in mapping.items()
    }


def mask_secrets(text: str, secrets: dict[str, str]) -> str:
    """Replace any secret value that leaked into a rendered preview with a mask."""
    for value in sorted(secrets.values(), key=len, reverse=True):
        if value and len(value) >= 4:
            text = text.replace(value, "••••••••")
    return text


def input_schema_for(variables: list[str]) -> dict[str, Any]:
    """JSON schema an agent sees for a custom API tool: every template variable is a string."""
    return {
        "type": "object",
        "properties": {
            v.split(".")[0]: {"type": "string", "description": f"value for {{{{{v}}}}}"} for v in variables
        },
        "additionalProperties": True,
    }
