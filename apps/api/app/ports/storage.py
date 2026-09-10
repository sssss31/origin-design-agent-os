from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int
    content_type: str
    checksum_sha256: str


@runtime_checkable
class ObjectStorage(Protocol):
    """Private-bucket object storage. Browsers never get bucket credentials, only signed URLs."""

    name: str

    async def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject: ...

    async def get(self, key: str) -> bytes: ...

    async def exists(self, key: str) -> bool: ...

    async def delete(self, key: str) -> None: ...

    async def presign_download(self, key: str, *, expires_in: int, filename: str | None = None) -> str: ...

    async def health(self) -> bool: ...
