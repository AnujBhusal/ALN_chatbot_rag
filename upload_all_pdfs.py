#!/usr/bin/env python3
"""
Complete PDF upload management for Render backend.
- Cleans up duplicate documents
- Uploads all PDFs from the project
- Tracks progress and provides detailed feedback
"""
import requests
from pathlib import Path
import time

BASE_URL = "https://aln-chatbot-rag.onrender.com/api"

# All PDFs in the project
PDFS = [
    {"path": "Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf", "title": "Assessment Brief CMP6230"},
    {"path": "General_Document.pdf", "title": "General Document"},
    {"path": "Donor_Proposal.pdf", "title": "Donor Proposal"},
    {"path": "Meeting_Notes.pdf", "title": "Meeting Notes"},
    {"path": "Internal_Policy.pdf", "title": "Internal Policy"},
    {"path": "Integrity_Icon.pdf", "title": "Integrity Icon"},
    {"path": "Governance_Weekly.pdf", "title": "Governance Weekly"},
]

print("=" * 80)
print("📚 COMPREHENSIVE PDF UPLOAD MANAGER FOR RENDER")
print("=" * 80)

# Step 1: Clean up duplicates
print("\n🧹 Step 1: Cleaning up duplicate documents...")
try:
    r = requests.delete(f"{BASE_URL}/ingest/cleanup-duplicates", timeout=30)
    if r.status_code == 200:
        result = r.json()
        deleted = result.get('total_deleted', 0)
        print(f"   ✅ Deleted {deleted} duplicate documents")
    else:
        print(f"   ⚠️  Cleanup returned {r.status_code}")
except Exception as e:
    print(f"   ⚠️  Cleanup error: {e}")

# Step 2: List remaining documents
print("\n📋 Step 2: Checking remaining documents...")
try:
    r = requests.get(f"{BASE_URL}/chat/documents", timeout=10)
    if r.status_code == 200:
        docs = r.json()
        print(f"   Current documents: {len(docs)}")
        for doc in docs:
            print(f"      - ID {doc['id']}: {doc['title']}")
except Exception as e:
    print(f"   Error: {e}")

# Step 3: Upload all PDFs
print("\n📤 Step 3: Uploading all PDFs...\n")

uploaded_count = 0
failed_count = 0

for idx, pdf_info in enumerate(PDFS, 1):
    pdf_path = Path(pdf_info["path"])
    
    if not pdf_path.exists():
        print(f"   ❌ [{idx}/{len(PDFS)}] {pdf_path.name} - FILE NOT FOUND")
        failed_count += 1
        continue
    
    print(f"   📄 [{idx}/{len(PDFS)}] Uploading {pdf_path.name}...")
    
    try:
        with open(pdf_path, "rb") as f:
            files = {"file": (pdf_path.name, f, "application/pdf")}
            data = {
                "title": pdf_info["title"],
                "document_type": "general",
                "year": "2024",
                "chunk_strategy": "sentence"
            }
            
            start = time.time()
            r = requests.post(
                f"{BASE_URL}/ingest/upload",
                files=files,
                data=data,
                timeout=15
            )
            elapsed = time.time() - start
            
            if r.status_code == 200:
                result = r.json()
                doc_id = result.get('document_id')
                print(f"      ✅ Success in {elapsed:.1f}s (ID: {doc_id})")
                uploaded_count += 1
            else:
                print(f"      ❌ Failed: {r.status_code}")
                failed_count += 1
                
    except Exception as e:
        print(f"      ❌ Error: {e}")
        failed_count += 1
    
    # Small delay between uploads
    if idx < len(PDFS):
        time.sleep(1)

# Step 4: Summary
print("\n" + "=" * 80)
print("📊 UPLOAD SUMMARY")
print("=" * 80)
print(f"✅ Uploaded: {uploaded_count}/{len(PDFS)}")
print(f"❌ Failed: {failed_count}/{len(PDFS)}")

if uploaded_count > 0:
    print(f"\n⏳ Documents are processing in background...")
    print(f"   Processing time: ~1-2 minutes per PDF")
    print(f"   You can start querying immediately, though embedding may still be completing")
    
    # Step 5: Wait and test query
    print(f"\n🧪 Step 4: Waiting 30s then testing query...")
    time.sleep(30)
    
    try:
        r = requests.post(
            f"{BASE_URL}/chat/query",
            json={
                "query": "List all the documents you have access to",
                "mode": "general",
                "session_id": "test_session"
            },
            timeout=30
        )
        
        if r.status_code == 200:
            result = r.json()
            answer = result.get('answer', 'No response')
            print(f"   ✅ Query working!")
            print(f"      Response: {answer[:200]}...")
        else:
            print(f"   ⚠️  Query returned {r.status_code}")
    except Exception as e:
        print(f"   ⚠️  Query error: {e}")

print("\n" + "=" * 80)
print("📚 NEXT STEPS:")
print("=" * 80)
print("1. Wait 2-3 minutes for all embeddings to complete")
print("2. Test document mode: 'I want to ask about [PDF name]'")
print("3. Monitor Render logs for background processing:")
print("   https://dashboard.render.com → aln-chatbot-rag → Logs")
print("=" * 80)
