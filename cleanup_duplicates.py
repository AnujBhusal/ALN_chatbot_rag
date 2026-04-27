#!/usr/bin/env python3
"""
Remove duplicate documents from the database.
Keeps the latest one, removes older duplicates.
"""

import sys
import os
sys.path.insert(0, '/c/Users/Anuj Bhusal/Desktop/Rag-Backend')

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.db import models
from collections import defaultdict

print(f"🔗 Connecting to database...")
db = SessionLocal()

try:
    # Get all documents
    documents = db.query(models.Document).order_by(models.Document.uploaded_at).all()
    
    print(f"\n📋 Found {len(documents)} total documents\n")
    
    # Group by title to find duplicates
    by_title = defaultdict(list)
    for doc in documents:
        by_title[doc.title].append(doc)
    
    duplicates_found = False
    total_deleted = 0
    
    for title, docs in by_title.items():
        if len(docs) > 1:
            duplicates_found = True
            print(f"🔍 Found {len(docs)} copies of: '{title}'")
            
            # Keep latest, delete others
            latest = max(docs, key=lambda d: d.uploaded_at)
            print(f"   ✅ Keeping ID {latest.id} (uploaded: {latest.uploaded_at})")
            
            for old_doc in docs:
                if old_doc.id != latest.id:
                    print(f"   ❌ Deleting ID {old_doc.id} (uploaded: {old_doc.uploaded_at})")
                    
                    # Delete associated chunks first
                    chunk_count = db.query(models.DocumentChunk).filter(
                        models.DocumentChunk.document_id == old_doc.id
                    ).delete()
                    print(f"      └─ Deleted {chunk_count} chunks")
                    
                    # Delete document
                    db.delete(old_doc)
                    total_deleted += 1
            
            print()
    
    if duplicates_found:
        db.commit()
        print(f"✅ Cleanup complete! Deleted {total_deleted} duplicate documents\n")
    else:
        print("✅ No duplicates found!\n")
    
    # Show remaining documents
    remaining = db.query(models.Document).all()
    print(f"📊 Documents after cleanup: {len(remaining)}")
    for doc in remaining:
        chunk_count = db.query(models.DocumentChunk).filter(
            models.DocumentChunk.document_id == doc.id
        ).count()
        print(f"   - ID {doc.id}: {doc.title} ({chunk_count} chunks)")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
