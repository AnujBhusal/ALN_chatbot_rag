"""
Query Rewriting Service for improved semantic retrieval.

Handles:
- Synonym expansion (winners → awardees recipients)
- Domain context addition
- Follow-up question resolution
- Vague reference clarification
"""

from typing import List, Dict, Optional
import logging
import re

logger = logging.getLogger(__name__)

# Domain-specific synonym expansions
SYNONYMS = {
    "winners": "awardees recipients honorees",
    "winner": "awardee recipient honoree",
    "alumni": "past awardees former recipients graduates",
    "alumnis": "past awardees former recipients graduates",
    "alumnus": "past awardee former recipient graduate",
    "employees": "staff workers personnel officers",
    "employee": "staff worker personnel officer",
    "rules": "policies regulations guidelines procedures",
    "rule": "policy regulation guideline procedure",
    "selected": "awardees recipients chosen nominated",
    "chosen": "awardees recipients selected nominated",
    "got award": "awardee recipient honor",
    "received award": "awardee recipient honor",
    "list": "enumerate names who include comprised",
    "tell": "explain state mention list",
    "who": "which people individuals names",
    "program": "Integrity Icon initiative project scheme",
}

# Domain keywords to potentially inject
DOMAIN_KEYWORDS = {
    "integrity icon": True,
    "awardee": True,
    "recipient": True,
    "nomination": True,
    "governance": True,
    "aln": True,
}


def _expand_synonyms(query: str) -> str:
    """Lightweight synonym pre-expansion without LLM."""
    expanded = query.lower()
    added_terms = []

    for key, value in SYNONYMS.items():
        # Use word boundary matching to avoid partial matches
        pattern = r'\b' + re.escape(key) + r'\b'
        if re.search(pattern, expanded, re.IGNORECASE):
            added_terms.append(value)

    if added_terms:
        expanded += " " + " ".join(added_terms)
        logger.debug(f"📝 Synonym expansion: added {len(added_terms)} term groups")

    return expanded.strip()


def _resolve_followup(query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
    """
    Resolve follow-up questions by referencing recent context.
    
    Examples:
    - "mention them" → "mention the awardees from the Integrity Icon program"
    - "every year" → "awardees selected every year in Integrity Icon"
    """
    if not chat_history or len(chat_history) < 2:
        return query

    followup_cues = [
        "them", "those", "these", "that", "this", "it", "they",
        "also", "too", "following", "next", "previous", "earlier"
    ]
    
    query_lower = query.lower()
    is_followup = any(cue in query_lower for cue in followup_cues) or len(query.split()) <= 5

    if not is_followup:
        return query

    # Get last user message and assistant response
    last_user_msg = ""
    last_assistant_msg = ""

    for msg in reversed(chat_history):
        role = (msg.get("role") or "").lower()
        content = (msg.get("message") or "").strip()

        if not content:
            continue

        if not last_user_msg and role == "user":
            last_user_msg = content
        elif not last_assistant_msg and role == "assistant":
            last_assistant_msg = content

        if last_user_msg and last_assistant_msg:
            break

    if not last_user_msg:
        return query

    # Compact the context
    last_user_compact = last_user_msg[:100]
    if len(last_user_msg) > 100:
        last_user_compact = last_user_msg[:100].rsplit(" ", 1)[0].strip() + "..."

    resolved = f"{query} related to {last_user_compact}".strip()
    logger.debug(f"📝 Follow-up resolved: '{query}' → '{resolved}'")

    return resolved


def rewrite_query(
    query: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    use_llm_rewrite: bool = True,
) -> str:
    """
    Rewrite user query to improve semantic retrieval.

    Process:
    1. Lightweight synonym expansion
    2. Follow-up resolution from chat history
    3. Optional: LLM-based semantic rewrite (if enabled)

    Args:
        query: Original user query
        chat_history: List of previous messages with role and message fields
        use_llm_rewrite: If True and LLM available, perform semantic rewrite

    Returns:
        Rewritten query optimized for retrieval
    """
    if not query or not isinstance(query, str):
        return query

    logger.debug(f"🔄 Query Rewriter started: '{query}'")

    # Step 1: Try to resolve follow-ups
    query = _resolve_followup(query, chat_history)

    # Step 2: Expand synonyms
    expanded = _expand_synonyms(query)

    if use_llm_rewrite:
        # Step 3: Optional LLM-based rewrite for semantic improvements
        try:
            from app.services.llm import LLMService
            llm_service = LLMService()

            if llm_service.groq_client or llm_service.use_ollama or llm_service.hf_headers:
                rewritten = _llm_rewrite_query(query, llm_service)
                if rewritten and rewritten != query:
                    logger.info(f"🧠 LLM rewrite: '{query}' → '{rewritten}'")
                    return rewritten
        except Exception as e:
            logger.warning(f"⚠️ LLM rewrite failed: {e}, falling back to expansion")

    logger.debug(f"✅ Rewritten query: '{expanded}'")
    return expanded


def _llm_rewrite_query(query: str, llm_service) -> Optional[str]:
    """
    Use LLM to perform semantic query rewriting.

    Quick, focused rewrite to improve retrieval without changing original intent.
    """
    prompt = f"""You are a query rewriting expert for document retrieval.

Rewrite this query to be more specific and semantically rich, improving search results.

RULES:
- Keep it under 20 words
- Preserve original intent
- Add related terms or domain keywords if helpful
- DO NOT answer the question
- OUTPUT ONLY the rewritten query (nothing else)

Query: {query}

Rewritten Query:"""

    try:
        response = llm_service.call_llm(prompt)
        if response:
            rewritten = response.strip()
            # Ensure we got an actual rewrite, not just echoing
            if len(rewritten) > 3 and rewritten.lower() != query.lower():
                return rewritten
    except Exception as e:
        logger.debug(f"LLM rewrite call failed: {e}")

    return None


def expand_query_with_aliases(query: str) -> str:
    """
    Expand query with common aliases for better Pinecone matching.
    Used in conjunction with vector search.
    """
    aliases = []

    # Check for key terms and add aliases
    if any(word in query.lower() for word in ["awardee", "award", "winner", "recipient"]):
        aliases.extend(["Integrity Icon", "awardee", "recipient", "honor"])

    if any(word in query.lower() for word in ["governance", "policy", "internal"]):
        aliases.extend(["governance", "policy", "procedures"])

    if any(word in query.lower() for word in ["proposal", "donor", "funding"]):
        aliases.extend(["proposal", "donor", "fund", "project"])

    if aliases:
        expanded = query + " " + " ".join(set(aliases))
        logger.debug(f"📌 Aliases added: {aliases}")
        return expanded

    return query
