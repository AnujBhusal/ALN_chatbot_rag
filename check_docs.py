#!/usr/bin/env python3
import os
from app.db.session import SessionLocal
from app.db import models

db = SessionLocal()
try:
    docs = db.query(models.Document).all()
    print(f'Documents in database: {len(docs)}')
    for doc in docs:
        print(f'  ID {doc.id}: {doc.filename} ({doc.title})')
        chunks = db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == doc.id).count()
        print(f'         Chunks: {chunks}')
finally:
    db.close()
