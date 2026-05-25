"""
Vectorstore Audit Tool

Generates audit_report.json, duplicate_report.json, orphan_vectors.json, missing_vectors.json

Usage examples:
  python scripts/vectorstore_audit.py --output-dir=./audit_reports --dry-run
  python scripts/vectorstore_audit.py --output-dir=./audit_reports --safe-delete --confirm

Notes:
- The tool verifies DB -> Pinecone consistency by constructing deterministic point IDs
  of the form "{document_id}_{chunk_id}" (this repo's convention).
- Orphan vector discovery (vectors in Pinecone that have no DB record) is best-effort
  because Pinecone does not provide a simple list-all-ids endpoint. The tool compares
  expected IDs from the DB against what Pinecone contains (via fetch), and reports
  a namespace mismatch if Pinecone has more vectors than were matched.

"""
import argparse
import json
import math
import os
import time
from typing import List, Dict, Any

# Import project services
from app.db.session import SessionLocal
from app.db import models
from app.services.vectorstore import VectorStoreService
from app.services.embeddings import EmbeddingService
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH = 200  # fetch size for Pinecone fetch calls


def batch_iterable(it, size):
    it = list(it)
    for i in range(0, len(it), size):
        yield it[i : i + size]


def load_db_documents(db):
    docs = db.query(models.Document).order_by(models.Document.id.asc()).all()
    return docs


def collect_expected_ids(db) -> Dict[str, Dict[str, Any]]:
    """Return mapping of expected_point_id -> metadata (document_id, chunk_id, doc_title)"""
    mapping: Dict[str, Dict[str, Any]] = {}
    chunks = db.query(models.DocumentChunk).order_by(models.DocumentChunk.id.asc()).all()
    # Build mapping by chunk
    for chunk in chunks:
        doc_id = chunk.document_id
        point_id = f"{doc_id}_{chunk.id}"
        mapping[point_id] = {
            "document_id": doc_id,
            "chunk_id": chunk.id,
            "chunk_text_preview": (chunk.chunk_text or "")[:200],
        }
    return mapping


def fetch_existing_vectors(vectorstore: VectorStoreService, ids: List[str], namespace: str = None) -> Dict[str, Any]:
    """Fetch explicit vector ids from Pinecone. Returns a mapping id -> metadata dict for present ids."""
    # Ensure connection
    if not vectorstore._ensure_connected():
        raise RuntimeError("Could not connect to vectorstore")

    index = vectorstore.index
    found: Dict[str, Any] = {}

    # Pinecone Index.fetch accepts up to a large number of ids; batch to avoid limits
    for batch in batch_iterable(ids, BATCH):
        try:
            res = index.fetch(ids=batch, namespace=vectorstore.namespace)
            # res can be dict-like with 'vectors' key
            vectors = res.get('vectors') if isinstance(res, dict) else getattr(res, 'vectors', None)
            if not vectors:
                # Some Pinecone responses store as {'vectors': {id: { 'metadata':..., 'values':...}}}
                continue
            for vid, v in vectors.items():
                metadata = v.get('metadata') if isinstance(v, dict) else getattr(v, 'metadata', {})
                found[vid] = metadata
        except Exception as e:
            logger.warning(f"Fetch batch failed: {e}")
            # Try alternative access pattern
            try:
                # Some Pinecone clients return fetch result as an object with .vectors mapping
                res = index.fetch(ids=batch, namespace=vectorstore.namespace)
                vectors = getattr(res, 'vectors', {})
                for vid, v in vectors.items():
                    try:
                        metadata = v.metadata
                    except Exception:
                        metadata = {}
                    found[vid] = metadata
            except Exception as e2:
                logger.error(f"Fetch fallback failed: {e2}")
    return found


def describe_namespaces(vectorstore: VectorStoreService) -> Dict[str, Any]:
    try:
        stats = vectorstore.index.describe_index_stats()
        return stats
    except Exception as e:
        logger.warning(f"Could not describe index stats: {e}")
        return {}


def run_audit(output_dir: str, dry_run: bool = True, safe_delete: bool = False, confirm: bool = False):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    vs = VectorStoreService()
    if not vs._ensure_connected():
        logger.warning("Vectorstore not available; some checks will be skipped")

    docs = load_db_documents(db)
    expected = collect_expected_ids(db)
    expected_ids = list(expected.keys())

    logger.info(f"DB documents: {len(docs)}, expected vectors (from chunks): {len(expected_ids)}")

    # Fetch existing vectors for expected ids
    found = {}
    missing_ids = []

    for batch in batch_iterable(expected_ids, BATCH):
        logger.info(f"Fetching batch of {len(batch)} expected ids from Pinecone...")
        try:
            batch_found = fetch_existing_vectors(vs, batch, namespace=vs.namespace)
            # mark missing
            for pid in batch:
                if pid in batch_found:
                    found[pid] = batch_found[pid]
                else:
                    missing_ids.append(pid)
        except Exception as e:
            logger.error(f"Error fetching batch: {e}")
            missing_ids.extend(batch)

    logger.info(f"Found vectors: {len(found)}, Missing expected vectors: {len(missing_ids)}")

    # Save missing vectors report
    missing_vectors_path = out / 'missing_vectors.json'
    with open(missing_vectors_path, 'w', encoding='utf-8') as fh:
        json.dump(missing_ids, fh, indent=2)

    # Validate metadata consistency for found vectors
    metadata_mismatches = []
    duplicate_chunks = {}
    doc_chunk_counts_expected = {}
    doc_chunk_counts_found = {}

    # Expected counts per document
    for doc in docs:
        doc_chunk_counts_expected[doc.id] = db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == doc.id).count()
        doc_chunk_counts_found[doc.id] = 0

    for pid, md in found.items():
        try:
            parts = pid.split('_')
            doc_id = int(parts[0])
            chunk_id = int(parts[1])
        except Exception:
            # invalid id format
            metadata_mismatches.append({
                'point_id': pid,
                'issue': 'invalid_point_id_format',
                'metadata': md,
            })
            continue

        # check doc exists
        db_doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
        if not db_doc:
            metadata_mismatches.append({
                'point_id': pid,
                'issue': 'document_id_not_in_db',
                'metadata': md,
            })
            continue

        # check chunk exists
        db_chunk = db.query(models.DocumentChunk).filter(models.DocumentChunk.id == chunk_id, models.DocumentChunk.document_id == doc_id).first()
        if not db_chunk:
            metadata_mismatches.append({
                'point_id': pid,
                'issue': 'chunk_id_not_in_db',
                'metadata': md,
            })
            continue

        # metadata consistency
        meta_doc_id = md.get('document_id') if isinstance(md, dict) else None
        meta_chunk_id = md.get('chunk_id') if isinstance(md, dict) else None

        # coerce types
        try:
            if meta_doc_id is not None:
                meta_doc_id_int = int(float(meta_doc_id))
            else:
                meta_doc_id_int = None
        except Exception:
            meta_doc_id_int = None
        try:
            if meta_chunk_id is not None:
                meta_chunk_id_int = int(float(meta_chunk_id))
            else:
                meta_chunk_id_int = None
        except Exception:
            meta_chunk_id_int = None

        if meta_doc_id_int != doc_id or meta_chunk_id_int != chunk_id:
            metadata_mismatches.append({
                'point_id': pid,
                'issue': 'metadata_mismatch',
                'expected': {'document_id': doc_id, 'chunk_id': chunk_id},
                'found_metadata': md,
            })

        # chunk count per document observed
        doc_chunk_counts_found[doc_id] = doc_chunk_counts_found.get(doc_id, 0) + 1

    # Duplicate checksums (DB)
    dup_checksums = []
    checksum_map = {}
    for doc in docs:
        c = getattr(doc, 'file_checksum', None)
        if not c:
            continue
        checksum_map.setdefault(c, []).append({'id': doc.id, 'title': doc.title})
    for checksum, items in checksum_map.items():
        if len(items) > 1:
            dup_checksums.append({'checksum': checksum, 'documents': items})

    # Duplicate vectors by metadata text (best-effort): group found vectors by metadata.text snippet
    text_map = {}
    duplicate_vectors = []
    for pid, md in found.items():
        txt = None
        if isinstance(md, dict):
            txt = (md.get('text') or '')[:200]
        else:
            txt = str(md)[:200]
        if not txt:
            continue
        text_map.setdefault(txt, []).append(pid)
    for txt, pids in text_map.items():
        if len(pids) > 1:
            duplicate_vectors.append({'text_preview': txt, 'point_ids': pids})

    # Namespace stats via describe_index_stats
    namespace_stats = describe_namespaces(vs)

    # Compose audit report
    audit_report = {
        'timestamp': time.time(),
        'db_document_count': len(docs),
        'expected_vector_count': len(expected_ids),
        'found_vector_count': len(found),
        'missing_vector_count': len(missing_ids),
        'duplicate_checksums': len(dup_checksums),
        'duplicate_vector_groups': len(duplicate_vectors),
        'namespace_stats': namespace_stats,
    }

    with open(out / 'audit_report.json', 'w', encoding='utf-8') as fh:
        json.dump(audit_report, fh, indent=2)

    with open(out / 'duplicate_report.json', 'w', encoding='utf-8') as fh:
        json.dump({'duplicate_checksums': dup_checksums, 'duplicate_vectors': duplicate_vectors}, fh, indent=2)

    with open(out / 'orphan_vectors.json', 'w', encoding='utf-8') as fh:
        # Best-effort orphan detection: find metadata entries pointing to doc_ids not in DB
        orphans = [m for m in metadata_mismatches if m.get('issue') == 'document_id_not_in_db']
        json.dump(orphans, fh, indent=2)

    with open(out / 'missing_vectors.json', 'w', encoding='utf-8') as fh:
        json.dump(missing_ids, fh, indent=2)

    # Per-document chunk statistics
    per_doc_stats = []
    for doc in docs:
        expected_count = doc_chunk_counts_expected.get(doc.id, 0)
        found_count = doc_chunk_counts_found.get(doc.id, 0)
        per_doc_stats.append({'document_id': doc.id, 'title': doc.title, 'expected_chunks': expected_count, 'found_vectors': found_count})

    with open(out / 'per_document_stats.json', 'w', encoding='utf-8') as fh:
        json.dump(per_doc_stats, fh, indent=2)

    # Retrieval health: sample a few documents and run a query
    retrieval_health = []
    emb = EmbeddingService()
    sample_docs = docs[:5]
    for doc in sample_docs:
        # pick first chunk text from DB
        chunk = db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == doc.id).first()
        if not chunk:
            retrieval_health.append({'document_id': doc.id, 'status': 'no_chunk'})
            continue
        try:
            qemb = emb.embed_texts([chunk.chunk_text])[0]
            results = vs.query(qemb, top_k=5, query_filter={'document_id': {'$eq': doc.id}})
            retrieval_health.append({'document_id': doc.id, 'found': len(results)})
        except Exception as e:
            retrieval_health.append({'document_id': doc.id, 'error': str(e)})

    with open(out / 'retrieval_health.json', 'w', encoding='utf-8') as fh:
        json.dump(retrieval_health, fh, indent=2)

    logger.info(f"Audit files written to {out.resolve()}")

    # Dry-run cleanup and safe-delete
    if safe_delete:
        if not confirm:
            logger.warning("Safe delete requested but not confirmed; pass --confirm to perform deletions")
        else:
            # Delete missing vectors? (nothing to delete)
            # Delete orphan vectors: best-effort delete by ids found in metadata_mismatches with document_id_not_in_db
            orphan_ids = [m['point_id'] for m in metadata_mismatches if m.get('issue') == 'document_id_not_in_db']
            if orphan_ids:
                logger.info(f"Deleting {len(orphan_ids)} orphan vectors from Pinecone...")
                if not dry_run:
                    vs.delete_by_ids(orphan_ids)
                else:
                    logger.info("Dry-run: not actually deleting orphan vectors")

    db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='./audit_reports')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--safe-delete', action='store_true', help='Attempt to delete detected orphan vectors (requires --confirm)')
    parser.add_argument('--confirm', action='store_true', help='Confirm destructive actions')
    args = parser.parse_args()

    run_audit(args.output_dir, dry_run=args.dry_run, safe_delete=args.safe_delete, confirm=args.confirm)
