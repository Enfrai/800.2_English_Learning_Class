"""Check a QR check-in token before a learner signs in (US-012).

US-011 opens a check-in window for a class session and puts a long random
token in the QR code link. Only the token's SHA-256 hash is stored, the same
way the User Service stores session tokens, so the database never holds the
token itself.

Author: Pei Wu
Date: 25 Oct 2026
"""

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from models import checkin_windows, class_sessions
from sqlalchemy import select
from sqlalchemy.orm import Session

# Tokens from secrets.token_urlsafe(32) are 43 characters. Anything far
# longer is not a token, so it is refused before hashing or querying.
MAX_TOKEN_LENGTH = 256

# Message catalogue, UI design document section 7. The learner sees the same
# message for every reason, so a guessed token reveals nothing.
CHECKIN_CLOSED = "Check-in is closed. Please ask the teacher"


def hash_token(token: str) -> str:
    """Return the hash stored in checkin_windows.token_hash."""
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class OpenCheckin:
    window_id: UUID
    session_id: UUID
    session_date: date
    expires_at: datetime


class CheckinUnavailableError(Exception):
    """Check-in cannot be used. ``reason`` says why, for tests and logs."""

    reason = "unavailable"

    def __init__(self) -> None:
        super().__init__(CHECKIN_CLOSED)


class UnknownCheckinTokenError(CheckinUnavailableError):
    """No check-in window has this token."""

    reason = "unknown token"


class CheckinClosedError(CheckinUnavailableError):
    """The teacher closed check-in (US-011 AC4)."""

    reason = "closed"


class CheckinExpiredError(CheckinUnavailableError):
    """Check-in has passed its expiry, at most four hours after opening."""

    reason = "expired"


class CheckinSessionPastError(CheckinUnavailableError):
    """The class session is dated before today."""

    reason = "session before today"


def find_open_checkin(
    db: Session, token: str | None, *, now: datetime, today: date
) -> OpenCheckin:
    """Return the open check-in window and class for a QR token.

    ``now`` is a timezone-aware time and ``today`` the club's local date,
    both given by the caller.

    Raises:
        UnknownCheckinTokenError: the token is empty, too long or unknown.
        CheckinClosedError: the teacher closed check-in.
        CheckinExpiredError: the window has expired.
        CheckinSessionPastError: the class session is before today.
    """
    if not token or len(token) > MAX_TOKEN_LENGTH:
        raise UnknownCheckinTokenError()
    row = (
        db.execute(
            select(
                checkin_windows.c.id,
                checkin_windows.c.session_id,
                checkin_windows.c.expires_at,
                checkin_windows.c.closed_at,
                class_sessions.c.session_date,
            )
            .join(class_sessions, class_sessions.c.id == checkin_windows.c.session_id)
            .where(checkin_windows.c.token_hash == hash_token(token))
        )
        .mappings()
        .first()
    )
    if row is None:
        raise UnknownCheckinTokenError()
    if row["closed_at"] is not None and row["closed_at"] <= now:
        raise CheckinClosedError()
    if row["expires_at"] <= now:
        raise CheckinExpiredError()
    if row["session_date"] < today:
        raise CheckinSessionPastError()
    return OpenCheckin(
        window_id=row["id"],
        session_id=row["session_id"],
        session_date=row["session_date"],
        expires_at=row["expires_at"],
    )
