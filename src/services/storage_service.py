"""File storage service for redesign outputs (HTML, screenshots, images)."""

from __future__ import annotations

import logging
from pathlib import Path

from src.config import get_settings

logger = logging.getLogger(__name__)


class StorageService:
    """Manages file storage for redesign outputs."""

    def __init__(self) -> None:
        settings = get_settings()
        self._backend = settings.storage.backend
        self._local_path = Path(settings.storage.local_path)

    async def initialize(self) -> None:
        if self._backend == "local":
            self._local_path.mkdir(parents=True, exist_ok=True)
            logger.info("Local storage initialized at %s", self._local_path)

    def get_job_dir(self, job_id: str) -> Path:
        """Get the storage directory for a specific job."""
        job_dir = self._local_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    async def store_html(self, job_id: str, html: str, filename: str = "redesign.html") -> str:
        """Store redesigned HTML and return the path."""
        job_dir = self.get_job_dir(job_id)
        file_path = job_dir / filename
        file_path.write_text(html, encoding="utf-8")
        logger.info("Stored HTML: %s (%d chars)", file_path, len(html))
        return str(file_path)

    async def store_bytes(self, job_id: str, data: bytes, filename: str) -> str:
        """Store binary data (screenshots, images) and return the path."""
        job_dir = self.get_job_dir(job_id)
        file_path = job_dir / filename
        file_path.write_bytes(data)
        logger.info("Stored file: %s (%d bytes)", file_path, len(data))
        return str(file_path)

    async def retrieve(self, path: str) -> bytes | None:
        """Retrieve file data from storage path."""
        file_path = Path(path)
        if file_path.exists():
            return file_path.read_bytes()
        logger.warning("File not found: %s", path)
        return None

    async def retrieve_text(self, path: str) -> str | None:
        """Retrieve text file from storage path."""
        file_path = Path(path)
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        logger.warning("File not found: %s", path)
        return None

    async def delete(self, path: str) -> bool:
        """Delete a file."""
        file_path = Path(path)
        if file_path.exists():
            file_path.unlink()
            return True
        return False
