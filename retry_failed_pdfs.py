#!/usr/bin/env python3
"""Retry failed PDF uploads with extended timeouts"""
import os
import requests
import time
from pathlib import Path

BASE_URL = "https://aln-chatbot-rag.onrender.com/api"

# PDFs that failed in first attempt
FAILED_PDFS = [
    "Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf",
    "General_Document.pdf",
    "Donor_Proposal.pdf",
    "Meeting_Notes.pdf",
]

pdf_folder = Path(__file__).parent

print("=" * 80)
print("📚 RETRY FAILED PDF UPLOADS")
print("=" * 80)

successful = []
failed = []

for pdf_name in FAILED_PDFS:
    pdf_path = pdf_folder / pdf_name
    
    if not pdf_path.exists():
        print(f"\n❌ Not found: {pdf_name}")
        failed.append(pdf_name)
        continue
    
    print(f"\n📄 Uploading {pdf_name}...", end=" ", flush=True)
    
    try:
        with open(pdf_path, "rb") as f:
            files = {"file": (pdf_name, f, "application/pdf")}
            data = {
                "chunk_strategy": "sentence",
                "metadata": {"source": "production"}
            }
            
            # Extended timeout for upload endpoint
            response = requests.post(
                f"{BASE_URL}/ingest/upload",
                files=files,
                data=data,
                timeout=45  # Extended to 45s
            )
        
        if response.status_code == 200:
            result = response.json()
            doc_id = result.get("document_id")
            print(f"✅ Success (ID: {doc_id})")
            successful.append((pdf_name, doc_id))
        else:
            print(f"❌ Server error: {response.status_code}")
            failed.append(pdf_name)
    
    except requests.exceptions.Timeout:
        print(f"❌ Timeout (45s)")
        failed.append(pdf_name)
    except Exception as e:
        print(f"❌ Error: {str(e)[:50]}")
        failed.append(pdf_name)
    
    # Wait between uploads to avoid server overload
    time.sleep(2)

print("\n" + "=" * 80)
print("📊 RETRY SUMMARY")
print("=" * 80)
print(f"✅ Successfully uploaded: {len(successful)}")
for pdf, doc_id in successful:
    print(f"   - {pdf} (ID: {doc_id})")
print(f"❌ Still failed: {len(failed)}")
for pdf in failed:
    print(f"   - {pdf}")
print("\n✅ Total now uploaded: {}/7".format(3 + len(successful)))
print("\n⏳ Documents are processing in background (~1-2 min per PDF)")
