from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException


def _to_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().lower() for item in value.split(",") if item.strip()}


AUTH_ENABLED = _to_bool(os.getenv("ALN_AUTH_ENABLED", "true"), default=True)
ALLOWED_DOMAINS = _parse_csv(
    os.getenv("ALN_ALLOWED_EMAIL_DOMAINS", "accountabilitylab.org,accountabilitylabnepal.org")
)
ALLOWED_EMAILS = _parse_csv(os.getenv("ALN_ALLOWED_EMAILS", ""))
ACCESS_KEY = os.getenv("ALN_ACCESS_KEY", "").strip()


def _is_allowed_email(email: str) -> bool:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        return False

    if normalized in ALLOWED_EMAILS:
        return True

    domain = normalized.split("@", 1)[1]
    return domain in ALLOWED_DOMAINS


async def require_aln_member(
    x_aln_email: Optional[str] = Header(default=None, alias="X-ALN-Email"),
    x_aln_access_key: Optional[str] = Header(default=None, alias="X-ALN-Access-Key"),
) -> dict[str, str]:
    """Enforce ALN member-only API access using email domain and optional access key."""
    if not AUTH_ENABLED:
        return {"email": "auth-disabled"}

    if not x_aln_email or not _is_allowed_email(x_aln_email):
        raise HTTPException(status_code=403, detail="ALN member access required")

    if ACCESS_KEY and x_aln_access_key != ACCESS_KEY:
        raise HTTPException(status_code=401, detail="Invalid ALN access key")

    return {"email": x_aln_email.strip().lower()}
