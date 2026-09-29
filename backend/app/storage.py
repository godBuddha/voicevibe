"""Pluggable media storage — S3/MinIO (prod compose) or Local FS (dev/GPU box).

Keys are relative POSIX paths (e.g. "voices/{id}/ref.wav"). Backend selection
happens ONLY in get_storage(): S3_ENDPOINT set -> S3Storage, else LocalStorage
under MEDIA_ROOT. Swapping the backend must not touch pipeline code — same
contract as the provider layer.

S3 requires env: S3_ENDPOINT (+ S3_ACCESS_KEY / S3_SECRET_KEY, S3_BUCKET).
Local requires env: MEDIA_ROOT (default "./media").
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError(f"invalid storage key: {key!r}")
        return p

    def put(self, key: str, data: bytes) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def put_from_file(self, key: str, src_path: str) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, p)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def get_to_temp(self, key: str) -> str:
        """Local backend: direct path (zero copy). Remote backends copy to tmp."""
        return str(self._path(key))


class S3Storage:
    """MinIO / S3 — same key contract as LocalStorage, via the minio SDK."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str,
                 bucket: str = "voicevibe", secure: bool | None = None):
        from minio import Minio

        if secure is None:
            secure = endpoint.startswith("https://")
        host = endpoint.split("://", 1)[-1]
        self._client = Minio(host, access_key=access_key, secret_key=secret_key,
                             secure=secure)
        self.bucket = bucket
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def put(self, key: str, data: bytes) -> str:
        import io

        self._client.put_object(self.bucket, key, io.BytesIO(data), len(data))
        return key

    def put_from_file(self, key: str, src_path: str) -> str:
        self._client.fput_object(self.bucket, key, src_path)
        return key

    def get(self, key: str) -> bytes:
        resp = self._client.get_object(self.bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def exists(self, key: str) -> bool:
        from minio.error import S3Error

        try:
            self._client.stat_object(self.bucket, key)
            return True
        except S3Error:
            return False

    def get_to_temp(self, key: str) -> str:
        """Download to a tmp file — remote backend, callers need a real path."""
        suffix = "." + key.rsplit(".", 1)[-1] if "." in key else ""
        fd, tmp = tempfile.mkstemp(prefix="s3_", suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(self.get(key))
        return tmp

    def presigned_url(self, key: str, expires_hours: float = 1.0) -> str:
        import datetime

        return self._client.get_presigned_url(
            "GET", self.bucket, key,
            expires=datetime.timedelta(hours=expires_hours))


def get_storage() -> LocalStorage | S3Storage:
    """S3_ENDPOINT set -> S3/MinIO (prod compose); else Local FS under MEDIA_ROOT."""
    endpoint = os.getenv("S3_ENDPOINT")
    if endpoint:
        return S3Storage(
            endpoint,
            os.getenv("S3_ACCESS_KEY", os.getenv("MINIO_ROOT_USER", "minioadmin")),
            os.getenv("S3_SECRET_KEY", os.getenv("MINIO_ROOT_PASSWORD", "")),
            bucket=os.getenv("S3_BUCKET", "voicevibe"),
        )
    return LocalStorage(os.getenv("MEDIA_ROOT", "./media"))
