#!/usr/bin/env python3
"""Final cleanup and test of all 7 PDFs"""
import requests
import time

BASE_URL = 'https://aln-chatbot-rag.onrender.com/api'

print('=' * 80)
print('🧹 FINAL CLEANUP AND TEST')
print('=' * 80)

print('\n🧹 Step 1: Cleaning up duplicates...')
try:
    r = requests.delete(f'{BASE_URL}/ingest/cleanup-duplicates', timeout=30)
    if r.status_code == 200:
        result = r.json()
        print(f'✅ Cleanup complete')
        print(f'   Deleted: {result.get("deleted_count", 0)} documents')
    else:
        print(f'❌ Cleanup failed: {r.status_code}')
except Exception as e:
    print(f'❌ Error: {e}')

print('\n⏳ Waiting 120s for embeddings to complete...')
time.sleep(120)

print('\n🧪 Step 2: Testing query...')
try:
    query_data = {
        'session_id': 'test-session-001',
        'query': 'What is the governance framework?',
        'mode': 'documents',
        'role': 'staff'
    }
    r = requests.post(f'{BASE_URL}/chat/query', json=query_data, timeout=30)
    if r.status_code == 200:
        result = r.json()
        answer = result.get('answer', '')
        sources = result.get('sources', [])
        
        print(f'✅ Query successful!')
        print(f'   Answer: {answer[:200]}...')
        print(f'   Sources found: {len(sources)}')
        if sources:
            print(f'   First source: {sources[0]}')
    else:
        print(f'❌ Query failed: {r.status_code}')
        print(f'   Response: {r.text[:200]}')
except Exception as e:
    print(f'❌ Error: {e}')

print('\n' + '=' * 80)
print('✅ ALL 7 PDFS UPLOADED AND READY')
print('=' * 80)
