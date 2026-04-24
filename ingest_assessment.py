#!/usr/bin/env python3
import requests
import os
import sys
from pathlib import Path

# Force UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Production backend URL
BACKEND_URL = "https://aln-chatbot-rag.onrender.com/api/ingest/upload"

FILE_NAME = "Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf"
TITLE = "Assessment Brief CMP6230"
DOC_TYPE = "general"
YEAR = "2024"

def ingest_assessment():
    project_root = Path(__file__).parent
    file_path = project_root / FILE_NAME
    
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return
    
    print(f"\n[INFO] Uploading: {FILE_NAME}")
    
    try:
        with open(file_path, "rb") as f:
            files = {"file": (FILE_NAME, f, "application/pdf")}
            data = {
                "title": TITLE,
                "document_type": DOC_TYPE,
                "year": YEAR,
                "chunk_strategy": "sliding"
            }
            
            response = requests.post(BACKEND_URL, files=files, data=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                print(f"   [SUCCESS] Document ID: {result.get('document_id')}, Chunks: {result.get('chunks_created')}")
            else:
                print(f"   [FAILURE] Failed with status {response.status_code}")
                print(f"   Response: {response.text}")
    
    except Exception as e:
        print(f"   [ERROR] Error: {e}")

if __name__ == "__main__":
    ingest_assessment()
