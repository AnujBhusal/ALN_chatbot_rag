from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

DOCUMENT_TYPES = {
    "donor_proposal",
    "integrity_icon",
    "governance_weekly",
    "internal_policy",
    "meeting_notes",
    "general",
}

DOCUMENT_TYPE_KEYWORDS = {
    "donor_proposal": [
        "donor proposal",
        "proposal",
        "funding",
        "grant",
        "budget",
        "concept note",
        "concept paper",
    ],
    "integrity_icon": [
        "integrity icon",
        "integrity-icon",
        "nominations",
        "nomination",
        "award",
    ],
    "governance_weekly": [
        "governance weekly",
        "weekly governance",
        "governance update",
        "governance meeting",
    ],
    "internal_policy": [
        "policy",
        "sop",
        "standard operating procedure",
        "internal policy",
        "guideline",
        "guidelines",
    ],
    "meeting_notes": [
        "meeting notes",
        "minutes",
        "meeting minute",
        "action points",
        "agenda",
    ],
}

PROGRAM_HINTS = [
    "integrity icon",
    "governance",
    "youth",
    "civic",
    "election",
    "accountability",
    "advocacy",
    "fundraising",
]

DONOR_HINTS = [
    "usaid",
    "unicef",
    "un women",
    "european union",
    "european commission",
    "ned",
    "dfat",
    "fcdo",
    "giz",
    "ford foundation",
    "oak foundation",
    "open society",
]

YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")


@dataclass
class DocumentMetadata:
    title: str
    document_type: str
    year: Optional[int]
    program_name: Optional[str]
    donor_name: Optional[str]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def classify_document_type(text: str, filename: str, provided_type: Optional[str] = None) -> str:
    if provided_type and provided_type in DOCUMENT_TYPES:
        return provided_type

    haystack = _normalize_text(f"{filename} {text[:4000]}")
    for document_type, keywords in DOCUMENT_TYPE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return document_type

    return "general"


def infer_title(filename: str, text: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    if stem:
        return stem.title()

    first_line = text.strip().splitlines()[0] if text.strip().splitlines() else ""
    if first_line:
        return first_line[:120].strip()

    return "Untitled Document"


def infer_year(text: str, filename: str) -> Optional[int]:
    matches = YEAR_PATTERN.findall(f"{filename} {text[:2500]}")
    if not matches:
        return None

    years = [int(year) for year in matches]
    return max(years) if years else None


def infer_program_name(text: str, filename: str) -> Optional[str]:
    haystack = _normalize_text(f"{filename} {text[:3000]}")
    for hint in PROGRAM_HINTS:
        if hint in haystack:
            return hint.title()
    return None


def infer_donor_name(text: str, filename: str) -> Optional[str]:
    haystack = _normalize_text(f"{filename} {text[:3000]}")
    for hint in DONOR_HINTS:
        if hint in haystack:
            return hint.upper() if len(hint) <= 4 else hint.title()
    return None


def build_document_metadata(
    *,
    filename: str,
    text: str,
    document_type: Optional[str] = None,
    title: Optional[str] = None,
    year: Optional[int] = None,
    program_name: Optional[str] = None,
    donor_name: Optional[str] = None,
) -> DocumentMetadata:
    resolved_title = title.strip() if title and title.strip() else infer_title(filename, text)
    resolved_type = classify_document_type(text=text, filename=filename, provided_type=document_type)
    resolved_year = year if year is not None else infer_year(text=text, filename=filename)
    resolved_program = program_name.strip() if program_name and program_name.strip() else infer_program_name(text=text, filename=filename)
    resolved_donor = donor_name.strip() if donor_name and donor_name.strip() else infer_donor_name(text=text, filename=filename)

    return DocumentMetadata(
        title=resolved_title,
        document_type=resolved_type,
        year=resolved_year,
        program_name=resolved_program,
        donor_name=resolved_donor,
    )


def metadata_to_dict(metadata: DocumentMetadata) -> Dict[str, Any]:
    return {
        "title": metadata.title,
        "document_type": metadata.document_type,
        "year": metadata.year,
        "program_name": metadata.program_name,
        "donor_name": metadata.donor_name,
    }
