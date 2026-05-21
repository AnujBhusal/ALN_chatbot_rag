# PDF Ingestion Duplication Fix Guide

## Problem Summary

Your deployed chatbot shows 7x duplication: **3 PDFs → 21+ documents**

### Root Cause
When documents are deleted from the database, their vector embeddings remain in Pinecone. This creates orphaned data that continues to be retrieved in queries, causing duplicate results across multiple "versions" of the same document.

### Critical Code Issues

1. **`delete_document` endpoint** - Deletes from PostgreSQL but NOT Pinecone
2. **`cleanup_duplicates` endpoint** - Removes duplicates from PostgreSQL but NOT Pinecone  
3. **No state synchronization** - PostgreSQL and Pinecone get out of sync over time

---

## 🔴 Issue #1: Delete Endpoint Missing Pinecone Cleanup

### Location
`app/api/ingest.py` - Lines 502-545

### Current Code
```python
@router.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    """
    Delete a specific document and its chunks.
    Used by cleanup script to remove old duplicates.
    """
    try:
        document = db.query(models.Document).filter(models.Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
        
        logger.info(f"🗑️  Deleting document {document_id}: {document.title}")
        
        # Delete chunks first
        chunks = db.query(models.DocumentChunk).filter(
            models.DocumentChunk.document_id == document_id
        ).all()
        
        chunk_count = len(chunks)
        for chunk in chunks:
            db.delete(chunk)
        
        # Delete document
        db.delete(document)
        db.commit()
        
        # ❌ MISSING: vectorstore.delete_by_document_id(document_id)
        
        logger.info(f"✅ Deleted document {document_id} ({chunk_count} chunks removed)")
        
        return {
            "message": f"Document {document_id} deleted",
            "document_id": document_id,
            "title": document.title,
            "chunks_deleted": chunk_count
        }
```

### Problem
Orphaned vectors remain in Pinecone for retrieval to find

### Solution

Replace the function with:

```python
@router.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    """
    Delete a specific document and its chunks from BOTH database and Pinecone.
    Used by cleanup script to remove old duplicates.
    """
    try:
        document = db.query(models.Document).filter(models.Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
        
        logger.info(f"🗑️  Deleting document {document_id}: {document.title}")
        
        # Step 1: Delete chunks from database
        chunks = db.query(models.DocumentChunk).filter(
            models.DocumentChunk.document_id == document_id
        ).all()
        
        chunk_count = len(chunks)
        for chunk in chunks:
            db.delete(chunk)
        
        # Step 2: Delete document from database
        db.delete(document)
        db.commit()
        logger.info(f"   ✅ Database cleanup: Deleted {chunk_count} chunks")
        
        # Step 3: Delete vectors from Pinecone 🔥 NEW
        logger.info(f"   📤 Deleting vectors from Pinecone...")
        vectorstore.delete_by_document_id(document_id)
        logger.info(f"   ✅ Pinecone cleanup: Deleted all vectors for document {document_id}")
        
        return {
            "message": f"Document {document_id} deleted from both database and Pinecone",
            "document_id": document_id,
            "title": document.title,
            "chunks_deleted": chunk_count,
            "pinecone_cleaned": True
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"   ❌ Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 🔴 Issue #2: Cleanup Duplicates Missing Pinecone Cleanup

### Location
`app/api/ingest.py` - Lines 420-467

### Current Code
```python
@router.delete("/cleanup-duplicates")
async def cleanup_duplicates(db: Session = Depends(get_db)) -> dict:
    """
    Remove duplicate documents, keeping only the latest one.
    Admin endpoint for database maintenance.
    """
    from collections import defaultdict
    
    # Get all documents ordered by upload time
    documents = db.query(models.Document).order_by(models.Document.uploaded_at).all()
    logger.info(f"🔍 Found {len(documents)} total documents")
    
    # Group by title
    by_title = defaultdict(list)
    for doc in documents:
        by_title[doc.title].append(doc)
    
    # Find and delete duplicates
    deleted_doc_ids = []
    deleted_chunk_count = 0
    
    for title, docs in by_title.items():
        if len(docs) > 1:
            logger.info(f"   ⚠️  Found {len(docs)} duplicates for '{title}'")
            # Keep the latest, delete older ones
            for old_doc in docs[:-1]:
                logger.info(f"      Deleting ID {old_doc.id}")
                deleted_doc_ids.append(old_doc.id)
                # Delete chunks first
                chunks = db.query(models.DocumentChunk).filter(
                    models.DocumentChunk.document_id == old_doc.id
                ).all()
                deleted_chunk_count += len(chunks)
                for chunk in chunks:
                    db.delete(chunk)
                db.delete(old_doc)
    
    db.commit()
    logger.info(f"✅ Cleanup complete: Deleted {len(deleted_doc_ids)} documents, {deleted_chunk_count} chunks")
    
    return {
        "message": "Duplicate cleanup complete",
        "deleted_documents": deleted_doc_ids,
        "total_deleted": len(deleted_doc_ids),
        "total_chunks_deleted": deleted_chunk_count,
    }
```

### Problem
Deletes duplicates from database but leaves Pinecone vectors orphaned

### Solution

Replace with:

```python
@router.delete("/cleanup-duplicates")
async def cleanup_duplicates(db: Session = Depends(get_db)) -> dict:
    """
    Remove duplicate documents from BOTH database and Pinecone, keeping only the latest one.
    Admin endpoint for database maintenance.
    
    Process:
    1. Find documents with same title
    2. Keep the latest (by upload time)
    3. Delete older ones from both database AND Pinecone
    """
    from collections import defaultdict
    
    # Get all documents ordered by upload time
    documents = db.query(models.Document).order_by(models.Document.uploaded_at).all()
    logger.info(f"🔍 Found {len(documents)} total documents")
    
    # Group by title
    by_title = defaultdict(list)
    for doc in documents:
        by_title[doc.title].append(doc)
    
    # Find and delete duplicates
    deleted_doc_ids = []
    deleted_chunk_count = 0
    pinecone_deleted_count = 0
    
    for title, docs in by_title.items():
        if len(docs) > 1:
            logger.info(f"   ⚠️  Found {len(docs)} duplicates for '{title}'")
            # Keep the latest, delete older ones
            for old_doc in docs[:-1]:
                logger.info(f"      Deleting ID {old_doc.id}")
                deleted_doc_ids.append(old_doc.id)
                
                # Step 1: Delete chunks from database
                chunks = db.query(models.DocumentChunk).filter(
                    models.DocumentChunk.document_id == old_doc.id
                ).all()
                deleted_chunk_count += len(chunks)
                for chunk in chunks:
                    db.delete(chunk)
                db.delete(old_doc)
                
                # Step 2: Delete vectors from Pinecone 🔥 NEW
                try:
                    logger.info(f"      📤 Deleting Pinecone vectors for document {old_doc.id}...")
                    vectorstore.delete_by_document_id(old_doc.id)
                    pinecone_deleted_count += 1
                    logger.info(f"      ✅ Pinecone cleanup successful")
                except Exception as e:
                    logger.warning(f"      ⚠️  Pinecone deletion failed: {e}")
    
    db.commit()
    logger.info(f"✅ Cleanup complete:")
    logger.info(f"   - Database: Deleted {len(deleted_doc_ids)} documents, {deleted_chunk_count} chunks")
    logger.info(f"   - Pinecone: Cleaned up {pinecone_deleted_count} document vectors")
    
    return {
        "message": "Duplicate cleanup complete (database + Pinecone)",
        "deleted_documents": deleted_doc_ids,
        "total_deleted": len(deleted_doc_ids),
        "total_chunks_deleted": deleted_chunk_count,
        "pinecone_cleaned": pinecone_deleted_count,
        "pinecone_sync": pinecone_deleted_count == len(deleted_doc_ids)
    }
```

---

## 🟡 Issue #3: Add Full Pinecone Cleanup Utility

### New Endpoint

Add a new endpoint to completely rebuild Pinecone state from database (nuclear option):

```python
@router.post("/full-sync-pinecone")
async def full_sync_pinecone(db: Session = Depends(get_db)) -> dict:
    """
    FULL SYNC: Rebuild Pinecone state from database.
    
    This is a heavy operation:
    1. Delete ALL vectors in Pinecone
    2. Re-upsert all chunks from database
    3. Ensures PostgreSQL and Pinecone are in sync
    
    Use only when:
    - You suspect Pinecone has significant orphaned data
    - After major data cleanup operations
    - To reset to a known good state
    """
    import time
    
    logger.info("\n" + "=" * 80)
    logger.info("🔄 STARTING FULL PINECONE SYNC")
    logger.info("=" * 80)
    
    try:
        # Step 1: Get all documents and their chunks
        documents = db.query(models.Document).all()
        total_docs = len(documents)
        total_chunks = 0
        
        logger.info(f"📊 Found {total_docs} documents in database")
        
        if total_docs == 0:
            logger.info("⚠️  No documents to sync")
            return {
                "message": "No documents to sync",
                "documents_processed": 0,
                "chunks_upserted": 0
            }
        
        # Step 2: Delete all existing vectors from Pinecone
        logger.info(f"🗑️  Purging all vectors from Pinecone...")
        try:
            # Delete all vectors (no filter = all vectors)
            vectorstore.index.delete(delete_all=True, namespace=vectorstore.namespace)
            logger.info(f"✅ Pinecone purged successfully")
        except Exception as e:
            logger.warning(f"⚠️  Purge warning: {e}")
        
        time.sleep(1)  # Wait for Pinecone to settle
        
        # Step 3: Re-upsert all chunks
        logger.info(f"📤 Re-upserting {total_chunks} chunks from database...")
        
        upserted_count = 0
        batch_size = 50
        
        for doc_idx, document in enumerate(documents, 1):
            chunks = db.query(models.DocumentChunk).filter(
                models.DocumentChunk.document_id == document.id
            ).all()
            
            total_chunks += len(chunks)
            
            if not chunks:
                logger.warning(f"   ⚠️  Document {document.id} ({document.title}) has no chunks")
                continue
            
            # Re-generate embeddings and metadata
            chunk_texts = [chunk.chunk_text for chunk in chunks]
            
            # Batch embedding generation
            for batch_idx in range(0, len(chunk_texts), batch_size):
                batch_end = min(batch_idx + batch_size, len(chunk_texts))
                batch_texts = chunk_texts[batch_idx:batch_end]
                batch_chunks = chunks[batch_idx:batch_end]
                
                # Generate embeddings
                embeddings = embedder.embed_texts(batch_texts)
                
                # Prepare metadata
                metadatas = [
                    {
                        "document_id": document.id,
                        "chunk_id": chunk.id,
                        "text": chunk.chunk_text,
                        "title": document.title,
                        "document_type": document.document_type,
                        "year": document.year,
                        "filename": document.filename,
                        "filetype": document.filetype,
                    }
                    for chunk in batch_chunks
                ]
                
                # Upsert to Pinecone
                vectorstore.upsert_embeddings(embeddings, metadatas)
                upserted_count += len(batch_texts)
            
            logger.info(f"   [{doc_idx}/{total_docs}] ✅ {document.title}: {len(chunks)} chunks")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ FULL PINECONE SYNC COMPLETE")
        logger.info("=" * 80)
        logger.info(f"📊 Documents processed: {total_docs}")
        logger.info(f"📊 Chunks upserted: {upserted_count}")
        logger.info("=" * 80 + "\n")
        
        return {
            "message": "Full Pinecone sync completed successfully",
            "documents_processed": total_docs,
            "chunks_upserted": upserted_count,
            "sync_status": "complete"
        }
    
    except Exception as e:
        logger.error(f"❌ Full sync failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")
```

**Note:** You'll need to import embedder at the top of the ingest.py file (already done).

---

## 🟢 Issue #4: Add State Consistency Check on Startup

### Location
`app/main.py` - Add to startup_event

```python
@app.on_event("startup")
async def startup_event():
    """Auto-ingest PDFs from ./data/pdfs folder if running locally."""
    
    # ... existing folder ingestion code ...
    
    # NEW: Add Pinecone state check
    if config.LOCAL_MODE or not config.RENDER_ENVIRONMENT:
        logger.info("\n" + "=" * 80)
        logger.info("🔍 CHECKING DATABASE ↔ PINECONE CONSISTENCY")
        logger.info("=" * 80)
        
        try:
            from app.db.session import SessionLocal
            from app.db import models
            
            db = SessionLocal()
            
            # Count documents in database
            db_doc_count = db.query(models.Document).count()
            db_chunk_count = db.query(models.DocumentChunk).count()
            
            # Count vectors in Pinecone
            vectorstore_client = VectorStoreService()
            if vectorstore_client._ensure_connected():
                pinecone_stats = vectorstore_client.index.describe_index_stats()
                pinecone_vector_count = pinecone_stats.total_vector_count if hasattr(pinecone_stats, 'total_vector_count') else 0
            else:
                pinecone_vector_count = 0
            
            logger.info(f"📊 PostgreSQL State:")
            logger.info(f"   - Documents: {db_doc_count}")
            logger.info(f"   - Chunks: {db_chunk_count}")
            logger.info(f"📊 Pinecone State:")
            logger.info(f"   - Vectors: {pinecone_vector_count}")
            
            # Check for inconsistency
            if pinecone_vector_count > db_chunk_count * 1.5:  # 50% tolerance
                logger.warning("\n" + "⚠️ " * 20)
                logger.warning("⚠️  PINECONE STATE INCONSISTENCY DETECTED!")
                logger.warning(f"⚠️  Expected ~{db_chunk_count} vectors but found {pinecone_vector_count}")
                logger.warning("⚠️  This suggests orphaned vectors from deleted documents")
                logger.warning("⚠️  Run: POST /api/ingest/full-sync-pinecone")
                logger.warning("⚠️ " * 20 + "\n")
            else:
                logger.info("✅ Database ↔ Pinecone sync looks healthy")
            
            db.close()
            logger.info("=" * 80 + "\n")
        
        except Exception as e:
            logger.warning(f"Could not check Pinecone consistency: {e}")
```

---

## 🟢 Issue #5: Add Metrics & Monitoring

### New Endpoint for Diagnostics

```python
@router.get("/status/consistency")
async def check_consistency(db: Session = Depends(get_db)) -> dict:
    """
    Get current state of PostgreSQL vs Pinecone.
    Use this to monitor for duplication issues.
    """
    try:
        # Count in database
        db_docs = db.query(models.Document).count()
        db_chunks = db.query(models.DocumentChunk).count()
        
        # Count in Pinecone
        vectorstore_client = VectorStoreService()
        pinecone_vectors = 0
        
        if vectorstore_client._ensure_connected():
            try:
                stats = vectorstore_client.index.describe_index_stats()
                pinecone_vectors = stats.total_vector_count if hasattr(stats, 'total_vector_count') else 0
            except:
                pinecone_vectors = -1  # Error querying
        
        # Calculate consistency score
        consistency_score = 100
        expected_vectors = db_chunks
        
        if pinecone_vectors > 0:
            vector_ratio = pinecone_vectors / max(1, expected_vectors)
            if vector_ratio > 1.5:
                consistency_score = 50  # Major inconsistency
            elif vector_ratio > 1.1:
                consistency_score = 75  # Minor inconsistency
        
        return {
            "database": {
                "documents": db_docs,
                "chunks": db_chunks
            },
            "pinecone": {
                "vectors": pinecone_vectors,
                "expected": expected_vectors,
                "ratio": round(pinecone_vectors / max(1, expected_vectors), 2) if pinecone_vectors > 0 else None
            },
            "consistency_score": consistency_score,
            "status": "HEALTHY" if consistency_score >= 90 else "WARNING" if consistency_score >= 50 else "CRITICAL"
        }
    
    except Exception as e:
        logger.error(f"Error checking consistency: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 📋 Implementation Steps

1. **Apply Fix #1** - Update `delete_document()` in `app/api/ingest.py`
2. **Apply Fix #2** - Update `cleanup_duplicates()` in `app/api/ingest.py`
3. **Add Fix #3** - Add `full_sync_pinecone()` endpoint in `app/api/ingest.py`
4. **Add Fix #4** - Update startup event in `app/main.py`
5. **Add Fix #5** - Add `check_consistency()` endpoint in `app/api/ingest.py`

---

## 🚀 Emergency Recovery

If you need to fix duplication RIGHT NOW:

### Step 1: Run Cleanup
```bash
curl -X DELETE http://localhost:8000/api/ingest/cleanup-duplicates
```

### Step 2: Full Pinecone Sync
```bash
curl -X POST http://localhost:8000/api/ingest/full-sync-pinecone
```

### Step 3: Verify State
```bash
curl http://localhost:8000/api/ingest/status/consistency
```

### Expected Output:
```json
{
  "database": {
    "documents": 3,
    "chunks": 150
  },
  "pinecone": {
    "vectors": 150,
    "expected": 150,
    "ratio": 1.0
  },
  "consistency_score": 100,
  "status": "HEALTHY"
}
```

---

## ✅ Verification Checklist

After applying fixes:

- [ ] Delete a document via API → Check Pinecone is cleaned
- [ ] Create duplicates via API → Run cleanup-duplicates → Verify Pinecone sync
- [ ] Query for document → Only get results from current version
- [ ] Check consistency endpoint → Shows healthy state (ratio close to 1.0)
- [ ] Restart deployment → Check startup consistency report
- [ ] Test with actual PDFs → No duplicate references in results

---

## 📚 Related Files

- `app/api/ingest.py` - Upload, delete, cleanup endpoints
- `app/services/vectorstore.py` - Pinecone operations
- `app/db/models.py` - Document & DocumentChunk schemas
- `app/main.py` - Startup and initialization
- `app/services/retrieval.py` - Deduplication logic

---

## Additional Notes

- All Pinecone operations use namespace="default"
- Vector IDs follow format: `{document_id}_{chunk_id}`
- Deletion by document_id uses Pinecone filter: `{"document_id": {"$eq": document_id}}`
- Consider adding monitoring/alerts for consistency_score < 90
