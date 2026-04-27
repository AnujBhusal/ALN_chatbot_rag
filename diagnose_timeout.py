#!/usr/bin/env python3
"""Check Render logs for upload error details."""
import requests
import subprocess

print("📋 Fetching Render logs...\n")

# Get logs using Render API (requires auth token in env)
# For now, guide user to check manually
print("❌ Cannot fetch logs programmatically without Render API token")
print("\n✅ To check logs manually:")
print("   1. Go to: https://dashboard.render.com")
print("   2. Select service: 'aln-chatbot-rag'") 
print("   3. Click 'Logs' tab")
print("   4. Look for errors around the upload timestamps (65 seconds ago)")
print("\n🔍 Key things to look for:")
print("   - 'ModuleNotFoundError: No module named sentence_transformers'")
print("   - 'timeout' or 'timed out'")
print("   - Memory/CPU exhaustion")
print("   - Chunking/embedding generation errors")

print("\n💡 Meanwhile, let's test embedding generation locally with a smaller test...")

try:
    from app.services.embeddings import EmbeddingService
    from app.services.chunking import ChunkingService
    import time
    
    chunker = ChunkingService()
    embedder = EmbeddingService()
    
    # Create sample chunks
    test_text = "This is a test document. " * 100  # ~2.5KB
    
    print(f"\n📝 Test text: {len(test_text)} chars")
    chunks = chunker.sentence_chunk(test_text)
    print(f"📊 Chunks created: {len(chunks)}")
    
    # Time embedding
    start = time.time()
    embeddings = embedder.embed_texts(chunks)
    elapsed = time.time() - start
    
    print(f"⏱️  Embedding time: {elapsed:.2f}s for {len(chunks)} chunks")
    print(f"   Rate: {len(chunks)/elapsed:.1f} chunks/sec")
    
    # Estimate for full PDF
    # Assume 5KB average per chunk = ~112 chunks from 562KB PDF
    est_time = (112 / (len(chunks)/elapsed))
    print(f"\n📈 Estimated for full PDF (~112 chunks): {est_time:.1f}s")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
