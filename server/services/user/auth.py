"""Read-only session authentication and database-backed role dependencies."""

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import user_sessions, users
from security import SAFE_METHODS, SESSION_COOKIE, require_same_origin

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: UUID
    display_name: str
    role: str
    expires_at: datetime


def get_db(request: Request) -> Iterator[Session]:
    """Use the owning application's session factory; never create tables here."""
    with request.app.state.session_factory() as db:
        yield db


def authenticate_session(token: str, db: Session) -> AuthenticatedUser:
    """Validate without refreshing expiry or writing any session fields.

    A request already authenticated when revocation commits may finish. Subsequent
    validations fail. This read-only operation cannot resurrect a revoked session.
    """
    if not token or len(token) > 512:
        raise unauthenticated()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(UTC)
    row = (
        db.execute(
            select(
                users.c.id,
                users.c.display_name,
                users.c.role,
                user_sessions.c.expires_at,
            )
            .select_from(
                user_sessions.join(users, user_sessions.c.user_id == users.c.id)
            )
            .where(
                user_sessions.c.token_hash == token_hash,
                user_sessions.c.revoked_at.is_(None),
                user_sessions.c.expires_at > now,
                user_sessions.c.last_activity_at > now - timedelta(minutes=30),
                users.c.is_active.is_(True),
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise unauthenticated()
    return AuthenticatedUser(
        row["id"], row["display_name"], row["role"], row["expires_at"]
    )


def unauthenticated() -> HTTPException:
    """
    Construct the standard unauthenticated-session HTTP exception.
    """
    return HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_session_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    # An explicit malformed Authorization header never falls back to a cookie.
    """
    Extract one unambiguous session credential and enforce mutation origin checks.
    """
    authorization = request.headers.getlist("authorization")
    if authorization and (len(authorization) != 1 or credentials is None):
        raise unauthenticated()
    cookie_values = [
        item.partition("=")[2].strip()
        for header in request.headers.getlist("cookie")
        for item in header.split(";")
        if item.partition("=")[0].strip() == SESSION_COOKIE
    ]
    if len(cookie_values) > 1:
        raise unauthenticated()
    cookie_token = request.cookies.get(SESSION_COOKIE)
    bearer_token = credentials.credentials if credentials else None
    if (
        cookie_token is not None
        and bearer_token is not None
        and cookie_token != bearer_token
    ):
        raise unauthenticated()
    token = bearer_token if bearer_token is not None else cookie_token
    if not token:
        raise unauthenticated()
    if cookie_token is not None and request.method not in SAFE_METHODS:
        require_same_origin(request, required=True)
    if len(token) > 512:
        raise unauthenticated()
    return token


def get_current_user(
    token: Annotated[str, Depends(get_session_token)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthenticatedUser:
    """
    Resolve a live staff identity from the presented token and database session.
    """
    return authenticate_session(token, db)


def require_coordinator(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """
    Reject staff identities that do not have the Coordinator role.
    """
    if user.role != "coordinator":
        raise HTTPException(status_code=403, detail="You do not have permission")
    return user


def require_teacher(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """
    Reject staff identities that do not have the Teacher role.
    """
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="You do not have permission")
    return user
