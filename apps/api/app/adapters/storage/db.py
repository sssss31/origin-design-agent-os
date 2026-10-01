"""Object storage inside Postgres (bytea) — for hosts without a durable disk (serverless) when
no S3 bucket is configured. Same interface and signed-URL scheme as the filesystem adapter, so
the `/files/{key}` route serves both. Fine for design assets of a few MB; use S3 for large media."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.storage.local_fs import LocalFSStorage
from app.models.storage import StoredBlob
from app.ports.storage import StoredObject


class DbStorage(LocalFSStorage):
    name = "db"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        signing_key: str,
        public_base_url: str,
    ) -> None:
        # no filesystem root: only the signing helpers of the parent are used
        self._sessions = session_factory
        self._key = signing_key.encode()
        self._base = public_base_url.rstrip("/")

    @staticmethod
    def _check(key: str) -> str:
        if not key or key.startswith("/") or ".." in key.split("/") or len(key) > 512:
            raise ValueError("invalid storage key")
        return key

    async def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject:
        key = self._check(key)
        checksum = hashlib.sha256(data).hexdigest()
        async with self._sessions() as session:
            row = await session.get(StoredBlob, key)
            if row is None:
                row = StoredBlob(key=key)
                session.add(row)
            row.content = data
            row.content_type = content_type
            row.size = len(data)
            row.checksum_sha256 = checksum
            row.created_at = datetime.now(UTC)
            await session.commit()
        return StoredObject(key=key, size=len(data), content_type=content_type, checksum_sha256=checksum)

    async def get(self, key: str) -> bytes:
        key = self._check(key)
        async with self._sessions() as session:
            content = await session.scalar(select(StoredBlob.content).where(StoredBlob.key == key))
        if content is None:
            raise FileNotFoundError(key)
        return bytes(content)

    async def exists(self, key: str) -> bool:
        async with self._sessions() as session:
            return (
                await session.scalar(select(StoredBlob.key).where(StoredBlob.key == self._check(key)))
            ) is not None

    async def delete(self, key: str) -> None:
        async with self._sessions() as session:
            await session.execute(delete(StoredBlob).where(StoredBlob.key == self._check(key)))
            await session.commit()

    async def health(self) -> bool:
        try:
            async with self._sessions() as session:
                await session.scalar(select(StoredBlob.key).limit(1))
            return True
        except Exception:  # noqa: BLE001 - health is a boolean signal
            return False
