from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from sqlalchemy.orm import Session
import requests

from app.db import models
from app.db.session import get_db
from app.services.embeddings import EmbeddingService
from app.services.intent import (
    can_access_document_type,
    detect_intent,
    accessible_document_types,
)
from app.services.llm import LLMService
from app.services.memory import MemoryService
from app.services.retrieval import build_source_items, build_summary_context, group_results_by_document
from app.services.vectorstore import VectorStoreService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])

embedder = EmbeddingService()
vectorstore = VectorStoreService()
memory = MemoryService()
llm = LLMService()


class QueryRequest(BaseModel):
    session_id: str
    query: str
    document_id: Optional[int] = None
    use_latest_document: bool = True
    role: str = Field(default="staff", pattern="^(admin|staff)$")
    document_type: Optional[str] = Field(default=None)


class SourceItem(BaseModel):
    document_id: Optional[int] = None
    title: str
    type: str
    year: Optional[int] = None
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    document_context: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    session_id: str
    answer: str
    rating: str = Field(pattern="^(up|down)$")
    comment: Optional[str] = None


def _small_talk_response(query: str) -> str:
    normalized = query.lower().strip()

    if any(greet in normalized for greet in ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]):
        return "Hello! I can help with both general conversation and ALN document questions."
    if "how are you" in normalized:
        return "I am doing well. I can chat generally or help you find information from ALN documents."
    if "who are you" in normalized or "what can you do" in normalized:
        return "I am your ALN assistant. I can answer general questions and also retrieve evidence-based answers from uploaded ALN documents."
    if "thank" in normalized:
        return "You are welcome. Let me know what you want to explore next."

    return "I can help with general questions, and I can also answer using ALN documents when you need evidence-backed responses."


def _is_general_knowledge_query(query: str) -> bool:
    normalized = query.lower().strip()
    document_patterns = [
        "proposal",
        "policy",
        "meeting",
        "minutes",
        "integrity icon",
        "governance weekly",
        "document",
        "pdf",
        "upload",
        "source",
    ]

    has_document_pattern = any(pattern in normalized for pattern in document_patterns)
    return not has_document_pattern


def _general_fallback_response(query: str) -> str:
    normalized = query.lower().strip()
    if "accountability lab nepal" in normalized:
        return (
            "Accountability Lab Nepal is the Nepal chapter of Accountability Lab, "
            "a civic innovation organization that supports accountability through active citizens, "
            "responsible leadership, and stronger public institutions."
        )

    return (
        "I can answer general questions as well as ALN document-based questions. "
        "Ask me anything, and I will switch between conversational and evidence-backed modes as needed."
    )


def _lookup_wikipedia_answer(query: str) -> Optional[str]:
    """Try to answer an open-domain question using Wikipedia search + summary."""
    try:
        search_response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 1,
            },
            timeout=10,
        )
        search_response.raise_for_status()
        search_data = search_response.json()
        search_results = search_data.get("query", {}).get("search", [])
        if not search_results:
            return None

        title = search_results[0].get("title")
        if not title:
            return None

        summary_response = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}",
            timeout=10,
        )
        summary_response.raise_for_status()
        summary_data = summary_response.json()
        extract = summary_data.get("extract") or summary_data.get("description")
        if not extract:
            return None

        return extract.strip()
    except Exception as error:
        logger.debug(f"Wikipedia lookup failed for query '{query}': {error}")
        return None


def _build_document_context(document: Optional[models.Document]) -> Optional[Dict[str, Any]]:
    if not document:
        return None

    return {
        "id": document.id,
        "title": document.title,
        "filename": document.filename,
        "type": document.document_type,
        "year": document.year,
        "uploaded": document.uploaded_at,
    }


def _build_context_blocks(results: List[Dict[str, Any]], chunks_per_doc: int = 3) -> str:
    grouped = group_results_by_document(results)
    blocks: List[str] = []

    for group in grouped:
        header = f"[Title: {group['title']}] [Type: {group['type']}] [Year: {group['year'] if group['year'] is not None else 'N/A'}]"
        chunk_lines = []
        for source in group["sources"][:chunks_per_doc]:
            metadata = source.get("metadata", {}) or {}
            chunk_lines.append(metadata.get("text", ""))
        if chunk_lines:
            blocks.append(header + "\n" + "\n".join(chunk_lines))

    return "\n\n".join(blocks)


def _build_context_from_documents(documents: List[models.Document], db: Session, chunks_per_doc: int = 3) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for document in documents:
        chunks = (
            db.query(models.DocumentChunk)
            .filter(models.DocumentChunk.document_id == document.id)
            .order_by(models.DocumentChunk.id.asc())
            .limit(chunks_per_doc)
            .all()
        )
        for chunk in chunks:
            results.append(
                {
                    "id": f"chunk_{chunk.id}",
                    "score": 0.4,
                    "metadata": {
                        "document_id": document.id,
                        "chunk_id": chunk.id,
                        "text": chunk.chunk_text,
                        "title": document.title,
                        "document_type": document.document_type,
                        "year": document.year,
                    },
                }
            )
    return results


def _build_query_filter(requested_document_type: Optional[str], role: str, year: Optional[int]) -> Optional[Filter]:
    must_conditions: List[FieldCondition] = []
    should_conditions: List[FieldCondition] = []

    if requested_document_type:
        must_conditions.append(FieldCondition(key="document_type", match=MatchValue(value=requested_document_type)))

    if year is not None:
        must_conditions.append(FieldCondition(key="year", match=MatchValue(value=year)))

    if role != "admin":
        allowed_types = accessible_document_types(role)
        should_conditions = [
            FieldCondition(key="document_type", match=MatchValue(value=document_type))
            for document_type in allowed_types
        ]

    if not must_conditions and not should_conditions:
        return None

    if should_conditions and not must_conditions:
        return Filter(should=should_conditions)

    if should_conditions:
        return Filter(must=must_conditions, should=should_conditions)

    return Filter(must=must_conditions)


@router.post("/query", response_model=QueryResponse)
async def chat_query(request: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    """Answer ALN queries with metadata-aware retrieval and grouped sources."""
    document_context = None
    target_document_ids: List[int] = []

    intent = detect_intent(request.query)
    requested_document_type = request.document_type or intent.document_type

    if intent.is_small_talk and requested_document_type is None and request.document_id is None:
        answer = _small_talk_response(request.query)
        memory.add_message(request.session_id, "user", request.query)
        memory.add_message(request.session_id, "assistant", answer)
        return QueryResponse(answer=answer, sources=[], document_context=None)

    if _is_general_knowledge_query(request.query) and requested_document_type is None and request.document_id is None:
        history = memory.get_history(request.session_id)

        wikipedia_answer = _lookup_wikipedia_answer(request.query)
        if wikipedia_answer:
            memory.add_message(request.session_id, "user", request.query)
            memory.add_message(request.session_id, "assistant", wikipedia_answer)
            return QueryResponse(answer=wikipedia_answer, sources=[], document_context=None)

        general_prompt = llm.build_prompt(
            request.query,
            "",
            history,
            system_instruction=(
                "You are a helpful conversational assistant. Answer clearly and naturally. "
                "You may use general knowledge when the user is not requesting ALN document retrieval."
            ),
        )
        answer = llm.call_llm(general_prompt)

        if "could not find enough" in answer.lower() or "not available in aln documents" in answer.lower():
            answer = _general_fallback_response(request.query)

        memory.add_message(request.session_id, "user", request.query)
        memory.add_message(request.session_id, "assistant", answer)
        return QueryResponse(answer=answer, sources=[], document_context=None)

    if requested_document_type and not can_access_document_type(request.role, requested_document_type):
        raise HTTPException(status_code=403, detail="This document type is restricted for your role")

    if request.document_id is not None:
        document = db.query(models.Document).filter(models.Document.id == request.document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        if not can_access_document_type(request.role, document.document_type):
            raise HTTPException(status_code=403, detail="This document is restricted for your role")
        target_document_ids = [document.id]
        document_context = _build_document_context(document)
    elif not requested_document_type and request.use_latest_document and not intent.is_summary:
        latest_document = db.query(models.Document).order_by(models.Document.uploaded_at.desc()).first()
        if latest_document and can_access_document_type(request.role, latest_document.document_type):
            target_document_ids = [latest_document.id]
            document_context = _build_document_context(latest_document)

    query_embedding = embedder.embed_texts([request.query])[0]
    query_filter = _build_query_filter(requested_document_type, request.role, intent.year)

    top_k = 20 if intent.is_summary else 12
    results = vectorstore.query(query_embedding, top_k=top_k, query_filter=query_filter)

    # If year-specific filtering is too strict, retry without year while preserving role/doc-type constraints.
    if not results and intent.year is not None:
        fallback_without_year_filter = _build_query_filter(requested_document_type, request.role, None)
        results = vectorstore.query(query_embedding, top_k=top_k, query_filter=fallback_without_year_filter)

    if target_document_ids:
        filtered = [
            result
            for result in results
            if result.get("metadata", {}).get("document_id") in target_document_ids
        ]
        if filtered:
            results = filtered

    context = _build_context_blocks(results)

    if not context and target_document_ids:
        chunks = db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id.in_(target_document_ids)).all()
        results = [
            {
                "id": f"chunk_{chunk.id}",
                "score": 0.5,
                "metadata": {
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.id,
                    "text": chunk.chunk_text,
                    "title": document_context["title"] if document_context else "Untitled Document",
                    "document_type": document_context["type"] if document_context else "general",
                    "year": document_context["year"] if document_context else None,
                },
            }
            for chunk in chunks[:5]
        ]
        context = _build_context_blocks(results)

    if not context and requested_document_type:
        documents_for_type = (
            db.query(models.Document)
            .filter(models.Document.document_type == requested_document_type)
            .order_by(models.Document.uploaded_at.desc())
            .all()
        )
        if documents_for_type:
            results = _build_context_from_documents(documents_for_type, db, chunks_per_doc=3)
            context = _build_context_blocks(results)

    history = memory.get_history(request.session_id)

    answer_instruction = (
        "Answer ONLY using the provided ALN documents. If not found, say 'Not available in ALN documents'."
    )

    if requested_document_type and context:
        answer_instruction += (
            f" The user selected the {requested_document_type.replace('_', ' ')} PDF set, "
            "so answer using only that document set and keep the response concise."
        )

    if intent.is_summary and context:
        summary_prompt = llm.build_prompt(
            request.query,
            build_summary_context(results),
            [],
            system_instruction=(
                "You are preparing an evidence-backed synthesis for ALN. "
                "Summarize themes and commitments across documents, cite document titles where possible, "
                "and do not use information outside the provided context."
            ),
        )
        summary_draft = llm.call_llm(summary_prompt)

        final_prompt = llm.build_prompt(
            request.query,
            f"Summary Draft:\n{summary_draft}\n\nEvidence:\n{context}",
            history,
            system_instruction=answer_instruction + " Provide a concise multi-document summary in 4-6 bullets.",
        )
        answer = llm.call_llm(final_prompt)
    else:
        prompt = llm.build_prompt(
            request.query,
            context,
            history,
            system_instruction=answer_instruction,
        )
        answer = llm.call_llm(prompt)

    memory.add_message(request.session_id, "user", request.query)
    memory.add_message(request.session_id, "assistant", answer)

    return QueryResponse(
        answer=answer,
        sources=[SourceItem(**source) for source in build_source_items(results)],
        document_context=document_context,
    )


@router.post("/feedback")
async def submit_feedback(payload: FeedbackRequest, db: Session = Depends(get_db)):
    feedback = models.ChatFeedback(
        session_id=payload.session_id,
        answer=payload.answer,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return {"message": "Feedback saved", "feedback_id": feedback.id}


@router.get("/documents")
async def list_documents(
    role: str = Query(default="staff", pattern="^(admin|staff)$"),
    db: Session = Depends(get_db),
):
    """List uploaded documents, filtered by role access."""
    documents = db.query(models.Document).order_by(models.Document.uploaded_at.desc()).all()
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "title": doc.title,
            "document_type": doc.document_type,
            "year": doc.year,
            "program_name": doc.program_name,
            "donor_name": doc.donor_name,
            "filetype": doc.filetype,
            "uploaded_at": doc.uploaded_at,
            "chunk_count": len(doc.chunks) if hasattr(doc, "chunks") else 0,
        }
        for doc in documents
        if can_access_document_type(role, doc.document_type)
    ]


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    role: str = Query(default="admin", pattern="^(admin|staff)$"),
    db: Session = Depends(get_db),
):
    """Delete a document and all its chunks. Restricted to admin."""
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete documents")

    document = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        vectorstore.delete_by_document_id(document_id)
    except Exception as e:
        logger.warning(f"Could not delete from vector store: {e}")

    db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id == document_id).delete()
    db.delete(document)
    db.commit()

    return {"message": f"Document {document_id} deleted successfully"}


@router.get("/documents/{document_id}/preview")
async def document_preview(
    document_id: int,
    role: str = Query(default="staff", pattern="^(admin|staff)$"),
    db: Session = Depends(get_db),
):
    """Return lightweight preview text for a document."""
    document = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if not can_access_document_type(role, document.document_type):
        raise HTTPException(status_code=403, detail="This document is restricted for your role")

    chunks = (
        db.query(models.DocumentChunk)
        .filter(models.DocumentChunk.document_id == document_id)
        .order_by(models.DocumentChunk.id.asc())
        .limit(5)
        .all()
    )

    return {
        "document_id": document.id,
        "title": document.title,
        "document_type": document.document_type,
        "year": document.year,
        "preview_text": "\n\n".join([chunk.chunk_text for chunk in chunks]),
    }
