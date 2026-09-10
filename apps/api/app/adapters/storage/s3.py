"""S3-compatible object storage (AWS S3, Cloudflare R2, MinIO). boto3 is sync, so calls run in a thread."""

from __future__ import annotations

import asyncio
import hashlib
from functools import partial
from typing import Any

from app.ports.storage import StoredObject


class S3Storage:
    name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        access_key: str | None,
        secret_key: str | None,
        region: str = "auto",
        public_endpoint_url: str | None = None,
    ) -> None:
        import boto3
        from botocore.config import Config

        cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=cfg,
        )
        # Presigned URLs must be reachable by the browser; inside Docker the internal endpoint differs.
        self._presign_client = (
            boto3.client(
                "s3",
                endpoint_url=public_endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
                config=cfg,
            )
            if public_endpoint_url
            else self._client
        )

    async def _call(self, fn: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(partial(fn, **kwargs))

    async def put(self, key: str, data: bytes, *, content_type: str) -> StoredObject:
        await self._call(
            self._client.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )
        return StoredObject(
            key=key,
            size=len(data),
            content_type=content_type,
            checksum_sha256=hashlib.sha256(data).hexdigest(),
        )

    async def get(self, key: str) -> bytes:
        obj = await self._call(self._client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(obj["Body"].read)

    async def exists(self, key: str) -> bool:
        try:
            await self._call(self._client.head_object, Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> None:
        await self._call(self._client.delete_object, Bucket=self.bucket, Key=key)

    async def presign_download(self, key: str, *, expires_in: int, filename: str | None = None) -> str:
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return await self._call(
            self._presign_client.generate_presigned_url,
            ClientMethod="get_object",
            Params=params,
            ExpiresIn=expires_in,
        )

    async def health(self) -> bool:
        try:
            await self._call(self._client.head_bucket, Bucket=self.bucket)
            return True
        except Exception:
            return False

    async def ensure_bucket(self) -> None:
        try:
            await self._call(self._client.head_bucket, Bucket=self.bucket)
        except Exception:
            await self._call(self._client.create_bucket, Bucket=self.bucket)
