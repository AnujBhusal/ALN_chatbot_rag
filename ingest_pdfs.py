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
PDFS = [
    {
        "file": "Internal_Policy.pdf",
        "title": "Internal Policy",
        "document_type": "policy",
        "year": 2024,
    },
    {
        "file": "Meeting_Notes.pdf",
        "title": "Meeting Notes",
        "document_type": "meeting",
        "year": 2024,
    },
    {
        "file": "General_Document.pdf",
        "title": "General Document",
        "document_type": "general",
        "year": 2024,
    },
    {
        "file": "Donor_Proposal.pdf",
        "title": "Donor Proposal",
        "document_type": "proposal",
        "year": 2024,
    },
    {
        "file": "Governance_Weekly.pdf",
        "title": "Governance Weekly",
        "document_type": "governance",
        "year": 2024,
    },
    {
        "file": "Integrity_Icon.pdf",
        "title": "Integrity Icon",
        "document_type": "integrity",
        "year": 2024,
    },
]

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
