"""Signed-URL download endpoint used by the local filesystem storage adapter.

S3-compatible backends presign directly against the bucket, so this route is only
mounted when `STORAGE_BACKEND=local`.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app.adapters.storage.local_fs import LocalFSStorage
from app.core.errors import Forbidden, NotFound

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{key:path}")
async def download_local_file(
    key: str,
    request: Request,
    expires: int = Query(...),
    signature: str = Query(...),
    filename: str | None = Query(default=None),
) -> Response:
    storage = request.app.state.adapters.storage
    if not isinstance(storage, LocalFSStorage):
        raise NotFound("Not found")
    if not storage.verify(key, expires, signature):
        raise Forbidden("Signed URL is invalid or expired", code="bad_signature")
    try:
        data = await storage.get(key)
    except (FileNotFoundError, ValueError) as exc:
        raise NotFound("File not found") from exc
    headers = {"Cache-Control": "private, max-age=0, no-store"}
    if filename:
        safe = filename.replace('"', "")
        headers["Content-Disposition"] = f'attachment; filename="{safe}"'
    # Never render uploaded HTML/SVG inline on the app origin (spec §17).
    headers["X-Content-Type-Options"] = "nosniff"
    headers["Content-Security-Policy"] = "sandbox"
    return Response(content=data, media_type=LocalFSStorage.guess_type(key), headers=headers)
