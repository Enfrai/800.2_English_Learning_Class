"""Correct the attendance of a past class, with a change log (US-015).

Only a coordinator corrects, and only classes before the club's today; during
the class itself anyone on staff ticks and unticks (US-004). Team decisions
(25 Oct 2026): unticking a learner here sets the record to absent instead of
deleting it, because each change-log entry points at its record; a learner
with no record gets a new present record, logged as absent -> present.

Author: Pei Wu
Date: 25 Oct 2026
"""

from datetime import date
from typing import Any
from uuid import UUID, uuid4

from attendance import PRESENT, SessionNotFoundError
from models import attendance_audits, attendance_records, class_sessions
from sqlalchemy import func, select
from sqlalchemy.orm import Session

ABSENT = "absent"
COORDINATOR = "coordinator"

# Message catalogue, UI design document section 7.
NO_PERMISSION = "You do not have permission"
# Not in the catalogue; to be agreed with the team.
SESSION_NOT_PAST = "This class is today. Change it on the class list"


class CorrectionError(Exception):
    """Base class for correction errors that are reported to the user."""


class NotCoordinatorError(CorrectionError):
    """Only a coordinator corrects past attendance (US-015 AC3)."""

    def __init__(self) -> None:
        super().__init__(NO_PERMISSION)


class SessionNotPastError(CorrectionError):
    """The class is today or later; it is changed on its list (US-004)."""

    def __init__(self) -> None:
        super().__init__(SESSION_NOT_PAST)


def _session_date(db: Session, session_id: UUID) -> date:
    session_date = db.execute(
        select(class_sessions.c.session_date).where(class_sessions.c.id == session_id)
    ).scalar_one_or_none()
    if session_date is None:
        raise SessionNotFoundError("Class session not found")
    return session_date


def correct_attendance(
    db: Session,
    *,
    session_id: UUID,
    learner_id: UUID,
    present: bool,
    corrected_by: UUID,
    corrector_role: str,
    today: date,
    reason: str | None = None,
) -> dict[str, Any] | None:
    """Mark a learner present or not present at a past class, and log it.

    Returns the learner's record after the change, or None when the learner
    had no record and stays not present. If the record already has the
    wanted status, nothing changes and nothing is logged. ``today`` is the
    club's local date. The caller owns the transaction.

    Raises:
        NotCoordinatorError: the person correcting is not a coordinator.
        SessionNotFoundError: no session has this id.
        SessionNotPastError: the class is today or later.
    """
    if corrector_role != COORDINATOR:
        raise NotCoordinatorError()
    if _session_date(db, session_id) >= today:
        raise SessionNotPastError()

    current = (
        db.execute(
            select(attendance_records)
            .where(
                attendance_records.c.session_id == session_id,
                attendance_records.c.learner_id == learner_id,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    old_status = current["status"] if current else ABSENT
    new_status = PRESENT if present else ABSENT
    if old_status == new_status:
        return dict(current) if current else None

    # clock_timestamp() rather than now(): changes made in one transaction
    # still get distinct times, so the history keeps its order (UT-34).
    changed_at = func.clock_timestamp()
    if current is None:
        record = (
            db.execute(
                attendance_records.insert()
                .values(
                    id=uuid4(),
                    session_id=session_id,
                    learner_id=learner_id,
                    status=new_status,
                    recorded_by=corrected_by,
                    recorded_at=changed_at,
                    corrected_by=corrected_by,
                    corrected_at=changed_at,
                )
                .returning(attendance_records)
            )
            .mappings()
            .one()
        )
    else:
        record = (
            db.execute(
                attendance_records.update()
                .where(attendance_records.c.id == current["id"])
                .values(
                    status=new_status,
                    corrected_by=corrected_by,
                    corrected_at=changed_at,
                )
                .returning(attendance_records)
            )
            .mappings()
            .one()
        )
    db.execute(
        attendance_audits.insert().values(
            id=uuid4(),
            attendance_id=record["id"],
            old_status=old_status,
            new_status=new_status,
            corrected_by=corrected_by,
            reason=(reason or "").strip() or None,
            created_at=changed_at,
        )
    )
    return dict(record)


def change_history(db: Session, session_id: UUID) -> list[dict[str, Any]]:
    """Return every correction of a class, oldest first (US-015 AC4).

    Each entry has the learner, the old and new status, who changed it and
    when. A class with no corrections gives an empty list.

    Raises:
        SessionNotFoundError: no session has this id.
    """
    _session_date(db, session_id)
    rows = db.execute(
        select(
            attendance_audits.c.id,
            attendance_records.c.learner_id,
            attendance_audits.c.old_status,
            attendance_audits.c.new_status,
            attendance_audits.c.corrected_by,
            attendance_audits.c.reason,
            attendance_audits.c.created_at,
        )
        .join(
            attendance_records,
            attendance_records.c.id == attendance_audits.c.attendance_id,
        )
        .where(attendance_records.c.session_id == session_id)
        .order_by(attendance_audits.c.created_at, attendance_audits.c.id)
    ).mappings()
    return [dict(row) for row in rows]


def corrected_learners(db: Session, session_id: UUID) -> list[UUID]:
    """Return the learners whose attendance at a class was corrected.

    Includes learners corrected to not present, so the list can mark every
    changed learner "Corrected" (UI design document 6.16).
    """
    return list(
        db.execute(
            select(attendance_records.c.learner_id)
            .where(
                attendance_records.c.session_id == session_id,
                attendance_records.c.corrected_at.is_not(None),
            )
            .order_by(attendance_records.c.learner_id)
        ).scalars()
    )
