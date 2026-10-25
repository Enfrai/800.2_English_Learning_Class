"""Unit tests for flagging and reviewing Māori content (US-008).

Cases UT-44 to UT-47 from the Test Plan, section 4.6, the macron part of
UT-48 (NFR-10) for review labels, and the team decision of 23 Oct 2026 that
unreviewed Māori content is hidden from learners only.

Author: Pei Wu
Date: 25 Oct 2026
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from maori_review import (
    LessonNotFoundError,
    NotCoordinatorError,
    NotFlaggedError,
    ReviewValidationError,
    learner_visible_condition,
    record_review,
    reset_review_after_material_change,
    review_label,
    set_maori_content,
    visible_to_learners,
)
from models import lessons

NewLesson = Callable[..., UUID]
LessonRow = Callable[[UUID], dict[str, Any]]
ReviewLog = Callable[[UUID], list[dict[str, Any]]]

NOT_YET_REVIEWED = "Māori content – not yet reviewed"
REVIEW_DAY = date(2026, 10, 8)


@pytest.fixture
def review(
    db: Session, coordinator_id: UUID, today: date
) -> Callable[..., dict[str, Any]]:
    """Record a review as the coordinator, with values that pass by default."""

    def record(
        lesson_id: UUID,
        *,
        name: str | None = "Aroha",
        day: date | None = REVIEW_DAY,
        role: str = "coordinator",
    ) -> dict[str, Any]:
        return record_review(
            db,
            lesson_id,
            reviewer_name=name,
            review_date=day,
            recorded_by=coordinator_id,
            recorder_role=role,
            today=today,
        )

    return record


@pytest.fixture
def flagged_lesson(db: Session, new_lesson: NewLesson) -> UUID:
    lesson_id = new_lesson()
    set_maori_content(db, lesson_id, True)
    return lesson_id


# UT-44 (US-008 AC1)


def test_ticking_maori_content_marks_the_lesson_not_yet_reviewed(
    db: Session, new_lesson: NewLesson, lesson_row: LessonRow
) -> None:
    lesson_id = new_lesson()

    saved = set_maori_content(db, lesson_id, True)

    assert saved["has_maori_content"] is True
    assert saved["review_status"] == "pending"
    assert review_label(saved) == NOT_YET_REVIEWED
    assert lesson_row(lesson_id) == saved


def test_lesson_without_maori_content_has_no_label(
    new_lesson: NewLesson, lesson_row: LessonRow
) -> None:
    assert review_label(lesson_row(new_lesson())) is None


def test_ticking_again_keeps_the_review(
    db: Session, flagged_lesson: UUID, review: Callable[..., dict[str, Any]]
) -> None:
    reviewed = review(flagged_lesson)

    saved = set_maori_content(db, flagged_lesson, True)

    assert saved == reviewed


def test_unticking_clears_the_flag_and_the_review(
    db: Session, flagged_lesson: UUID, review: Callable[..., dict[str, Any]]
) -> None:
    review(flagged_lesson)

    saved = set_maori_content(db, flagged_lesson, False)

    assert saved["has_maori_content"] is False
    assert saved["review_status"] == "not_required"
    assert saved["reviewer_name"] is None
    assert saved["review_date"] is None
    assert saved["reviewed_by"] is None
    assert saved["reviewed_at"] is None
    assert review_label(saved) is None


def test_unticking_a_lesson_without_maori_content_changes_nothing(
    db: Session, new_lesson: NewLesson, lesson_row: LessonRow
) -> None:
    lesson_id = new_lesson()
    before = lesson_row(lesson_id)

    assert set_maori_content(db, lesson_id, False) == before


def test_unknown_or_deleted_lesson_is_reported(
    db: Session, new_lesson: NewLesson
) -> None:
    deleted = new_lesson(deleted_at=datetime.now(UTC))

    with pytest.raises(LessonNotFoundError):
        set_maori_content(db, uuid4(), True)
    with pytest.raises(LessonNotFoundError):
        set_maori_content(db, deleted, True)


# UT-45 (US-008 AC2)


def test_coordinator_review_changes_the_label_to_reviewed_by_name_and_date(
    flagged_lesson: UUID,
    review: Callable[..., dict[str, Any]],
    coordinator_id: UUID,
    review_log: ReviewLog,
) -> None:
    saved = review(flagged_lesson, name="  Aroha  ")

    assert saved["review_status"] == "reviewed"
    assert saved["reviewer_name"] == "Aroha"
    assert saved["review_date"] == REVIEW_DAY
    assert saved["reviewed_by"] == coordinator_id
    assert saved["reviewed_at"] is not None
    assert review_label(saved) == "Reviewed by Aroha, 8 Oct 2026"
    [entry] = review_log(flagged_lesson)
    assert entry["review_status"] == "reviewed"
    assert entry["reviewed_by"] == coordinator_id
    assert entry["comment"] == "Reviewed by Aroha, 8 Oct 2026"


def test_review_dated_today_is_accepted(
    flagged_lesson: UUID, review: Callable[..., dict[str, Any]], today: date
) -> None:
    assert review(flagged_lesson, day=today)["review_date"] == today


def test_reviewer_name_of_150_characters_is_accepted(
    flagged_lesson: UUID, review: Callable[..., dict[str, Any]]
) -> None:
    assert review(flagged_lesson, name="a" * 150)["reviewer_name"] == "a" * 150


# UT-46 (US-008 AC3)


@pytest.mark.parametrize(
    ("name", "days_from_today", "errors"),
    [
        ("", -17, {"reviewer_name": "Reviewer name is required"}),
        ("   ", -17, {"reviewer_name": "Reviewer name is required"}),
        (None, -17, {"reviewer_name": "Reviewer name is required"}),
        ("Aroha", 1, {"review_date": "Review date cannot be in the future"}),
        ("Aroha", None, {"review_date": "Review date is required"}),
        (
            "",
            5,
            {
                "reviewer_name": "Reviewer name is required",
                "review_date": "Review date cannot be in the future",
            },
        ),
        (
            "a" * 151,
            -17,
            {"reviewer_name": "Reviewer name must be 150 characters or fewer"},
        ),
    ],
)
def test_bad_review_is_refused_with_a_message_and_the_label_stays(
    flagged_lesson: UUID,
    review: Callable[..., dict[str, Any]],
    lesson_row: LessonRow,
    review_log: ReviewLog,
    today: date,
    name: str | None,
    days_from_today: int | None,
    errors: dict[str, str],
) -> None:
    before = lesson_row(flagged_lesson)
    day = None if days_from_today is None else today + timedelta(days=days_from_today)

    with pytest.raises(ReviewValidationError) as error:
        review(flagged_lesson, name=name, day=day)

    assert error.value.errors == errors
    assert lesson_row(flagged_lesson) == before
    assert review_label(before) == NOT_YET_REVIEWED
    assert review_log(flagged_lesson) == []


def test_teacher_cannot_record_a_review(
    flagged_lesson: UUID,
    review: Callable[..., dict[str, Any]],
    lesson_row: LessonRow,
) -> None:
    with pytest.raises(NotCoordinatorError) as error:
        review(flagged_lesson, role="teacher")

    assert str(error.value) == "You do not have permission"
    assert lesson_row(flagged_lesson)["review_status"] == "pending"


def test_lesson_without_maori_content_cannot_be_reviewed(
    new_lesson: NewLesson, review: Callable[..., dict[str, Any]]
) -> None:
    with pytest.raises(NotFlaggedError):
        review(new_lesson())


# UT-47 (US-008 AC4)


def test_changing_materials_returns_a_reviewed_lesson_to_not_yet_reviewed(
    db: Session,
    flagged_lesson: UUID,
    review: Callable[..., dict[str, Any]],
    review_log: ReviewLog,
) -> None:
    review(flagged_lesson)
    teacher_id = uuid4()

    saved = reset_review_after_material_change(db, flagged_lesson, teacher_id)

    assert saved["review_status"] == "pending"
    assert review_label(saved) == NOT_YET_REVIEWED
    assert saved["reviewer_name"] is None
    assert saved["review_date"] is None
    assert saved["reviewed_by"] is None
    entries = {
        (entry["review_status"], entry["reviewed_by"], entry["comment"])
        for entry in review_log(flagged_lesson)
    }
    assert ("pending", teacher_id, "Lesson materials changed") in entries
    assert len(entries) == 2


@pytest.mark.parametrize("flagged", [False, True])
def test_changing_materials_of_an_unreviewed_lesson_changes_nothing(
    db: Session,
    new_lesson: NewLesson,
    lesson_row: LessonRow,
    review_log: ReviewLog,
    flagged: bool,
) -> None:
    lesson_id = new_lesson()
    if flagged:
        set_maori_content(db, lesson_id, True)
    before = lesson_row(lesson_id)

    saved = reset_review_after_material_change(db, lesson_id, uuid4())

    assert saved == before
    assert review_log(lesson_id) == []


# UT-48 (NFR-10): macrons kept exactly


def test_reviewer_name_with_macrons_is_kept_exactly(
    flagged_lesson: UUID, review: Callable[..., dict[str, Any]]
) -> None:
    saved = review(flagged_lesson, name="Kiri Tāmaki-Ōtene")

    assert saved["reviewer_name"] == "Kiri Tāmaki-Ōtene"
    assert review_label(saved) == "Reviewed by Kiri Tāmaki-Ōtene, 8 Oct 2026"


# Hidden from learners only (team decision, 23 Oct 2026)


def test_only_unreviewed_maori_content_is_hidden_from_learners(
    db: Session, new_lesson: NewLesson, lesson_row: LessonRow
) -> None:
    lesson_ids = {
        "no Māori content": new_lesson(),
        "not yet reviewed": new_lesson(has_maori_content=True, review_status="pending"),
        "reviewed": new_lesson(has_maori_content=True, review_status="reviewed"),
        "rejected": new_lesson(has_maori_content=True, review_status="rejected"),
    }

    visible_in_sql = set(
        db.execute(
            select(lessons.c.id).where(
                lessons.c.id.in_(lesson_ids.values()), learner_visible_condition()
            )
        ).scalars()
    )

    assert visible_in_sql == {lesson_ids["no Māori content"], lesson_ids["reviewed"]}
    for case, lesson_id in lesson_ids.items():
        expected = lesson_id in visible_in_sql
        assert visible_to_learners(lesson_row(lesson_id)) is expected, case


def test_reviewed_lesson_without_a_reviewer_name_is_labelled_reviewed(
    new_lesson: NewLesson, lesson_row: LessonRow
) -> None:
    # Reviews recorded before US-008 added reviewer_name and review_date.
    lesson_id = new_lesson(has_maori_content=True, review_status="reviewed")

    assert review_label(lesson_row(lesson_id)) == "Reviewed"
