"""Pluggable media storage — Local (dev/GPU box) now, S3/MinIO (prod) later.

Keys are relative POSIX paths (e.g. "voices/{id}/ref.wav"). LocalStorage maps
them under MEDIA_ROOT; S3Storage (D7) will map them to a bucket. Swapping the
backend must not touch pipeline code — same contract as the provider layer.
"""
from __future__ import annotations

import os
import shutil
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


def get_storage() -> LocalStorage:
    return LocalStorage(os.getenv("MEDIA_ROOT", "/workspace/media"))
