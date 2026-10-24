"""Uploaded modpack zips: streamed to $MC_ROOT/modpacks/pending, claimed by a server on create."""

import re
import secrets
import time
from collections.abc import AsyncIterator
from pathlib import Path

PENDING_MAX_AGE_SECONDS = 24 * 3600
_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")


class UploadTooLarge(Exception):
    pass


class UploadNotFound(Exception):
    pass


class UploadStore:
    def __init__(self, modpacks_dir: Path) -> None:
        self.modpacks_dir = modpacks_dir
        self.pending_dir = modpacks_dir / "pending"

    def _pending(self, upload_id: str) -> Path:
        if not _UPLOAD_ID.match(upload_id):
            raise UploadNotFound("Unknown upload")
        return self.pending_dir / f"{upload_id}.zip"

    async def save(self, chunks: AsyncIterator[bytes], filename: str, max_bytes: int) -> str:
        """Stream a request body to disk; returns the upload id."""
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.cleanup()
        upload_id = secrets.token_hex(16)
        path = self._pending(upload_id)
        size = 0
        try:
            with path.open("wb") as out:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadTooLarge(f"Upload is larger than {max_bytes // 2**20} MB")
                    out.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        path.with_suffix(".name").write_text(Path(filename).name[:200], encoding="utf-8")
        return upload_id

    def path(self, upload_id: str) -> Path:
        path = self._pending(upload_id)
        if not path.is_file():
            raise UploadNotFound("Upload not found or expired; upload the zip again")
        return path

    def original_name(self, upload_id: str) -> str:
        name_file = self._pending(upload_id).with_suffix(".name")
        return name_file.read_text(encoding="utf-8") if name_file.is_file() else "modpack.zip"

    def discard(self, upload_id: str) -> None:
        path = self._pending(upload_id)
        path.unlink(missing_ok=True)
        path.with_suffix(".name").unlink(missing_ok=True)

    def claim(self, upload_id: str, server_id: int) -> str:
        """Move a pending upload to the server's own zip; returns its file name in modpacks/."""
        source = self.path(upload_id)
        name = f"server-{server_id}.zip"
        source.replace(self.modpacks_dir / name)
        source.with_suffix(".name").unlink(missing_ok=True)
        return name

    def cleanup(self) -> None:
        if not self.pending_dir.is_dir():
            return
        cutoff = time.time() - PENDING_MAX_AGE_SECONDS
        for path in self.pending_dir.iterdir():
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
