from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserProfile(BaseModel):
    id: int
    name: str
    email: str


class AuthResponse(BaseModel):
    token: str
    user: UserProfile


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_b64, digest_b64 = stored_hash.split("$", 1)
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(digest_b64.encode())
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(actual, expected)


def _generate_token() -> str:
    return secrets.token_urlsafe(40)


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    token = authorization[len(prefix):].strip()
    return token or None


def get_current_user_optional(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    token = _extract_bearer_token(authorization)
    if not token:
        return None

    session = db.query(models.UserSession).filter(models.UserSession.token == token).first()
    if not session:
        return None

    return db.query(models.User).filter(models.User.id == session.user_id).first()


def get_current_user(
    user: Optional[models.User] = Depends(get_current_user_optional),
) -> models.User:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.post("/register", response_model=AuthResponse)
async def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    existing = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        name=payload.name.strip(),
        email=payload.email.lower(),
        password_hash=_hash_password(payload.password),
    )
    db.add(user)
    db.flush()

    token = _generate_token()
    user_session = models.UserSession(user_id=user.id, token=token)
    db.add(user_session)
    db.commit()
    db.refresh(user)

    return AuthResponse(
        token=token,
        user=UserProfile(id=user.id, name=user.name, email=user.email),
    )


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _generate_token()
    user_session = models.UserSession(user_id=user.id, token=token)
    db.add(user_session)
    db.commit()

    return AuthResponse(
        token=token,
        user=UserProfile(id=user.id, name=user.name, email=user.email),
    )


@router.get("/me", response_model=UserProfile)
async def me(current_user: models.User = Depends(get_current_user)) -> UserProfile:
    return UserProfile(id=current_user.id, name=current_user.name, email=current_user.email)


@router.post("/logout")
async def logout(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    token = _extract_bearer_token(authorization)
    if token:
        db.query(models.UserSession).filter(models.UserSession.token == token).delete()
        db.commit()
    return {"message": "Logged out"}
