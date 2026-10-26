"""Validate QR check-in windows again under the classroom lock before sign-in.

US-011 opens a check-in window for a class session and puts a long random
token in the QR code link. Only the token's SHA-256 hash is stored, the same
way the User Service stores session tokens, so the database never holds the
token itself.

Author: Pei Wu
Date: 25 Oct 2026
Updated: Shuohui Liu, 26 Oct 2026
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from attendance import check_session_is_running, mark_present
from models import checkin_windows, class_sessions, signin_failures
from sqlalchemy import select
from sqlalchemy.orm import Session

# Random or HMAC-derived 256-bit URL-safe tokens are 43 characters. Anything far
# longer is not a token, so it is refused before hashing or querying.
MAX_TOKEN_LENGTH = 256

# Message catalogue, UI design document section 7. The learner sees the same
# message for every reason, so a guessed token reveals nothing.
CHECKIN_CLOSED = "Check-in is closed. Please ask the teacher"
SIGNED_IN = "You are signed in"
# Also shown when several learners share the name: the teacher ticks the right
# one (team decision, 25 Oct 2026). It never reveals that the name exists.
NAME_NOT_FOUND = "We could not find that name. Please ask the teacher"
# Not in the message catalogue yet; to be agreed with the team.
TOO_MANY_TRIES = "Too many tries. Please ask the teacher"

# NFR-11: more than 10 wrong names from one device in 10 minutes blocks it
# for 10 minutes (Test Plan UT-67). Phones on the library Wi-Fi share one
# address, so a device is told apart by a random id from the sign-in page;
# the address has a much higher limit, so changing the id does not help.
MAX_WRONG_NAMES = 10
MAX_WRONG_NAMES_PER_ADDRESS = 50
WRONG_NAME_PERIOD = timedelta(minutes=10)
BLOCK_TIME = timedelta(minutes=10)
KEEP_FAILURES = timedelta(hours=1)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def hash_token(token: str) -> str:
    """Return the hash stored in checkin_windows.token_hash."""
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class OpenCheckin:
    window_id: UUID
    session_id: UUID
    session_date: date
    expires_at: datetime
    # The teacher who opened check-in. Self sign-ins are recorded under them,
    # because attendance_records.recorded_by holds a staff id (25 Oct 2026).
    opened_by: UUID


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
    """The class session is not dated today."""

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
                checkin_windows.c.opened_by,
                class_sessions.c.session_date,
                class_sessions.c.status.label("class_status"),
            )
            .join(class_sessions, class_sessions.c.id == checkin_windows.c.session_id)
            .where(checkin_windows.c.token_hash == hash_token(token))
        )
        .mappings()
        .first()
    )
    if row is None:
        raise UnknownCheckinTokenError()
    if row["class_status"] == "closed" or (
        row["closed_at"] is not None and aware(row["closed_at"]) <= now
    ):
        raise CheckinClosedError()
    if aware(row["expires_at"]) <= now:
        raise CheckinExpiredError()
    if row["session_date"] != today:
        raise CheckinSessionPastError()
    return OpenCheckin(
        window_id=row["id"],
        session_id=row["session_id"],
        session_date=row["session_date"],
        expires_at=aware(row["expires_at"]),
        opened_by=row["opened_by"],
    )


def sign_in(
    db: Session,
    checkin: OpenCheckin,
    learner_id: UUID,
    today: date,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Mark the learner present at the check-in's class (US-012 AC2).

    Uses the same rule as a teacher's tick (US-004), so a second sign-in
    raises AlreadySignedInError and no duplicate is made (AC4). Only the
    learner, the class and the time are stored: no location or device detail
    (Test Plan UT-66). The caller owns the transaction.
    """
    # Opening, closing, deletion and sign-in all acquire this class row first.
    check_session_is_running(db, checkin.session_id, today)
    current = (
        db.execute(
            select(checkin_windows).where(
                checkin_windows.c.id == checkin.window_id,
                checkin_windows.c.session_id == checkin.session_id,
            )
        )
        .mappings()
        .first()
    )
    instant = now or datetime.now(UTC)
    if current is None:
        raise UnknownCheckinTokenError()
    if current["closed_at"] is not None:
        raise CheckinClosedError()
    if aware(current["expires_at"]) <= instant:
        raise CheckinExpiredError()
    class_row = db.execute(
        select(class_sessions.c.session_date, class_sessions.c.status).where(
            class_sessions.c.id == checkin.session_id
        )
    ).one()
    if class_row.session_date != today or class_row.status == "closed":
        raise CheckinClosedError()
    return mark_present(
        db,
        session_id=checkin.session_id,
        learner_id=learner_id,
        recorded_by=checkin.opened_by,
        today=today,
    )


def device_key(value: str, secret: str) -> str:
    """Return a keyed hash of an address or device id; the value is not kept."""
    return hmac.new(secret.encode(), value.encode(), "sha256").hexdigest()


def wrong_name_limits(
    client_address: str | None, device_id: str | None, secret: str
) -> list[tuple[str, int]]:
    """Return the (key, limit) pairs a sign-in attempt is counted against.

    A valid device id from the sign-in page gets its own limit of 10, and
    the address gets 50. Without a valid id the address gets the limit of 10.
    """
    address_key = device_key(f"address:{client_address or 'unknown'}", secret)
    try:
        device = UUID(device_id or "")
    except ValueError:
        return [(address_key, MAX_WRONG_NAMES)]
    return [
        (device_key(f"device:{device}", secret), MAX_WRONG_NAMES),
        (address_key, MAX_WRONG_NAMES_PER_ADDRESS),
    ]


def blocked_until(
    db: Session, key: str, now: datetime, limit: int = MAX_WRONG_NAMES
) -> datetime | None:
    """Return when the key may try again, or None if it is not blocked.

    A key is blocked for BLOCK_TIME after ``limit`` wrong names within
    WRONG_NAME_PERIOD.
    """
    times = sorted(
        aware(value)
        for value in db.execute(
            select(signin_failures.c.failed_at).where(
                signin_failures.c.key_hash == key,
                signin_failures.c.failed_at > now - WRONG_NAME_PERIOD - BLOCK_TIME,
            )
        ).scalars()
    )
    until = None
    for first in range(len(times) - limit + 1):
        last = times[first + limit - 1]
        if last - times[first] <= WRONG_NAME_PERIOD and last + BLOCK_TIME > now:
            until = max(until or last + BLOCK_TIME, last + BLOCK_TIME)
    return until


def record_wrong_name(db: Session, key: str, now: datetime) -> None:
    """Count a wrong name for the device and forget counts over an hour old.

    The caller owns the transaction.
    """
    db.execute(signin_failures.insert().values(id=uuid4(), key_hash=key, failed_at=now))
    db.execute(
        signin_failures.delete().where(
            signin_failures.c.failed_at < now - KEEP_FAILURES
        )
    )
