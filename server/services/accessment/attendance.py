"""Attendance during a class: mark present and unmark (US-004).

Author: Pei Wu
Date: 23 Oct 2026
"""

from datetime import date
from typing import Any
from uuid import UUID

from models import attendance_records, class_sessions
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

PRESENT = "present"

# Message catalogue, UI design document section 7.
ALREADY_SIGNED_IN = "Already signed in"
PAST_ATTENDANCE_LOCKED = "Only a coordinator can correct past attendance"


class AttendanceError(Exception):
    """Base class for attendance errors that are reported to the user."""


class SessionNotFoundError(AttendanceError):
    """No class session has the given id."""


class PastSessionError(AttendanceError):
    """The session is before today. Changes go through a correction (US-015)."""

    def __init__(self) -> None:
        super().__init__(PAST_ATTENDANCE_LOCKED)


class AlreadySignedInError(AttendanceError):
    """The learner is already marked present. No second record is made."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(ALREADY_SIGNED_IN)
        self.record = record


class NotMarkedPresentError(AttendanceError):
    """There is no present record to remove."""


def check_session_is_running(db: Session, session_id: UUID, today: date) -> None:
    """Check that attendance at this session can still be changed.

    Raises:
        SessionNotFoundError: no session has this id.
        PastSessionError: the session is before ``today``.
    """
    session_date = db.execute(
        select(class_sessions.c.session_date).where(class_sessions.c.id == session_id)
    ).scalar_one_or_none()
    if session_date is None:
        raise SessionNotFoundError("Class session not found")
    if session_date < today:
        raise PastSessionError()


def mark_present(
    db: Session,
    *,
    session_id: UUID,
    learner_id: UUID,
    recorded_by: UUID,
    today: date,
) -> dict[str, Any]:
    """Mark a learner present and return the record, including its time.

    ``today`` is the club's local date, given by the caller. The caller owns
    the transaction and commits it.

    Raises:
        SessionNotFoundError: no session has this id.
        PastSessionError: the session is before ``today``.
        AlreadySignedInError: the learner is already present. Nothing changes.
    """
    check_session_is_running(db, session_id, today)
    # The unique (session_id, learner_id) constraint also stops a duplicate
    # when two teachers tick the same learner at the same moment.
    inserted = (
        db.execute(
            insert(attendance_records)
            .values(
                session_id=session_id,
                learner_id=learner_id,
                status=PRESENT,
                recorded_by=recorded_by,
            )
            .on_conflict_do_nothing(index_elements=["session_id", "learner_id"])
            .returning(attendance_records)
        )
        .mappings()
        .first()
    )
    if inserted is not None:
        return dict(inserted)

    existing = (
        db.execute(
            select(attendance_records).where(
                attendance_records.c.session_id == session_id,
                attendance_records.c.learner_id == learner_id,
            )
        )
        .mappings()
        .one()
    )
    if existing["status"] == PRESENT:
        raise AlreadySignedInError(dict(existing))
    # An absent record for a running class becomes present.
    updated = (
        db.execute(
            attendance_records.update()
            .where(attendance_records.c.id == existing["id"])
            .values(status=PRESENT, recorded_by=recorded_by, recorded_at=func.now())
            .returning(attendance_records)
        )
        .mappings()
        .one()
    )
    return dict(updated)


def unmark(db: Session, *, session_id: UUID, learner_id: UUID, today: date) -> None:
    """Remove a learner's present record, for a learner ticked by mistake.

    The caller owns the transaction and commits it.

    Raises:
        SessionNotFoundError: no session has this id.
        PastSessionError: the session is before ``today``.
        NotMarkedPresentError: the learner is not marked present.
    """
    check_session_is_running(db, session_id, today)
    removed = db.execute(
        attendance_records.delete()
        .where(
            attendance_records.c.session_id == session_id,
            attendance_records.c.learner_id == learner_id,
            attendance_records.c.status == PRESENT,
        )
        .returning(attendance_records.c.id)
    ).first()
    if removed is None:
        raise NotMarkedPresentError("Learner is not marked present")


def present_count(db: Session, session_id: UUID) -> int:
    """Return how many learners are marked present at a session."""
    return db.execute(
        select(func.count())
        .select_from(attendance_records)
        .where(
            attendance_records.c.session_id == session_id,
            attendance_records.c.status == PRESENT,
        )
    ).scalar_one()


def present_records(db: Session, session_id: UUID) -> list[dict[str, Any]]:
    """Return the present records of a session, earliest first."""
    return [
        dict(row)
        for row in db.execute(
            select(attendance_records)
            .where(
                attendance_records.c.session_id == session_id,
                attendance_records.c.status == PRESENT,
            )
            .order_by(attendance_records.c.recorded_at)
        ).mappings()
    ]
