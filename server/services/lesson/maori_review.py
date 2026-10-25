"""Flag lessons with Māori content and decide who may see them (US-008).

Decision (23 Oct 2026): a lesson flagged with Māori content that is not yet
reviewed is hidden from learners only. Teachers and coordinators still see,
edit and link it; the coordinator must see it to record the review.

Author: Pei Wu
Date: 25 Oct 2026
"""

from typing import Any
from uuid import UUID

from models import lessons
from sqlalchemy import ColumnElement, false, func, or_, select
from sqlalchemy.orm import Session

# lessons.review_status values used by US-008.
NOT_REQUIRED = "not_required"
NOT_YET_REVIEWED = "pending"
REVIEWED = "reviewed"

# Message catalogue, UI design document section 7. The dash is an en dash.
NOT_YET_REVIEWED_LABEL = "Māori content – not yet reviewed"


class LessonNotFoundError(Exception):
    """No lesson has the given id."""


def set_maori_content(db: Session, lesson_id: UUID, flagged: bool) -> dict[str, Any]:
    """Tick or untick "Contains Māori content" and return the lesson.

    Ticking marks the lesson "not yet reviewed" (US-008 AC1). Ticking a lesson
    that is already flagged keeps its review. Unticking clears the review,
    because a lesson without Māori content needs none. The caller owns the
    transaction and checks who may edit the lesson (US-006).

    Raises:
        LessonNotFoundError: no lesson has this id, or it was deleted.
    """
    current = (
        db.execute(
            select(lessons)
            .where(lessons.c.id == lesson_id, lessons.c.deleted_at.is_(None))
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if current is None:
        raise LessonNotFoundError("Lesson not found")
    if current["has_maori_content"] == flagged:
        return dict(current)
    if flagged:
        changes: dict[str, Any] = {
            "has_maori_content": True,
            "review_status": NOT_YET_REVIEWED,
        }
    else:
        changes = {
            "has_maori_content": False,
            "review_status": NOT_REQUIRED,
            "reviewed_by": None,
            "reviewed_at": None,
        }
    row = db.execute(
        lessons.update()
        .where(lessons.c.id == lesson_id)
        .values(**changes, updated_at=func.now())
        .returning(lessons)
    )
    return dict(row.mappings().one())


def needs_review(lesson: dict[str, Any]) -> bool:
    """Return whether the lesson has Māori content that is not yet reviewed."""
    return bool(lesson["has_maori_content"]) and lesson["review_status"] != REVIEWED


def review_label(lesson: dict[str, Any]) -> str | None:
    """Return the "not yet reviewed" label, or None when it does not apply.

    The "Reviewed by [name], [date]" label is added with recording reviews.
    """
    return NOT_YET_REVIEWED_LABEL if needs_review(lesson) else None


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
