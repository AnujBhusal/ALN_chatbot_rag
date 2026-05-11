#!/usr/bin/env python3
import json
import os
import hashlib
from pathlib import Path
import urllib.request
import urllib.error

RENDER_API_URL = "https://aln-chatbot-rag.onrender.com/api"
PROJECT_ROOT = Path(__file__).parent
DATA_PDFS_DIR = PROJECT_ROOT / "data" / "pdfs"

def get_file_hash(file_path):
    """Get SHA256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

print("📁 Checking PDFs in data/pdfs/...")
if not DATA_PDFS_DIR.exists():
    print(f"❌ {DATA_PDFS_DIR} not found")
    exit(1)

pdfs = list(DATA_PDFS_DIR.glob("*.pdf"))
print(f"Found {len(pdfs)} PDFs:")
for pdf in pdfs:
    print(f"  - {pdf.name}")

# Try to upload Governance_Weekly.pdf
governance_pdf = DATA_PDFS_DIR / "Governance_Weekly.pdf"
if governance_pdf.exists():
    print(f"\n📤 Uploading {governance_pdf.name}...")
    
    with open(governance_pdf, "rb") as f:
        files = {'file': (governance_pdf.name, f, 'application/pdf')}
        
        # Create multipart form data manually
        boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
        body = b''
        
        for key, (filename, fileobj, filetype) in files.items():
            file_data = fileobj.read()
            body += f'--{boundary}\r\n'.encode()
            body += f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
            body += f'Content-Type: {filetype}\r\n\r\n'.encode()
            body += file_data + b'\r\n'
        
        body += f'--{boundary}--\r\n'.encode()
        
        try:
            req = urllib.request.Request(
                f"{RENDER_API_URL}/ingest/upload",
                data=body,
                headers={
                    'Content-Type': f'multipart/form-data; boundary={boundary}'
                },
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read())
                print(f"✅ Upload successful!")
                print(f"   Document ID: {result.get('document_id')}")
                print(f"   Chunks: {result.get('chunks_created')}")
        except Exception as e:
            print(f"❌ Upload failed: {e}")

# Check what's on backend now
print("\n📚 Checking backend documents...")
try:
    req = urllib.request.Request(f"{RENDER_API_URL}/ingest/documents", method="GET")
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read())
        print(f"Total: {data.get('total')} documents")
        for doc in data.get('documents', []):
            print(f"  - {doc.get('title')} ({doc.get('chunks')} chunks)")
except Exception as e:
    print(f"❌ Error: {e}")
