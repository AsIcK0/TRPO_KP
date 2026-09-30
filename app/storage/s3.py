"""S3-совместимое хранилище (MinIO) через aioboto3."""

import logging
from collections.abc import AsyncIterator
from functools import lru_cache

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)
_MISSING_CODES = {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = aioboto3.Session()
        self._config = Config(signature_version="s3v4", s3={"addressing_style": "path"},
                              connect_timeout=5, read_timeout=30, retries={"max_attempts": 2})

    def _client(self):
        s = self._settings
        return self._session.client("s3", endpoint_url=s.s3_endpoint, aws_access_key_id=s.s3_access_key,
                                    aws_secret_access_key=s.s3_secret_key, region_name=s.s3_region,
                                    config=self._config)

    @property
    def bucket(self) -> str:
        return self._settings.s3_bucket

    async def ensure_bucket(self) -> None:
        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self.bucket)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in _MISSING_CODES:
                    raise
                await s3.create_bucket(Bucket=self.bucket)
                logger.info("Создан S3-бакет %s", self.bucket)

    async def check(self) -> bool:
        async with self._client() as s3:
            await s3.head_bucket(Bucket=self.bucket)
        return True

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        async with self._client() as s3:
            await s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    async def exists(self, key: str) -> bool:
        async with self._client() as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in _MISSING_CODES:
                    return False
                raise

    async def stream(self, key: str, chunk_size: int = 64 * 1024) -> AsyncIterator[bytes]:
        async with self._client() as s3:
            obj = await s3.get_object(Bucket=self.bucket, Key=key)
            async for chunk in obj["Body"].iter_chunks(chunk_size):
                yield chunk

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def get_storage() -> S3Storage:
    return S3Storage(get_settings())
