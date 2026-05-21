#!/usr/bin/env python3
"""
Script to ingest PDFs into the production RAG backend.
Usage: python ingest_pdfs.py
"""

import requests
import os
from pathlib import Path

# Production backend URL
BACKEND_URL = "https://aln-chatbot-rag.onrender.com/api/ingest/upload"

# PDF files with their metadata
from typing import List


def discover_pdfs(directory: str = "data/pdfs") -> List[dict]:
    """Discover PDF files under `data/pdfs` and generate simple metadata.

    - Title is derived from filename (stem, underscores/hyphens -> spaces).
    - document_type and year are guessed from filename when possible.
    """
    pdf_dir = Path(directory)
    found: List[dict] = []
    if not pdf_dir.exists():
        print(f"⚠️ PDF directory not found: {pdf_dir} — no files will be uploaded")
        return found

    for p in sorted(pdf_dir.glob("*.pdf")):
        stem = p.stem
        title = stem.replace("_", " ").replace("-", " ")
        lower = stem.lower()

        # simple heuristics for document type
        if "meeting" in lower or "minutes" in lower:
            doc_type = "meeting"
        elif "policy" in lower:
            doc_type = "policy"
        elif "proposal" in lower or "donor" in lower:
            doc_type = "proposal"
        elif "governance" in lower:
            doc_type = "governance"
        elif "integrity" in lower:
            doc_type = "integrity"
        else:
            doc_type = "general"

        # try to find a 4-digit year in the filename
        import re

        year_match = re.search(r"(20\d{2}|19\d{2})", stem)
        year = int(year_match.group(0)) if year_match else 2024

        found.append({"file": p.name, "title": title, "document_type": doc_type, "year": year})

    return found


# Discover PDFs from data/pdfs by default
PDFS = discover_pdfs()

def ingest_pdfs():
    """Upload all PDFs to the backend."""
    project_root = Path(__file__).parent
    success_count = 0
    fail_count = 0
    
    for pdf_info in PDFS:
        file_path = project_root / pdf_info["file"]
        
        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            fail_count += 1
            continue
        
        print(f"\n📄 Uploading: {pdf_info['file']}")
        print(f"   Title: {pdf_info['title']}")
        print(f"   Type: {pdf_info['document_type']}")
        print(f"   Year: {pdf_info['year']}")
        
        try:
            with open(file_path, "rb") as f:
                files = {"file": (pdf_info["file"], f, "application/pdf")}
                data = {
                    "title": pdf_info["title"],
                    "document_type": pdf_info["document_type"],
                    "year": str(pdf_info["year"]),
                }
                
                # Add chunk_strategy to data
                data["chunk_strategy"] = "sliding"
                
                response = requests.post(BACKEND_URL, files=files, data=data, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    doc_id = result.get("document_id")
                    chunk_count = result.get("chunks_created", 0)
                    print(f"   ✅ Success! Document ID: {doc_id}, Chunks: {chunk_count}")
                    success_count += 1
                else:
                    print(f"   ❌ Failed with status {response.status_code}")
                    print(f"   Response: {response.text}")
                    fail_count += 1
        
        except Exception as e:
            print(f"   ❌ Error: {e}")
            fail_count += 1
    
    print("\n" + "="*60)
    print(f"✅ Successfully ingested: {success_count}")
    print(f"❌ Failed: {fail_count}")
    print("="*60)

if __name__ == "__main__":
    print("🚀 Starting PDF ingestion into production...\n")
    ingest_pdfs()
