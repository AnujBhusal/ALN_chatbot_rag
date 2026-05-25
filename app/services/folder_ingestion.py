"""Folder ingestion wrapper around the centralized transactional ingestion service."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from app import config
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


class FolderIngestionService:
    """Backward-compatible wrapper. All work is delegated to IngestionService."""

    def __init__(self):
        self.ingestion_service = IngestionService()
        self.data_folder = Path(__file__).parent.parent.parent / "data" / "pdfs"

    def ingest_folder(self) -> Dict[str, Any]:
        if not self.data_folder.exists():
            logger.info(f"📁 Data folder not found: {self.data_folder}")
            return {"total": 0, "successful": 0, "failed": 0, "documents": [], "vector_count": 0, "chunk_count": 0, "timing_ms": {}}

        if not config.ENABLE_FOLDER_INGESTION:
            logger.info("⏭️  Folder ingestion disabled by ENABLE_FOLDER_INGESTION=false")
            return {"total": 0, "successful": 0, "failed": 0, "documents": [], "vector_count": 0, "chunk_count": 0, "timing_ms": {}}

        if not config.LOCAL_MODE and not config.ENABLE_FOLDER_INGESTION_ALLOW_PRODUCTION:
            logger.info("🌍 Production folder ingestion disabled unless explicitly enabled")
            return {"total": 0, "successful": 0, "failed": 0, "documents": [], "vector_count": 0, "chunk_count": 0, "timing_ms": {}}

        logger.info(f"📚 Delegating folder ingestion to centralized service for {self.data_folder}")
        return self.ingestion_service.ingest_folder(self.data_folder)
