#!/usr/bin/env python3
"""Test full PDF ingestion pipeline locally."""
import sys
import time
from pathlib import Path

# Ensure we can import from app
sys.path.insert(0, str(Path.cwd()))

from app.api.ingest import extract_text_from_file, normalize_extracted_text
from app.services.chunking import ChunkingService
from app.services.embeddings import EmbeddingService

print("🔬 TESTING FULL PDF INGEST PIPELINE\n")

pdf_path = Path("Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf")

if not pdf_path.exists():
    print(f"❌ PDF not found: {pdf_path}")
    exit(1)

try:
    # Step 1: Extract
    print("Step 1: Extracting text...")
    start = time.time()
    
    class FakeUploadFile:
        def __init__(self, path):
            self.file = open(path, 'rb')
            self.filename = path.name
            self.content_type = 'application/pdf'
        def read(self):
            return self.file.read()
        def seek(self, pos):
            self.file.seek(pos)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.file.close()
    
    fake_file = FakeUploadFile(pdf_path)
    raw_text = extract_text_from_file(fake_file)
    fake_file.__exit__(None, None, None)
    
    extract_time = time.time() - start
    print(f"   ✅ Extracted {len(raw_text):,} chars in {extract_time:.2f}s")
    
    # Step 2: Normalize
    print("Step 2: Normalizing text...")
    start = time.time()
    text = normalize_extracted_text(raw_text)
    normalize_time = time.time() - start
    print(f"   ✅ Normalized to {len(text):,} chars in {normalize_time:.2f}s")
    
    # Step 3: Chunk
    print("Step 3: Chunking...")
    start = time.time()
    chunker = ChunkingService()
    chunks = chunker.sentence_chunk(text)
    chunk_time = time.time() - start
    print(f"   ✅ Created {len(chunks)} chunks in {chunk_time:.2f}s")
    print(f"   📊 Avg chunk size: {len(text)/len(chunks):.0f} chars")
    
    # Step 4: Embed
    print("Step 4: Embedding chunks...")
    start = time.time()
    embedder = EmbeddingService()
    embeddings = embedder.embed_texts(chunks)
    embed_time = time.time() - start
    print(f"   ✅ Generated {len(embeddings)} embeddings in {embed_time:.2f}s")
    print(f"   📊 Embedding rate: {len(embeddings)/embed_time:.1f} chunks/sec")
    print(f"   📏 Dimension: {len(embeddings[0])}")
    
    # Total time
    total_time = extract_time + normalize_time + chunk_time + embed_time
    print(f"\n⏱️  TOTAL TIME: {total_time:.2f}s")
    print(f"   Extract: {extract_time:.2f}s")
    print(f"   Normalize: {normalize_time:.2f}s")
    print(f"   Chunk: {chunk_time:.2f}s")
    print(f"   Embed: {embed_time:.2f}s")
    
    if total_time > 30:
        print(f"\n⚠️  WARNING: {total_time:.2f}s exceeds typical HTTP timeout (30s)")
        print(f"   This will fail on Render unless request timeout is increased")
    else:
        print(f"\n✅ Total time is reasonable for HTTP request")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
