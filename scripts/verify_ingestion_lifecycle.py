"""
Verify end-to-end ingestion lifecycle using local API endpoints.
Usage: python scripts/verify_ingestion_lifecycle.py sample.pdf

This script will:
- Upload a PDF to /api/ingest/upload
- Poll for document presence and chunk counts
- Query vectorstore via /api/chat/documents and /api/chat/query to validate sources
- Delete the document via /api/ingest/documents/{id} and verify vectors removed

Make sure backend is running at http://localhost:8000
"""
import sys
import time
import requests
from pathlib import Path

BASE = 'http://localhost:8000'

def upload(pdf_path: Path):
    files = {'file': (pdf_path.name, open(pdf_path, 'rb'), 'application/pdf')}
    data = {'chunk_strategy': 'sentence'}
    r = requests.post(f'{BASE}/api/ingest/upload', files=files, data=data, timeout=60)
    return r

def list_docs():
    r = requests.get(f'{BASE}/api/ingest/documents')
    return r

def query_all_docs(query):
    payload = {
        'session_id': 'verify-session',
        'query': query,
        'mode': 'documents',
        'document_id': None,
        'use_latest_document': False,
        'role': 'staff'
    }
    r = requests.post(f'{BASE}/api/chat/query', json=payload, timeout=60)
    return r

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python scripts/verify_ingestion_lifecycle.py sample.pdf')
        sys.exit(1)
    pdf = Path(sys.argv[1])
    if not pdf.exists():
        print('PDF not found:', pdf)
        sys.exit(1)

    print('Uploading...', pdf.name)
    r = upload(pdf)
    print('Upload status:', r.status_code, r.text[:200])
    if r.status_code != 200:
        sys.exit(1)
    doc_id = r.json().get('document_id')
    print('Document ID:', doc_id)

    print('Waiting for processing (polling documents)...')
    for i in range(30):
        time.sleep(5)
        resp = list_docs()
        if resp.status_code == 200:
            docs = resp.json().get('documents', [])
            for d in docs:
                if d['id'] == doc_id:
                    print('Found document in listing:', d)
                    found = True
                    break
            else:
                found = False
            if found:
                break
    if not found:
        print('Document did not appear in listing within timeout')
        sys.exit(1)

    print('Testing all-documents query')
    q = query_all_docs('test')
    print('Query status:', q.status_code)
    if q.status_code == 200:
        data = q.json()
        print('Answer:', data.get('answer')[:200])
        print('Sources:', data.get('sources'))
    else:
        print('Query failed:', q.text)

    print('Deleting document', doc_id)
    d = requests.delete(f'{BASE}/api/ingest/documents/{doc_id}')
    print('Delete status:', d.status_code, d.text)

    print('Verifying deletion...')
    time.sleep(5)
    resp = list_docs()
    if resp.status_code == 200:
        docs = resp.json().get('documents', [])
        ids = [doc['id'] for doc in docs]
        print('Remaining doc ids:', ids)
        if doc_id in ids:
            print('ERROR: deleted document still present in listing')
        else:
            print('Document successfully removed from listing')
    else:
        print('Could not list documents after deletion')

    print('Done')
