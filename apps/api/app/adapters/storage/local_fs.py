"""Filesystem object storage for development and tests. Same interface as S3."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import mimetypes
import time
from pathlib import Path
from urllib.parse import quote

from app.ports.storage import StoredObject


class LocalFSStorage:
    name = "local"

    def __init__(self, root: str | Path, *, signing_key: str, public_base_url: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._key = signing_key.encode()
        self._base = public_base_url.rstrip("/")

    def _path(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ValueError("invalid storage key")
        path = (self.root / key).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("storage key escapes root")
        return path

    async def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject:
        path = self._path(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(path)

        await asyncio.to_thread(_write)
        return StoredObject(
            key=key,
            size=len(data),
            content_type=content_type,
            checksum_sha256=hashlib.sha256(data).hexdigest(),
        )

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return await asyncio.to_thread(path.read_bytes)

    async def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            await asyncio.to_thread(path.unlink)

    def sign(self, key: str, expires_at: int) -> str:
        msg = f"{key}:{expires_at}".encode()
        return (
            base64.urlsafe_b64encode(hmac.new(self._key, msg, hashlib.sha256).digest()).decode().rstrip("=")
        )

    def verify(self, key: str, expires_at: int, signature: str) -> bool:
        if expires_at < int(time.time()):
            return False
        return hmac.compare_digest(self.sign(key, expires_at), signature)

    async def presign_download(self, key: str, *, expires_in: int, filename: str | None = None) -> str:
        expires_at = int(time.time()) + expires_in
        sig = self.sign(key, expires_at)
        url = f"{self._base}/files/{quote(key, safe='/')}?expires={expires_at}&signature={sig}"
        if filename:
            url += f"&filename={quote(filename)}"
        return url

    async def health(self) -> bool:
        return self.root.is_dir()

    @staticmethod
    def guess_type(key: str) -> str:
        return mimetypes.guess_type(key)[0] or "application/octet-stream"
