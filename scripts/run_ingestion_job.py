"""
Direct ingestion job runner using the centralized transactional service.

Examples:
  python scripts/run_ingestion_job.py --file "data/pdfs/example.pdf"
  python scripts/run_ingestion_job.py --folder "data/pdfs"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.ingestion_service import IngestionService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Single PDF file to ingest")
    parser.add_argument("--folder", help="Folder of PDFs to ingest")
    parser.add_argument("--chunk-strategy", default="sentence", choices=["sentence", "sliding"])
    args = parser.parse_args()

    service = IngestionService()

    if args.file:
        result = service.ingest_pdf_path(Path(args.file), chunk_strategy=args.chunk_strategy, source="script")
        print(json.dumps(result.to_dict(), indent=2))
        return

    if args.folder:
        result = service.ingest_folder(Path(args.folder))
        print(json.dumps(result, indent=2))
        return

    parser.error("Provide either --file or --folder")


if __name__ == "__main__":
    main()
