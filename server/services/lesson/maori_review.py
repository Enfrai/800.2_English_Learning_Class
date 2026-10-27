"""Flag lessons with Māori content, record their review, and decide who may
see them (US-008).

Decision (23 Oct 2026): a lesson flagged with Māori content that is not yet
reviewed is hidden from learners only. Teachers and coordinators still see,
edit and link it; the coordinator must see it to record the review.

The reviewer is usually a Kaiārahi outside the system, so the coordinator
types their name. reviewed_by and reviewed_at record which coordinator entered
the review and when.

Author: Pei Wu
Date: 25 Oct 2026
"""

from datetime import date
from typing import Any
from uuid import UUID, uuid4

from models import lesson_review_logs, lessons
from sqlalchemy import ColumnElement, false, func, or_, select
from sqlalchemy.orm import Session

# lessons.review_status values used by US-008.
NOT_REQUIRED = "not_required"
NOT_YET_REVIEWED = "pending"
REVIEWED = "reviewed"

COORDINATOR = "coordinator"
MAX_REVIEWER_NAME_LENGTH = 150

# Message catalogue, UI design document section 7. The dash is an en dash.
NOT_YET_REVIEWED_LABEL = "Māori content – not yet reviewed"
NO_PERMISSION = "You do not have permission"
REVIEWER_NAME_REQUIRED = "Reviewer name is required"
REVIEWER_NAME_TOO_LONG = (
    f"Reviewer name must be {MAX_REVIEWER_NAME_LENGTH} characters or fewer"
)
REVIEW_DATE_REQUIRED = "Review date is required"
REVIEW_DATE_IN_FUTURE = "Review date cannot be in the future"
NOT_FLAGGED = "This lesson is not marked as containing Māori content"

REVIEW_FIELDS_CLEARED = {
    "reviewed_by": None,
    "reviewed_at": None,
    "reviewer_name": None,
    "review_date": None,
}


class MaoriReviewError(Exception):
    """Base class for review errors that are reported to the user."""


class LessonNotFoundError(MaoriReviewError):
    """No lesson has the given id."""


class NotCoordinatorError(MaoriReviewError):
    """Only a coordinator records a review (US-008 AC2, Test Plan UT-46)."""

    def __init__(self) -> None:
        """
        Initialize NotCoordinatorError and retain the supplied constructor state.
        """
        super().__init__(NO_PERMISSION)


class NotFlaggedError(MaoriReviewError):
    """The lesson is not marked as containing Māori content."""

    def __init__(self) -> None:
        """
        Initialize NotFlaggedError and retain the supplied constructor state.
        """
        super().__init__(NOT_FLAGGED)


class ReviewValidationError(MaoriReviewError):
    """The reviewer name or date breaks a rule. ``errors`` maps field to message."""

    def __init__(self, errors: dict[str, str]) -> None:
        """
        Initialize ReviewValidationError and retain the supplied constructor state.
        """
        super().__init__("; ".join(errors.values()))
        self.errors = errors


def _lock_lesson(db: Session, lesson_id: UUID) -> dict[str, Any]:
    """
    Lock and load a live lesson before a review-state change.
    """
    row = (
        db.execute(
            select(lessons)
            .where(lessons.c.id == lesson_id, lessons.c.deleted_at.is_(None))
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if row is None:
        raise LessonNotFoundError("Lesson not found")
    return dict(row)


def _update(db: Session, lesson_id: UUID, changes: dict[str, Any]) -> dict[str, Any]:
    """
    Update lesson review fields and return the refreshed row.
    """
    row = db.execute(
        lessons.update()
        .where(lessons.c.id == lesson_id)
        .values(**changes, updated_at=func.now())
        .returning(lessons)
    )
    return dict(row.mappings().one())


def _log(db: Session, lesson_id: UUID, status: str, by: UUID, comment: str) -> None:
    """
    Append a lesson-review transition to the review log.
    """
    db.execute(
        lesson_review_logs.insert().values(
            id=uuid4(),
            lesson_id=lesson_id,
            review_status=status,
            reviewed_by=by,
            comment=comment,
        )
    )


def set_maori_content(db: Session, lesson_id: UUID, flagged: bool) -> dict[str, Any]:
    """Tick or untick "Contains Māori content" and return the lesson.

    Ticking marks the lesson "not yet reviewed" (US-008 AC1). Ticking a lesson
    that is already flagged keeps its review. Unticking clears the review,
    because a lesson without Māori content needs none. The caller owns the
    transaction and checks who may edit the lesson (US-006).

    Raises:
        LessonNotFoundError: no lesson has this id, or it was deleted.
    """
    current = _lock_lesson(db, lesson_id)
    if current["has_maori_content"] == flagged:
        return current
    if flagged:
        changes = {"has_maori_content": True, "review_status": NOT_YET_REVIEWED}
    else:
        changes = {
            "has_maori_content": False,
            "review_status": NOT_REQUIRED,
            **REVIEW_FIELDS_CLEARED,
        }
    return _update(db, lesson_id, changes)


def check_review(
    reviewer_name: str | None, review_date: date | None, today: date
) -> tuple[str, date]:
    """Trim and check a review; return the name and date to store.

    Raises:
        ReviewValidationError: with every field that breaks a rule.
    """
    name = (reviewer_name or "").strip()
    errors: dict[str, str] = {}
    if not name:
        errors["reviewer_name"] = REVIEWER_NAME_REQUIRED
    elif len(name) > MAX_REVIEWER_NAME_LENGTH:
        errors["reviewer_name"] = REVIEWER_NAME_TOO_LONG
    if review_date is None:
        errors["review_date"] = REVIEW_DATE_REQUIRED
    elif review_date > today:
        errors["review_date"] = REVIEW_DATE_IN_FUTURE
    if errors:
        raise ReviewValidationError(errors)
    assert review_date is not None
    return name, review_date


def record_review(
    db: Session,
    lesson_id: UUID,
    *,
    reviewer_name: str | None,
    review_date: date | None,
    recorded_by: UUID,
    recorder_role: str,
    today: date,
) -> dict[str, Any]:
    """Record that the Māori content of a lesson was reviewed (US-008 AC2).

    ``today`` is the club's local date, given by the caller. The review is
    also added to lesson_review_logs. The caller owns the transaction.

    Raises:
        NotCoordinatorError: the person recording is not a coordinator.
        ReviewValidationError: the name is empty or too long, or the date is
            missing or in the future. Nothing changes (AC3).
        LessonNotFoundError: no lesson has this id, or it was deleted.
        NotFlaggedError: the lesson is not marked as containing Māori content.
    """
    if recorder_role != COORDINATOR:
        raise NotCoordinatorError()
    name, reviewed_on = check_review(reviewer_name, review_date, today)
    current = _lock_lesson(db, lesson_id)
    if not current["has_maori_content"]:
        raise NotFlaggedError()
    saved = _update(
        db,
        lesson_id,
        {
            "review_status": REVIEWED,
            "reviewer_name": name,
            "review_date": reviewed_on,
            "reviewed_by": recorded_by,
            "reviewed_at": func.now(),
        },
    )
    _log(db, lesson_id, REVIEWED, recorded_by, review_label(saved) or "")
    return saved


def reset_review_after_material_change(
    db: Session, lesson_id: UUID, changed_by: UUID
) -> dict[str, Any]:
    """Return a reviewed lesson to "not yet reviewed" (US-008 AC4).

    Call this when a file of the lesson is added, replaced or removed (US-006).
    A lesson that is not reviewed is returned unchanged. The reset is logged.
    The caller owns the transaction.

    Raises:
        LessonNotFoundError: no lesson has this id, or it was deleted.
    """
    current = _lock_lesson(db, lesson_id)
    if not current["has_maori_content"] or current["review_status"] != REVIEWED:
        return current
    saved = _update(
        db,
        lesson_id,
        {"review_status": NOT_YET_REVIEWED, **REVIEW_FIELDS_CLEARED},
    )
    _log(db, lesson_id, NOT_YET_REVIEWED, changed_by, "Lesson materials changed")
    return saved


def needs_review(lesson: dict[str, Any]) -> bool:
    """Return whether the lesson has Māori content that is not yet reviewed."""
    return bool(lesson["has_maori_content"]) and lesson["review_status"] != REVIEWED


def format_review_date(day: date) -> str:
    """Format a date like the UI design document, e.g. "8 Oct 2026"."""
    return f"{day.day} {day:%b %Y}"


def review_label(lesson: dict[str, Any]) -> str | None:
    """Return the review label of a lesson, or None when it has none.

    "Māori content – not yet reviewed" or "Reviewed by [name], [date]".
    """
    if not lesson["has_maori_content"]:
        return None
    if needs_review(lesson):
        return NOT_YET_REVIEWED_LABEL
    name, day = lesson.get("reviewer_name"), lesson.get("review_date")
    if not name or day is None:
        return "Reviewed"
    return f"Reviewed by {name}, {format_review_date(day)}"


def visible_to_learners(lesson: dict[str, Any]) -> bool:
    """Return whether learners may see the lesson (hidden while not reviewed)."""
    return not needs_review(lesson)


def learner_visible_condition() -> ColumnElement[bool]:
    """SQL condition for lessons learners may see, for queries in US-013.

    Matches visible_to_learners(): no Māori content, or reviewed.
    """
    return or_(
        lessons.c.has_maori_content == false(), lessons.c.review_status == REVIEWED
    )
