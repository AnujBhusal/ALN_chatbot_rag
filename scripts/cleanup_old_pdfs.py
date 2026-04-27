#!/usr/bin/env python3
"""
Cleanup old duplicate PDFs from Render backend.
Removes documents with IDs before 39 (old duplicates).
Keeps only the latest versions (IDs 39+).
"""

import requests
import os
import time

RENDER_API_URL = os.getenv("RENDER_BACKEND_URL", "https://aln-chatbot-rag.onrender.com/api")

def delete_old_documents():
    """Delete documents with IDs before 39 (old duplicates)."""
    
    print("=" * 80)
    print("🗑️  CLEANUP OLD DUPLICATE PDFS")
    print("=" * 80)
    
    # Get list of documents
    print("\n📋 Fetching list of documents...")
    try:
        response = requests.get(f"{RENDER_API_URL}/ingest/documents", timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to fetch documents: {response.status_code}")
            return
        
        result = response.json()
        documents = result.get("documents", [])
        
        # Find old documents (IDs before 39)
        old_docs = [doc for doc in documents if doc["id"] < 39]
        
        if not old_docs:
            print("✅ No old documents to delete (all IDs >= 39)")
            return
        
        print(f"\n🗑️  Found {len(old_docs)} old documents to delete:")
        for doc in sorted(old_docs, key=lambda x: x["id"]):
            print(f"   ID {doc['id']}: {doc['title']} ({doc['chunks']} chunks)")
        
        # Confirm deletion
        confirm = input(f"\n⚠️  Delete these {len(old_docs)} documents? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("❌ Cancelled - no documents deleted")
            return
        
        # Delete each old document
        print(f"\n🗑️  Deleting {len(old_docs)} old documents...")
        successful = 0
        failed = 0
        
        for doc in sorted(old_docs, key=lambda x: x["id"]):
            doc_id = doc["id"]
            title = doc["title"]
            
            try:
                response = requests.delete(
                    f"{RENDER_API_URL}/ingest/documents/{doc_id}",
                    timeout=15
                )
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"   ✅ Deleted ID {doc_id}: {title} ({result['chunks_deleted']} chunks)")
                    successful += 1
                else:
                    print(f"   ❌ Failed to delete ID {doc_id}: {response.status_code}")
                    failed += 1
                
                # Wait between deletions
                time.sleep(1)
            
            except Exception as e:
                print(f"   ❌ Error deleting ID {doc_id}: {str(e)[:50]}")
                failed += 1
        
        print("\n" + "=" * 80)
        print("✅ CLEANUP COMPLETE")
        print("=" * 80)
        print(f"Successfully deleted: {successful}/{len(old_docs)}")
        if failed > 0:
            print(f"Failed: {failed}/{len(old_docs)}")
        print("=" * 80)
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    delete_old_documents()
