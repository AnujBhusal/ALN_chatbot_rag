"""
Add `file_checksum` column if missing and backfill checksums for existing documents.
Run: python scripts/add_file_checksum.py
"""
import os
import hashlib
from app.db.session import SessionLocal
from app.db import models
from pathlib import Path

DB = SessionLocal()

def compute_sha256_from_path(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, 'rb') as fh:
            for chunk in iter(lambda: fh.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

if __name__ == '__main__':
    print('Starting checksum migration/backfill...')
    # Add column if not exists (sqlite/postgres compatible simple check)
    try:
        DB.execute("ALTER TABLE documents ADD COLUMN file_checksum VARCHAR")
        DB.commit()
        print('Added file_checksum column')
    except Exception as e:
        print('Could not add column (may already exist):', e)

    docs = DB.query(models.Document).all()
    print(f'Found {len(docs)} documents to inspect')
    updated = 0
    for doc in docs:
        if getattr(doc, 'file_checksum', None):
            continue
        # Try to find file path on disk
        candidates = []
        # If filename exists in data/pdfs
        local_path = Path('data') / 'pdfs' / doc.filename if getattr(doc, 'filename', None) else None
        if local_path and local_path.exists():
            candidates.append(local_path)
        # If file_path field exists historically
        if hasattr(doc, 'file_path') and getattr(doc, 'file_path'):
            p = Path(getattr(doc, 'file_path'))
            if p.exists():
                candidates.append(p)
        checksum = None
        for c in candidates:
            checksum = compute_sha256_from_path(c)
            if checksum:
                break
        if checksum:
            doc.file_checksum = checksum
            DB.add(doc)
            DB.commit()
            updated += 1
            print(f'Backfilled checksum for doc {doc.id}: {checksum[:8]}...')
        else:
            print(f'Could not find file for doc {doc.id} to compute checksum')

    print(f'Backfill complete. Updated: {updated}')
    DB.close()
