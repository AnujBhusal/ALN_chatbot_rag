#!/usr/bin/env python3
"""
Sync PDFs from data/pdfs/ folder to Render backend.

Features:
- Checks which PDFs already uploaded (avoids duplicates)
- Uploads only new PDFs
- Retry logic for timeouts
- Sequential uploads (no server overload)
- Graceful error handling
- Updates tracking file

Usage:
  python scripts/sync_pdfs_to_render.py
"""

import os
import json
import time
import requests
import hashlib
from pathlib import Path
from typing import Dict, List

# Configuration
RENDER_API_URL = os.getenv("RENDER_BACKEND_URL", "https://aln-chatbot-rag.onrender.com/api")
FORCE_REUPLOAD = os.getenv("FORCE_REUPLOAD", "false").lower() == "true"

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_PDFS_DIR = PROJECT_ROOT / "data" / "pdfs"
TRACKING_FILE = PROJECT_ROOT / ".uploaded_pdfs.json"

# Upload settings
UPLOAD_TIMEOUT = 60  # Extended timeout for Render (60s)
RETRY_COUNT = 3
RETRY_DELAY = 10  # seconds
CHUNK_STRATEGY = "sentence"


def get_file_hash(file_path: Path) -> str:
    """Get SHA256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_tracking_data() -> Dict:
    """Load previously uploaded PDFs tracking data."""
    if TRACKING_FILE.exists():
        try:
            with open(TRACKING_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Failed to load tracking file: {e}")
            return {"uploaded": {}, "failed": {}, "last_sync": None}
    
    return {"uploaded": {}, "failed": {}, "last_sync": None}


def save_tracking_data(data: Dict):
    """Save tracking data."""
    try:
        with open(TRACKING_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"✅ Saved tracking file: {TRACKING_FILE}")
    except Exception as e:
        print(f"❌ Failed to save tracking file: {e}")


def get_existing_documents_on_render() -> Dict[str, int]:
    """
    Query Render backend to get list of already-uploaded documents.
    Returns: {document_title: document_id}
    """
    try:
        response = requests.get(
            f"{RENDER_API_URL}/ingest/documents",
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            documents = result.get("documents", [])
            doc_map = {}
            
            for doc in documents:
                title = doc.get("title", "").strip().lower()
                doc_id = doc.get("id")
                if title and doc_id:
                    doc_map[title] = doc_id
            
            if doc_map:
                print(f"✅ Found {len(doc_map)} existing documents on Render backend:")
                for title, doc_id in list(doc_map.items())[:5]:  # Show first 5
                    print(f"   - {title} (ID: {doc_id})")
                if len(doc_map) > 5:
                    print(f"   ... and {len(doc_map) - 5} more")
            else:
                print("✅ No documents found on Render backend (will upload all)")
            
            return doc_map
        else:
            print(f"⚠️  Could not fetch documents from Render: {response.status_code}")
            return {}
    except Exception as e:
        print(f"⚠️  Could not query Render backend: {str(e)[:100]}")
        print("    Will proceed with local tracking only")
        return {}


def get_new_pdfs(tracking: Dict) -> List[Path]:
    """Find PDFs that haven't been uploaded yet."""
    if not DATA_PDFS_DIR.exists():
        print(f"❌ Data folder not found: {DATA_PDFS_DIR}")
        return []
    
    pdf_files = list(DATA_PDFS_DIR.glob("*.pdf"))
    
    if not pdf_files:
        print(f"📁 No PDFs found in {DATA_PDFS_DIR}")
        return []
    
    print(f"📚 Found {len(pdf_files)} total PDFs in local folder")
    
    if FORCE_REUPLOAD:
        print("🔄 Force reupload mode - uploading all PDFs")
        return sorted(pdf_files)
    
    # Check what's already on Render backend
    print("\n🔍 Checking which PDFs already exist on Render backend...")
    render_docs = get_existing_documents_on_render()
    
    new_pdfs = []
    for pdf_path in pdf_files:
        file_hash = get_file_hash(pdf_path)
        pdf_title = pdf_path.stem.strip().lower()  # Remove .pdf and lowercase
        
        # Check if already on Render
        if pdf_title in render_docs:
            doc_id = render_docs[pdf_title]
            print(f"⏭️  Already on Render: {pdf_path.name} (ID: {doc_id})")
            continue
        
        # Check local tracking
        if pdf_path.name in tracking["uploaded"]:
            stored_hash = tracking["uploaded"][pdf_path.name].get("hash")
            if stored_hash == file_hash:
                print(f"⏭️  Already uploaded: {pdf_path.name}")
                continue
            else:
                print(f"🔄 File changed: {pdf_path.name} (will re-upload)")
        
        print(f"📤 Will upload: {pdf_path.name}")
        new_pdfs.append(pdf_path)
    
    return sorted(new_pdfs)


def upload_pdf_with_retry(pdf_path: Path, attempt: int = 1) -> bool:
    """Upload single PDF with retry logic."""
    print(f"\n📄 Uploading {pdf_path.name}...", end=" ", flush=True)
    
    try:
        with open(pdf_path, "rb") as f:
            files = {"file": (pdf_path.name, f, "application/pdf")}
            data = {
                "chunk_strategy": CHUNK_STRATEGY,
                "metadata": {"source": "github_sync"}
            }
            
            # POST to Render backend
            response = requests.post(
                f"{RENDER_API_URL}/ingest/upload",
                files=files,
                data=data,
                timeout=UPLOAD_TIMEOUT
            )
        
        if response.status_code == 200:
            result = response.json()
            doc_id = result.get("document_id")
            print(f"✅ Success (ID: {doc_id})")
            return True
        else:
            print(f"❌ Server error {response.status_code}")
            return False
    
    except requests.exceptions.Timeout:
        if attempt < RETRY_COUNT:
            print(f"⏱️  Timeout - retrying in {RETRY_DELAY}s (attempt {attempt}/{RETRY_COUNT})...")
            time.sleep(RETRY_DELAY)
            return upload_pdf_with_retry(pdf_path, attempt + 1)
        else:
            print(f"❌ Timeout after {RETRY_COUNT} attempts")
            return False
    
    except requests.exceptions.ConnectionError as e:
        if attempt < RETRY_COUNT:
            print(f"🔌 Connection error - retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
            return upload_pdf_with_retry(pdf_path, attempt + 1)
        else:
            print(f"❌ Connection failed: {str(e)[:50]}")
            return False
    
    except Exception as e:
        print(f"❌ Error: {str(e)[:100]}")
        return False


def main():
    """Main sync function."""
    print("=" * 80)
    print("📚 PDF SYNC TO RENDER BACKEND")
    print("=" * 80)
    
    # Load tracking
    tracking = load_tracking_data()
    
    # Find new PDFs
    new_pdfs = get_new_pdfs(tracking)
    
    if not new_pdfs:
        print("\n✅ All PDFs already uploaded - nothing to do")
        tracking["last_sync"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_tracking_data(tracking)
        return
    
    print(f"\n📤 Uploading {len(new_pdfs)} new PDF(s)...")
    print("=" * 80)
    
    # Upload each PDF
    successful = []
    failed = []
    
    for idx, pdf_path in enumerate(new_pdfs, 1):
        print(f"\n[{idx}/{len(new_pdfs)}]", end=" ")
        
        if upload_pdf_with_retry(pdf_path):
            successful.append(pdf_path)
            
            # Update tracking
            tracking["uploaded"][pdf_path.name] = {
                "hash": get_file_hash(pdf_path),
                "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "size_bytes": pdf_path.stat().st_size
            }
            
            # Remove from failed if it was there
            if pdf_path.name in tracking["failed"]:
                del tracking["failed"][pdf_path.name]
        else:
            failed.append(pdf_path)
            
            # Track failure
            tracking["failed"][pdf_path.name] = {
                "last_error": time.strftime("%Y-%m-%d %H:%M:%S"),
                "retry_count": tracking["failed"].get(pdf_path.name, {}).get("retry_count", 0) + 1
            }
        
        # Wait between uploads to avoid server overload
        if idx < len(new_pdfs):
            time.sleep(2)
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 UPLOAD SUMMARY")
    print("=" * 80)
    print(f"✅ Successful: {len(successful)}/{len(new_pdfs)}")
    for pdf in successful:
        print(f"   ✅ {pdf.name}")
    
    if failed:
        print(f"\n❌ Failed: {len(failed)}/{len(new_pdfs)}")
        for pdf in failed:
            retry_count = tracking["failed"][pdf.name]["retry_count"]
            print(f"   ❌ {pdf.name} (retry #{retry_count})")
    
    print("\n⏳ PDFs processing in background (~1-2 min per file)")
    print("   Check Render logs: https://dashboard.render.com → aln-chatbot-rag → Logs")
    
    # Update tracking
    tracking["last_sync"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tracking["total_uploaded"] = len(tracking["uploaded"])
    save_tracking_data(tracking)
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
