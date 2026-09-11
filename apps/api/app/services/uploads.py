"""Shared upload validation + storage for assets, artifacts and skill files (spec §17)."""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from dataclasses import dataclass

from app.core.errors import ValidationFailed
from app.ports.storage import ObjectStorage, StoredObject

ALLOWED_UPLOAD_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/svg+xml": "svg",
    "application/pdf": "pdf",
    "application/json": "json",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/csv": "csv",
    "font/ttf": "ttf",
    "font/otf": "otf",
    "font/woff": "woff",
    "font/woff2": "woff2",
    "application/zip": "zip",
}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True)
class UploadInfo:
    stored: StoredObject
    filename: str
    mime_type: str
    checksum: str
    width: int | None
    height: int | None
    metadata: dict


def safe_filename(name: str, fallback: str = "file") -> str:
    base = name.replace("\\", "/").split("/")[-1]
    base = _SAFE.sub("_", base).strip("._") or fallback
    return base[:200]


def validate_upload(*, filename: str, content_type: str, size: int, max_bytes: int) -> str:
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_UPLOAD_TYPES:
        raise ValidationFailed(f"file type {mime or 'unknown'} is not allowed", code="unsupported_file_type")
    if size <= 0:
        raise ValidationFailed("empty file", code="empty_file")
    if size > max_bytes:
        raise ValidationFailed(f"file exceeds {max_bytes // (1024 * 1024)} MB", code="file_too_large")
    ext = "." + ALLOWED_UPLOAD_TYPES[mime]
    if not filename.lower().endswith(ext) and not (
        mime == "image/jpeg" and filename.lower().endswith(".jpeg")
    ):
        raise ValidationFailed(f"filename extension does not match {mime}", code="extension_mismatch")
    return mime


def sniff_image(data: bytes, mime: str) -> tuple[int | None, int | None, dict]:
    if not mime.startswith("image/") or mime == "image/svg+xml":
        return None, None, {}
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            dpi = im.info.get("dpi")
            meta: dict[str, object] = {"mode": im.mode, "format": im.format}
            if dpi:
                meta["dpi"] = int(dpi[0])
            return im.width, im.height, meta
    except Exception:
        return None, None, {"image_readable": False}


async def store_upload(
    storage: ObjectStorage, *, key_prefix: str, filename: str, content_type: str, data: bytes, max_bytes: int
) -> UploadInfo:
    mime = validate_upload(filename=filename, content_type=content_type, size=len(data), max_bytes=max_bytes)
    name = safe_filename(filename)
    key = f"{key_prefix}/{uuid.uuid4().hex}-{name}"
    stored = await storage.put(key, data, content_type=mime)
    width, height, meta = sniff_image(data, mime)
    return UploadInfo(
        stored=stored,
        filename=name,
        mime_type=mime,
        checksum=hashlib.sha256(data).hexdigest(),
        width=width,
        height=height,
        metadata=meta,
    )
