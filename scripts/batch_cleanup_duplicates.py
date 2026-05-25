#!/usr/bin/env python3
"""Delete duplicate documents from the live backend in small batches.

This script keeps the newest document for each title and deletes the older
copies one by one through the existing delete endpoint. It avoids the single
long-running cleanup request that can time out on Render.
"""

from __future__ import annotations

import time
from collections import defaultdict

import requests


BASE_URL = "https://aln-chatbot-rag.onrender.com/api/ingest"
BATCH_PAUSE_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 120


def fetch_documents() -> list[dict]:
    response = requests.get(f"{BASE_URL}/documents", timeout=60)
    response.raise_for_status()
    payload = response.json()
    return payload.get("documents", [])


def group_duplicates(documents: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for document in documents:
        grouped[document["title"]].append(document)

    duplicates: list[dict] = []
    for title, docs in grouped.items():
        if len(docs) <= 1:
            continue
        ordered = sorted(docs, key=lambda item: item.get("uploaded_at") or "")
        duplicates.extend(ordered[:-1])
        print(f"Keeping newest copy of '{title}' and deleting {len(ordered) - 1} older copies")

    return sorted(duplicates, key=lambda item: item.get("uploaded_at") or "")


def delete_document(document: dict) -> bool:
    doc_id = document["id"]
    title = document["title"]
    try:
        response = requests.delete(
            f"{BASE_URL}/documents/{doc_id}",
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        print(f"  ✅ Deleted {doc_id}: {title}")
        return True
    except Exception as exc:
        print(f"  ❌ Failed to delete {doc_id}: {title} ({exc})")
        return False


def main() -> None:
    print("=" * 80)
    print("BATCH DUPLICATE CLEANUP")
    print("=" * 80)

    documents = fetch_documents()
    print(f"Found {len(documents)} documents")

    duplicates = group_duplicates(documents)
    print(f"Need to delete {len(duplicates)} old documents")

    if not duplicates:
        print("Nothing to delete.")
        return

    success_count = 0
    fail_count = 0

    for index, document in enumerate(duplicates, start=1):
        print(f"[{index}/{len(duplicates)}] Deleting ID {document['id']} ({document['title']})")
        if delete_document(document):
            success_count += 1
        else:
            fail_count += 1
        time.sleep(BATCH_PAUSE_SECONDS)

    print("\n" + "=" * 80)
    print(f"Completed. Success: {success_count}, Failed: {fail_count}")
    print("=" * 80)

    try:
        remaining = fetch_documents()
        print(f"Remaining documents: {len(remaining)}")
        for doc in sorted(remaining, key=lambda item: item["id"], reverse=True):
            print(f"  - {doc['id']}: {doc['title']} ({doc.get('chunks', 0)} chunks)")
    except Exception as exc:
        print(f"Could not fetch final document list: {exc}")


if __name__ == "__main__":
    main()