"""Where screenshots go: local disk (development) or any S3-compatible store (production:
MinIO, AWS S3, Cloudflare R2), chosen by STORAGE=local|s3 (run 4, J6).

A stored file is referred to by a key like "<run id>/page-001.png". The web app serves files by
key through an API route that checks access first (and, with S3, redirects to a signed link
that expires), so neither side needs to know where the bytes physically live.
"""

import posixpath
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> str: ...

    def load(self, key: str) -> bytes: ...

    def delete_prefix(self, prefix: str) -> int:
        """Delete every file under `prefix` (a run's folder); returns how many."""
        ...


def _safe_key(key: str) -> str:
    """Keys are relative paths that never climb out ("../") and are never empty."""
    normal = posixpath.normpath(key)
    if not key or normal.startswith(("../", "/")) or normal == "..":
        raise ValueError(f"storage key escapes the storage root: {key!r}")
    return normal


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        # Refuse keys like "../../etc/passwd": every file must stay inside the storage root.
        if not path.is_relative_to(self.root):
            raise ValueError(f"storage key escapes the storage root: {key!r}")
        return path

    def save(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete_prefix(self, prefix: str) -> int:
        folder = self._path(_safe_key(prefix.rstrip("/")))
        if not folder.is_dir():
            return 0
        files = [p for p in folder.rglob("*") if p.is_file()]
        for file in files:
            file.unlink()
        for directory in sorted((p for p in folder.rglob("*") if p.is_dir()), reverse=True):
            directory.rmdir()
        folder.rmdir()
        return len(files)


class S3Storage:
    """Any S3-compatible store. `endpoint_url` points at MinIO or R2; None means AWS."""

    def __init__(
        self, bucket: str, region: str, endpoint_url: str | None, access_key: str, secret_key: str
    ):
        import boto3

        self.bucket = bucket
        self._bucket_ready = False
        self._s3 = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def _ensure_bucket(self) -> None:
        """Create the bucket the first time it's needed, if it doesn't exist (a fresh store)."""
        if self._bucket_ready:
            return
        from botocore.exceptions import ClientError

        try:
            self._s3.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._s3.create_bucket(Bucket=self.bucket)
        self._bucket_ready = True

    def save(self, key: str, data: bytes) -> str:
        key = _safe_key(key)
        self._ensure_bucket()
        content_type = "image/png" if key.endswith(".png") else "application/octet-stream"
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def load(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self.bucket, Key=_safe_key(key))["Body"].read()

    def delete_prefix(self, prefix: str) -> int:
        prefix = _safe_key(prefix.rstrip("/")) + "/"
        deleted = 0
        for page in self._s3.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=prefix
        ):
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                self._s3.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})
                deleted += len(keys)
        return deleted


def make_storage(settings) -> Storage:
    if settings.storage == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint or None,
            access_key=settings.s3_access_key.get_secret_value(),
            secret_key=settings.s3_secret_key.get_secret_value(),
        )
    return LocalStorage(settings.data_path())
