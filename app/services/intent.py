from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import re


DOCUMENT_TYPE_KEYWORDS = {
    "donor_proposal": ["donor", "proposal", "funding", "grant", "budget", "concept note", "concept paper"],
    "integrity_icon": ["integrity icon", "integrity-icon", "integrityicon", "nomination"],
    "governance_weekly": ["governance weekly", "weekly governance", "governance update"],
    "internal_policy": ["policy", "sop", "standard operating procedure", "internal policy", "guideline"],
    "meeting_notes": ["meeting notes", "minutes", "meeting minute", "action points", "agenda"],
}

SUMMARY_HINTS = ["summarize", "summary", "overview", "across proposals", "across documents", "key commitments"]
SENSITIVE_DOCUMENT_TYPES = {"internal_policy"}
YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")
SMALL_TALK_HINTS = {
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "how are you",
    "who are you",
    "what can you do",
    "thanks",
    "thank you",
}
ROLE_ALLOWED_DOCUMENT_TYPES = {
    "admin": [
        "donor_proposal",
        "integrity_icon",
        "governance_weekly",
        "internal_policy",
        "meeting_notes",
        "general",
    ],
    "staff": [
        "donor_proposal",
        "integrity_icon",
        "governance_weekly",
        "meeting_notes",
        "general",
    ],
}


@dataclass(frozen=True)
class DetectedIntent:
    document_type: Optional[str]
    is_summary: bool
    year: Optional[int]
    is_small_talk: bool


def detect_document_type(query: str) -> Optional[str]:
    normalized_query = query.lower()
    for document_type, keywords in DOCUMENT_TYPE_KEYWORDS.items():
        if any(keyword in normalized_query for keyword in keywords):
            return document_type
    return None


def is_summary_query(query: str) -> bool:
    normalized_query = query.lower()
    return any(hint in normalized_query for hint in SUMMARY_HINTS)


def detect_intent(query: str) -> DetectedIntent:
    normalized_query = query.lower().strip()
    year_match = YEAR_PATTERN.search(query)
    year = int(year_match.group(1)) if year_match else None

    # Use word-boundary matching to avoid "hi" matching "things", etc.
    is_small_talk = any(
        re.search(r'\b' + re.escape(hint) + r'\b', normalized_query)
        for hint in SMALL_TALK_HINTS
    )

    return DetectedIntent(
        document_type=detect_document_type(query),
        is_summary=is_summary_query(query),
        year=year,
        is_small_talk=is_small_talk,
    )


def accessible_document_types(role: str) -> list[str]:
    return ROLE_ALLOWED_DOCUMENT_TYPES.get(role, ROLE_ALLOWED_DOCUMENT_TYPES["staff"])


def can_access_document_type(role: str, document_type: str) -> bool:
    allowed = accessible_document_types(role)
    return document_type in allowed
