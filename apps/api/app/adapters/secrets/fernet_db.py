"""Secrets encrypted with Fernet (AES-128-CBC + HMAC) and stored in `secret_refs`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.governance import SecretRef
from app.ports.secrets import SecretHandle, fingerprint_of


class SecretNotFound(LookupError):
    pass


class FernetSecretStore:
    name = "fernet"

    def __init__(self, key: str, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._fernet = Fernet(key.encode())
        self._sessions = session_factory

    async def store(self, name: str, value: str) -> SecretHandle:
        row = SecretRef(
            name=name,
            backend=self.name,
            ciphertext=self._fernet.encrypt(value.encode()).decode(),
            fingerprint=fingerprint_of(value),
            version=1,
        )
        async with self._sessions() as session:
            session.add(row)
            await session.commit()
            return SecretHandle(ref=str(row.id), fingerprint=row.fingerprint, version=row.version)

    async def rotate(self, ref: str, value: str) -> SecretHandle:
        async with self._sessions() as session:
            row = await session.get(SecretRef, uuid.UUID(ref))
            if row is None:
                raise SecretNotFound(ref)
            row.ciphertext = self._fernet.encrypt(value.encode()).decode()
            row.fingerprint = fingerprint_of(value)
            row.version += 1
            row.rotated_at = datetime.now(UTC)
            await session.commit()
            return SecretHandle(ref=str(row.id), fingerprint=row.fingerprint, version=row.version)

    async def reveal(self, ref: str) -> str:
        async with self._sessions() as session:
            row = await session.scalar(select(SecretRef).where(SecretRef.id == uuid.UUID(ref)))
            if row is None or not row.ciphertext:
                raise SecretNotFound(ref)
            try:
                return self._fernet.decrypt(row.ciphertext.encode()).decode()
            except InvalidToken as exc:
                raise SecretNotFound(f"{ref}: cannot decrypt with current ENCRYPTION_KEY") from exc

    async def delete(self, ref: str) -> None:
        async with self._sessions() as session:
            row = await session.get(SecretRef, uuid.UUID(ref))
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def health(self) -> bool:
        return True
