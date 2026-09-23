from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SecretHandle:
    """What the rest of the system is allowed to hold: a reference and a display hint."""

    ref: str
    fingerprint: str
    version: int


@runtime_checkable
class SecretStore(Protocol):
    name: str

    async def store(self, name: str, value: str) -> SecretHandle: ...

    async def rotate(self, ref: str, value: str) -> SecretHandle: ...

    async def reveal(self, ref: str) -> str:
        """Server-side only. Never call from a request handler that serializes the result."""
        ...

    async def delete(self, ref: str) -> None: ...

    async def health(self) -> bool: ...


def key_preview(value: str) -> str:
    """Masked display form such as `sk-proj-••••••••7Xk2`: recognisable prefix + last 4 chars.

    Computed once when the secret is written and stored next to the reference; the secret
    itself is never read back to build it.
    """
    v = value.strip()
    if len(v) < 12:
        return "••••••••"
    prefix = ""
    for candidate in ("sk-proj-", "sk-svcacct-", "sk-admin-", "sk-"):
        if v.startswith(candidate):
            prefix = candidate
            break
    if not prefix and "-" in v[:12]:
        prefix = v[: v.index("-") + 1]
    return f"{prefix}••••••••{v[-4:]}"


def fingerprint_of(value: str) -> str:
    """Stable, non-reversible display hint (e.g. `…a1b2`). Never the tail of the secret itself."""
    import hashlib

    return "…" + hashlib.sha256(value.encode()).hexdigest()[:6]
