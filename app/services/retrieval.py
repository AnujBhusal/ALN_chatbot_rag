from __future__ import annotations

from typing import Any, Dict, List


def group_results_by_document(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group flat retrieval `results` by document. Compute a per-document score using
    the average of the top-k chunk scores (by default top_k=3). This avoids
    letting documents with many medium-scoring chunks dominate purely by count.

    - Deduplicate sources by chunk id when available.
    - Sort sources within each document by individual score desc.
    - Return grouped list sorted by document score desc.
    """

    grouped: Dict[str, Dict[str, Any]] = {}

    for result in results:
        metadata = result.get("metadata", {}) or {}
        # Normalize document id to string for dictionary keying
        raw_doc_id = metadata.get("document_id") if metadata.get("document_id") is not None else result.get("id")
        try:
            document_id = str(int(float(raw_doc_id)))
        except Exception:
            document_id = str(raw_doc_id)

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

    # Post-process groups: dedupe, sort sources by score desc, compute doc score
    grouped_list: List[Dict[str, Any]] = []
    for doc_key, group in grouped.items():
        sources = group.get("sources", [])

        # Deduplicate by chunk id or by text if chunk id missing
        seen_chunk_ids = set()
        deduped_sources: List[Dict[str, Any]] = []
        for s in sources:
            meta = s.get("metadata", {}) or {}
            chunk_id = meta.get("chunk_id") or meta.get("id") or None
            identifier = None
            try:
                identifier = int(float(chunk_id)) if chunk_id is not None else None
            except Exception:
                identifier = str(chunk_id) if chunk_id is not None else None

            # fallback to text snippet dedupe key
            text_key = (meta.get("text") or "")[:120]

            dedupe_key = identifier if identifier is not None else text_key
            if dedupe_key in seen_chunk_ids:
                continue
            seen_chunk_ids.add(dedupe_key)
            deduped_sources.append(s)

        # Sort sources by their match score (desc). Missing score -> 0.0
        def _score_of(item: Dict[str, Any]) -> float:
            try:
                return float(item.get("score", 0) or 0)
            except Exception:
                return 0.0

        deduped_sources.sort(key=_score_of, reverse=True)

        # Compute document-level score: average of top-k chunk scores (k=3)
        top_k = 3
        top_scores = [_score_of(s) for s in deduped_sources[:top_k]]
        doc_score = float(sum(top_scores) / max(1, len(top_scores))) if top_scores else 0.0

        grouped_list.append({
            "document_id": group.get("document_id"),
            "title": group.get("title"),
            "type": group.get("type"),
            "year": group.get("year"),
            "sources": deduped_sources,
            "_doc_score": doc_score,
        })

    # Sort documents by the computed document score (desc)
    grouped_list.sort(key=lambda g: g.get("_doc_score", 0.0), reverse=True)

    # Remove internal score field before returning
    for g in grouped_list:
        if "_doc_score" in g:
            g.pop("_doc_score")

    return grouped_list


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
