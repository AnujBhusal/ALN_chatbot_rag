from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import requests

from app.api.auth import get_current_user_optional, get_current_user
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
    mode: str = Field(default="general", pattern="^(general|documents)$")
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


class HistoryMessage(BaseModel):
    session_id: str
    role: str
    message: str
    created_at: Any


class ConversationMessage(BaseModel):
    role: str
    message: str
    created_at: Any


class ConversationSummary(BaseModel):
    session_id: str
    message_count: int
    first_message: str
    created_at: Any
    updated_at: Any


class Conversation(BaseModel):
    summary: ConversationSummary
    messages: List[ConversationMessage]


class GroupedHistoryResponse(BaseModel):
    conversations: List[Conversation]


class HistoryResponse(BaseModel):
    messages: List[HistoryMessage]


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


def _lookup_wikipedia_answer(query: str) -> Optional[str]:
    """Try to answer an open-domain question using Wikipedia search + summary."""
    try:
        headers = {"User-Agent": "ALN-Assistant/1.0 (GeneralKnowledgeLookup)"}
        search_response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 1,
            },
            headers=headers,
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
            headers=headers,
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


def _lookup_duckduckgo_answer(query: str) -> Optional[str]:
    """Fallback open-domain lookup using DuckDuckGo Instant Answer API."""
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
                "no_redirect": 1,
            },
            timeout=10,
            headers={"User-Agent": "ALN-Assistant/1.0 (GeneralKnowledgeLookup)"},
        )
        response.raise_for_status()
        data = response.json()

        abstract = (data.get("AbstractText") or "").strip()
        if abstract:
            return abstract

        related = data.get("RelatedTopics") or []
        for item in related:
            text = (item.get("Text") or "").strip() if isinstance(item, dict) else ""
            if text:
                return text
            topics = item.get("Topics") if isinstance(item, dict) else None
            if isinstance(topics, list):
                for sub_item in topics:
                    sub_text = (sub_item.get("Text") or "").strip() if isinstance(sub_item, dict) else ""
                    if sub_text:
                        return sub_text

        return None
    except Exception as error:
        logger.debug(f"DuckDuckGo lookup failed for query '{query}': {error}")
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


def _build_query_filter(requested_document_type: Optional[str], role: str, year: Optional[int], target_document_ids: Optional[List[int]] = None) -> Optional[Dict[str, Any]]:
    clauses: List[Dict[str, Any]] = []

    if target_document_ids:
        # Pinecone uses floats for numbers in json, but $in works properly
        clauses.append({"document_id": {"$in": target_document_ids}})


    if requested_document_type:
        clauses.append({"document_type": {"$eq": requested_document_type}})

    if year is not None:
        clauses.append({"year": {"$eq": year}})

    if role != "admin":
        allowed_types = accessible_document_types(role)
        clauses.append({"document_type": {"$in": allowed_types}})

    if not clauses:
        return None

    if len(clauses) == 1:
        return clauses[0]

    return {"$and": clauses}


def _coerce_document_id(value: Any) -> Optional[int]:
    """Normalize document_id from Pinecone metadata (can be int/float/string)."""
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _tokenize_for_overlap(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", text.lower())}


def _rank_database_chunks_for_query(query: str, chunks: List[models.DocumentChunk], limit: int = 8) -> List[models.DocumentChunk]:
    """Rank DB chunks by multiple scoring methods (overlap + keyword + length)."""
    if not chunks:
        return []

    query_lc = query.lower()
    query_tokens = _tokenize_for_overlap(query)
    
    # Extract key year or number from query (e.g., "2020" from "nominees in 2020")
    year_match = re.search(r'\b(20\d{2})\b', query)
    year_keywords = [year_match.group(1)] if year_match else []
    
    scored: List[tuple[float, models.DocumentChunk]] = []
    
    for chunk in chunks:
        text = (chunk.chunk_text or "").strip()
        if not text:
            continue

        text_lc = text.lower()
        score = 0.0
        
        # 1. Exact phrase match (high weight)
        if query_lc in text_lc and len(query_lc) >= 5:
            score += 100
            logger.debug(f"      Exact phrase match: +100")
        
        # 2. Year/number match (high weight)
        for keyword in year_keywords:
            if keyword in text:
                score += 50
                logger.debug(f"      Year match {keyword}: +50")
        
        # 3. Token overlap (medium weight)
        chunk_tokens = _tokenize_for_overlap(text)
        overlap = len(query_tokens & chunk_tokens)
        if overlap > 0:
            density = overlap / max(len(query_tokens), 1)
            token_score = overlap * 10 + density * 5
            score += token_score
            logger.debug(f"      Token overlap {overlap}/{len(query_tokens)}: +{token_score}")
        
        # 4. Keyword presence (medium weight - for "nominees", "awardees", "recipients", etc)
        keyword_synonyms = {
            'nominees': ['nominee', 'nominees', 'recipient', 'awardee', 'recipient'],
            'award': ['award', 'awardee', 'winner', 'recipient'],
            'list': ['list', 'include', 'included', 'comprised'],
            'individuals': ['individual', 'person', 'people', 'officer']
        }
        
        for query_word in query_tokens:
            if query_word in ['nominee', 'recipients', 'awardee', 'individual', 'people']:
                for syn in keyword_synonyms.get(query_word, []):
                    if syn in text_lc:
                        score += 15
                        logger.debug(f"      Synonym match '{syn}': +15")
        
        # 5. Content length bonus (prefer substantial chunks over tiny ones)
        if len(text) > 200:
            score += 5
        
        if score > 0:
            scored.append((score, chunk))

    if not scored:
        logger.debug(f"      No scored chunks, returning first {limit} from database")
        return chunks[:limit]

    scored.sort(key=lambda item: item[0], reverse=True)
    result = [chunk for score, chunk in scored[:limit]]
    logger.debug(f"      Top 3 scores: {[s for s, _ in scored[:3]]}")
    return result


def _persist_user_chat(
    db: Session,
    user: Optional[models.User],
    session_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    if not user:
        return

    db.add(
        models.UserChatMessage(
            user_id=user.id,
            session_id=session_id,
            role="user",
            message=user_message,
        )
    )
    db.add(
        models.UserChatMessage(
            user_id=user.id,
            session_id=session_id,
            role="assistant",
            message=assistant_message,
        )
    )
    db.commit()


@router.post("/query", response_model=QueryResponse)
async def chat_query(
    request: QueryRequest,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
) -> QueryResponse:
    """Answer ALN queries with metadata-aware retrieval and grouped sources."""
    document_context = None
    target_document_ids: List[int] = []

    intent = detect_intent(request.query)
    requested_document_type = request.document_type or intent.document_type
    force_general_mode = request.mode == "general"

    if intent.is_small_talk and requested_document_type is None and request.document_id is None:
        answer = _small_talk_response(request.query)
        memory.add_message(request.session_id, "user", request.query)
        memory.add_message(request.session_id, "assistant", answer)
        _persist_user_chat(db, current_user, request.session_id, request.query, answer)
        return QueryResponse(answer=answer, sources=[], document_context=None)

    if (
        force_general_mode or _is_general_knowledge_query(request.query)
    ) and requested_document_type is None and request.document_id is None:
        history = memory.get_history(request.session_id)

        # Skip Wikipedia/DuckDuckGo - go straight to LLM for better answers
        answer = llm.answer_general_question(request.query, history)

        memory.add_message(request.session_id, "user", request.query)
        memory.add_message(request.session_id, "assistant", answer)
        _persist_user_chat(db, current_user, request.session_id, request.query, answer)
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

    logger.debug(f"🔍 Query: {request.query}")
    logger.debug(f"   - Target document IDs: {target_document_ids}")
    logger.debug(f"   - Requested type: {requested_document_type}")
    logger.debug(f"   - Role: {request.role}")
    
    query_embedding = embedder.embed_texts([request.query])[0]
    logger.debug(f"   - Embedding dimension: {len(query_embedding)}")
    
    query_filter = _build_query_filter(requested_document_type, request.role, intent.year, target_document_ids)
    logger.debug(f"   - Query filter: {query_filter}")

    top_k = 20 if intent.is_summary else 12
    logger.debug(f"   - Searching for top_k={top_k} results...")
    results = vectorstore.query(query_embedding, top_k=top_k, query_filter=query_filter)
    logger.info(f"   ✅ Got {len(results)} results from vector store")
    if results:
        logger.debug(f"      Top result score: {results[0].get('score', 'N/A')}")

    # Defensive retry: if strict metadata filter yields zero, retry without filter
    # and apply filtering in app logic. This guards against metadata type mismatches.
    if not results and query_filter is not None:
        logger.warning("   ⚠️  No results with Pinecone filter, retrying unfiltered and filtering in app...")
        unfiltered_results = vectorstore.query(query_embedding, top_k=max(top_k * 3, 30), query_filter=None)
        logger.info(f"   ✅ Unfiltered retry got {len(unfiltered_results)} results")
        if unfiltered_results:
            results = unfiltered_results

    # If year-specific filtering is too strict, retry without year while preserving role/doc-type constraints.
    if not results and intent.year is not None:
        logger.warning(f"   ⚠️  No results with year filter, retrying without year...")
        fallback_without_year_filter = _build_query_filter(requested_document_type, request.role, None, target_document_ids)
        results = vectorstore.query(query_embedding, top_k=top_k, query_filter=fallback_without_year_filter)
        logger.info(f"   ✅ Retry got {len(results)} results")

    if target_document_ids:
        logger.debug(f"   - Filtering results to target documents {target_document_ids}...")
        # Force strict filtering just in case, and DO NOT fall back to other documents if empty.
        allowed_document_ids = set(target_document_ids)
        filtered_results = [
            result
            for result in results
            if _coerce_document_id(result.get("metadata", {}).get("document_id")) in allowed_document_ids
        ]
        logger.info(f"   ✅ Filtered to {len(filtered_results)} results from target documents")
        results = filtered_results

    context = _build_context_blocks(results)
    logger.info(f"   📝 Context built: {len(context)} chars, {context[:100]}...")

    if not context and target_document_ids:
        logger.warning(f"   ⚠️  Empty context from vector search! Checking database chunks...")
        chunks = db.query(models.DocumentChunk).filter(models.DocumentChunk.document_id.in_(target_document_ids)).all()
        logger.info(f"   📊 Found {len(chunks)} chunks in database")
        if chunks:
            logger.debug(f"      Sample chunk: {chunks[0].chunk_text[:100]}...")
        
        ranked_chunks = _rank_database_chunks_for_query(request.query, chunks, limit=8)
        logger.info(f"   🎯 Ranked {len(ranked_chunks)} fallback chunks for query: '{request.query}'")
        if ranked_chunks:
            logger.debug(f"      Top chunk: {ranked_chunks[0].chunk_text[:100]}...")
        
        # Build document lookup cache to get correct metadata for each chunk
        doc_cache = {}
        for chunk in ranked_chunks:
            if chunk.document_id not in doc_cache:
                doc = db.query(models.Document).filter(models.Document.id == chunk.document_id).first()
                doc_cache[chunk.document_id] = doc
        
        results = []
        for chunk in ranked_chunks:
            doc = doc_cache.get(chunk.document_id)
            results.append({
                "id": f"chunk_{chunk.id}",
                "score": 0.5,
                "metadata": {
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.id,
                    "text": chunk.chunk_text,
                    "title": doc.title if doc else "Untitled Document",
                    "document_type": doc.document_type if doc else "general",
                    "year": doc.year if doc else None,
                },
            })
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
        "Answer primarily using the provided ALN documents. "
        "You may reference earlier turns in chat history for context on follow-ups. "
        "If the answer is not in the documents, say 'Not available in ALN documents'."
    )

    if requested_document_type and context:
        answer_instruction += (
            f" The user selected the {requested_document_type.replace('_', ' ')} PDF set, "
            "so answer using that document set primarily and keep the response concise."
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
    _persist_user_chat(db, current_user, request.session_id, request.query, answer)

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


@router.get("/history", response_model=GroupedHistoryResponse)
async def get_chat_history(
    limit: int = Query(default=50, ge=1, le=500),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupedHistoryResponse:
    """
    Retrieve chat history grouped by session/conversation.
    Returns recent conversations with full message history for each.
    """
    # Fetch messages for this user ordered by session and creation time
    messages = (
        db.query(models.UserChatMessage)
        .filter(models.UserChatMessage.user_id == current_user.id)
        .order_by(
            models.UserChatMessage.session_id.desc(),
            models.UserChatMessage.created_at.asc(),
        )
        .all()
    )

    # Group messages by session_id
    from collections import OrderedDict
    sessions_dict: Dict[str, List[models.UserChatMessage]] = OrderedDict()
    for message in messages:
        if message.session_id not in sessions_dict:
            sessions_dict[message.session_id] = []
        sessions_dict[message.session_id].append(message)

    # Build conversation objects, limiting to most recent sessions
    conversations: List[Conversation] = []
    for session_id in reversed(list(sessions_dict.keys())[:limit]):
        session_messages = sessions_dict[session_id]
        if not session_messages:
            continue

        # Create summary
        first_message = session_messages[0].message if session_messages else ""
        created_at = session_messages[0].created_at
        updated_at = session_messages[-1].created_at

        summary = ConversationSummary(
            session_id=session_id,
            message_count=len(session_messages),
            first_message=first_message[:100],  # Truncate for summary
            created_at=created_at,
            updated_at=updated_at,
        )

        # Build message list
        conv_messages = [
            ConversationMessage(
                role=msg.role,
                message=msg.message,
                created_at=msg.created_at,
            )
            for msg in session_messages
        ]

        conversations.append(Conversation(summary=summary, messages=conv_messages))

    return GroupedHistoryResponse(conversations=conversations)


@router.delete("/history/{session_id}")
async def delete_chat_session(
    session_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Delete all chat messages for a given session_id belonging to the current user.
    Returns 404 if the session does not exist or belongs to another user.
    """
    deleted_count = (
        db.query(models.UserChatMessage)
        .filter(
            models.UserChatMessage.session_id == session_id,
            models.UserChatMessage.user_id == current_user.id,
        )
        .delete(synchronize_session=False)
    )

    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found or already deleted")

    db.commit()
    logger.info(f"Deleted session {session_id} ({deleted_count} messages) for user {current_user.id}")
    return {"message": "Chat session deleted", "session_id": session_id, "deleted_messages": deleted_count}


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


@router.get("/documents/{document_id}/full-text")
async def document_full_text(
    document_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the complete reconstructed text of a document from all stored chunks,
    ordered by chunk id (insertion / page order).
    Used by the frontend reference modal to show the full document content.
    """
    document = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = (
        db.query(models.DocumentChunk)
        .filter(models.DocumentChunk.document_id == document_id)
        .order_by(models.DocumentChunk.id.asc())
        .all()
    )

    if not chunks:
        raise HTTPException(status_code=404, detail="No content found for this document")

    full_text = "\n\n".join(chunk.chunk_text.strip() for chunk in chunks if chunk.chunk_text)

    return {
        "document_id": document.id,
        "title": document.title,
        "filename": document.filename,
        "document_type": document.document_type,
        "year": document.year,
        "chunk_count": len(chunks),
        "word_count": len(full_text.split()),
        "full_text": full_text,
    }
