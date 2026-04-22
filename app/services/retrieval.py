from __future__ import annotations

from typing import Any, Dict, List


def group_results_by_document(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}

    for result in results:
        metadata = result.get("metadata", {}) or {}
        document_id = str(metadata.get("document_id", result.get("id", "unknown")))
        existing = grouped.get(document_id)
        if existing is None:
            grouped[document_id] = {
                "document_id": metadata.get("document_id"),
                "title": metadata.get("title") or "Untitled Document",
                "type": metadata.get("document_type", "general"),
                "year": metadata.get("year"),
                "sources": [],
            }
            existing = grouped[document_id]

        existing["sources"].append(result)

    return list(grouped.values())


def build_source_items(results: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    grouped = group_results_by_document(results)
    sources: List[Dict[str, Any]] = []

    for group in grouped[:limit]:
        snippets: List[str] = []
        for source in group["sources"][:2]:
            metadata = source.get("metadata", {}) or {}
            snippet = metadata.get("text", "")
            if snippet:
                snippets.append(snippet[:120].strip())

        sources.append(
            {
                "document_id": group["document_id"],
                "title": group["title"],
                "type": group["type"],
                "year": group["year"],
                "snippet": " ".join(snippets)[:140],
            }
        )

    return sources


def build_summary_context(results: List[Dict[str, Any]], docs_limit: int = 6, chunks_per_doc: int = 3) -> str:
    grouped = group_results_by_document(results)
    blocks: List[str] = []

    for group in grouped[:docs_limit]:
        header = f"[Document: {group['title']}] [Type: {group['type']}] [Year: {group['year'] if group['year'] is not None else 'N/A'}]"
        excerpts: List[str] = []
        for source in group["sources"][:chunks_per_doc]:
            metadata = source.get("metadata", {}) or {}
            text = metadata.get("text", "").strip()
            if text:
                excerpts.append(text)
        if excerpts:
            blocks.append(header + "\n" + "\n".join(excerpts))

    return "\n\n".join(blocks)
