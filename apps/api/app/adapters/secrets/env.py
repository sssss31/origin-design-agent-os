"""Secrets resolved from environment variables (or a mounted secret file). `ref` is the variable name.

Useful for the single-provider V0 server deployment (`OPENAI_API_KEY`) and for managed
secret stores that inject values as environment variables.
"""

from __future__ import annotations

import os

from app.ports.secrets import SecretHandle, fingerprint_of


class EnvSecretStore:
    name = "env"

    async def store(self, name: str, value: str) -> SecretHandle:  # noqa: ARG002 - value is not persisted
        raise PermissionError(
            "EnvSecretStore is read-only; set the environment variable in the deployment instead"
        )

    async def rotate(self, ref: str, value: str) -> SecretHandle:
        raise PermissionError(
            "EnvSecretStore is read-only; rotate the environment variable in the deployment"
        )

    async def reveal(self, ref: str) -> str:
        value = os.environ.get(ref)
        if not value:
            raise LookupError(f"environment variable {ref} is not set")
        return value

    async def delete(self, ref: str) -> None:
        raise PermissionError("EnvSecretStore is read-only")

    async def health(self) -> bool:
        return True

    @staticmethod
    def handle_for(ref: str) -> SecretHandle:
        value = os.environ.get(ref, "")
        return SecretHandle(ref=ref, fingerprint=fingerprint_of(value) if value else "unset", version=1)
