"""Where screenshots go. Local disk now; the interface lets S3/R2 replace it later.

A stored file is referred to by a key like "<run id>/page-001.png". The web app serves files by
key through an API route, so neither side needs to know where the bytes physically live.
"""

from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> str: ...

    def load(self, key: str) -> bytes: ...


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
