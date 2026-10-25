"""Unit tests for lessons (US-006).

Cases UT-39, UT-42, UT-43 and UT-70 from the Test Plan, section 4.6, plus the
tag list and NFR-10 (macrons). File rules (UT-40) are in test_files.py and
the download (UT-41) in test_api.py.

Author: Sandhya Tiwari
Date: 23 Oct 2026
"""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lessons import (
    DATE_REQUIRED,
    NO_PERMISSION,
    TAG_REQUIRED,
    TAG_UNKNOWN,
    TITLE_REQUIRED,
    TITLE_TOO_LONG,
    TOPIC_TAGS,
    LessonNotFoundError,
    LessonPermissionError,
    LessonValidationError,
    add_lesson,
    add_material,
    delete_lesson,
    get_lesson,
    get_material,
    list_lessons,
    list_tags,
    seed_tags,
    update_lesson,
)
from models import lessons, tags
from user_client import Staff

LESSON_DATE = date(2026, 10, 21)


def save(db: Session, author: Staff, **changes) -> dict:
    values = {
        "title": "Catching the bus",
        "lesson_date": LESSON_DATE,
        "tag_names": ["Transport"],
    }
    values.update(changes)
    return add_lesson(db, created_by=author.id, **values)


def attach(
    db: Session, lesson_id, staff: Staff, name: str = "bus timetable.pdf"
) -> dict:
    return add_material(
        db,
        lesson_id,
        file_name=name,
        storage_key=uuid4().hex,
        mime_type="application/pdf",
        file_size=2048,
        share_with_learners=False,
        staff=staff,
    )


def lesson_count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(lessons)).scalar_one()


# Tag list (confirmed 23 Oct 2026)


def test_the_seven_agreed_tags_are_loaded_in_order(db: Session) -> None:
    assert list_tags(db) == list(TOPIC_TAGS)
    assert TOPIC_TAGS == (
        "Transport",
        "Health",
        "Shopping",
        "Culture",
        "History",
        "Accommodation",
        "Lifestyle",
    )


def test_loading_the_tags_again_adds_no_copies(db: Session) -> None:
    seed_tags(db)
    seed_tags(db)

    assert db.execute(select(func.count()).select_from(tags)).scalar_one() == 7


# UT-70 / AC1: save with title, date and one tag; it is listed


def test_saved_lesson_is_listed_with_its_date_and_tags(
    db: Session, teacher: Staff
) -> None:
    saved = save(db, teacher, tag_names=["Health", "Transport"])

    listed = [lesson for lesson in list_lessons(db) if lesson["id"] == saved["id"]]

    assert len(listed) == 1
    assert listed[0]["title"] == "Catching the bus"
    assert listed[0]["lesson_date"] == LESSON_DATE
    # Shown in the agreed tag order, whatever order they were chosen in.
    assert listed[0]["tags"] == ["Transport", "Health"]
    assert listed[0]["created_by"] == teacher.id


def test_list_shows_newest_lesson_date_first(db: Session, teacher: Staff) -> None:
    older = save(db, teacher, title="Older", lesson_date=date(2026, 9, 1))
    newer = save(db, teacher, title="Newer", lesson_date=date(2026, 10, 1))

    ids = [lesson["id"] for lesson in list_lessons(db)]

    assert ids.index(newer["id"]) < ids.index(older["id"])


def test_title_with_a_macron_is_stored_exactly_as_typed(
    db: Session, teacher: Staff
) -> None:
    saved = save(db, teacher, title="Te reo Māori")

    assert get_lesson(db, saved["id"])["title"] == "Te reo Māori"


def test_spaces_around_the_title_are_removed(db: Session, teacher: Staff) -> None:
    saved = save(db, teacher, title="  Doctor visits  ")

    assert saved["title"] == "Doctor visits"


# UT-39 / AC2: empty title, no date, no tag


@pytest.mark.parametrize("title", ["", "   ", None])
def test_empty_title_is_refused_and_nothing_is_saved(
    db: Session, teacher: Staff, title: str | None
) -> None:
    before = lesson_count(db)

    with pytest.raises(LessonValidationError) as error:
        save(db, teacher, title=title)

    assert (error.value.field, error.value.message) == ("title", TITLE_REQUIRED)
    assert error.value.message == "Title is required"
    assert lesson_count(db) == before


def test_title_over_255_characters_is_refused(db: Session, teacher: Staff) -> None:
    with pytest.raises(LessonValidationError) as error:
        save(db, teacher, title="a" * 256)

    assert error.value.message == TITLE_TOO_LONG


def test_title_of_255_characters_is_accepted(db: Session, teacher: Staff) -> None:
    assert save(db, teacher, title="a" * 255)["title"] == "a" * 255


def test_missing_date_is_refused(db: Session, teacher: Staff) -> None:
    before = lesson_count(db)

    with pytest.raises(LessonValidationError) as error:
        save(db, teacher, lesson_date=None)

    assert (error.value.field, error.value.message) == ("lesson_date", DATE_REQUIRED)
    assert error.value.message == "Lesson date is required"
    assert lesson_count(db) == before


@pytest.mark.parametrize("tag_names", [[], None, ["  "]])
def test_lesson_without_a_tag_is_refused(
    db: Session, teacher: Staff, tag_names: list[str] | None
) -> None:
    with pytest.raises(LessonValidationError) as error:
        save(db, teacher, tag_names=tag_names)

    assert (error.value.field, error.value.message) == ("tags", TAG_REQUIRED)


def test_tag_that_is_not_on_the_list_is_refused_and_nothing_is_saved(
    db: Session, teacher: Staff
) -> None:
    before = lesson_count(db)

    with pytest.raises(LessonValidationError) as error:
        save(db, teacher, tag_names=["Transport", "Cooking"])

    assert (error.value.field, error.value.message) == ("tags", TAG_UNKNOWN)
    db.rollback()
    assert lesson_count(db) == before


# UT-70 / AC5: edit only the title; date and materials are unchanged


def test_edited_title_is_listed_and_date_and_files_are_unchanged(
    db: Session, teacher: Staff
) -> None:
    saved = save(db, teacher)
    material = attach(db, saved["id"], teacher)

    update_lesson(
        db,
        saved["id"],
        title="Catching the train",
        lesson_date=saved["lesson_date"],
        tag_names=saved["tags"],
        staff=teacher,
    )

    lesson = get_lesson(db, saved["id"])
    assert lesson["title"] == "Catching the train"
    assert lesson["lesson_date"] == LESSON_DATE
    assert lesson["tags"] == ["Transport"]
    assert [m["id"] for m in lesson["materials"]] == [material["id"]]
    assert lesson["materials"][0]["file_name"] == "bus timetable.pdf"


def test_edit_with_an_empty_title_changes_nothing(db: Session, teacher: Staff) -> None:
    saved = save(db, teacher)

    with pytest.raises(LessonValidationError) as error:
        update_lesson(
            db,
            saved["id"],
            title=" ",
            lesson_date=LESSON_DATE,
            tag_names=["Transport"],
            staff=teacher,
        )

    assert error.value.message == TITLE_REQUIRED
    assert get_lesson(db, saved["id"])["title"] == "Catching the bus"


# UT-42: only the author or a coordinator can change a lesson


def test_author_can_edit_their_own_lesson(db: Session, teacher: Staff) -> None:
    saved = save(db, teacher)

    changed = update_lesson(
        db,
        saved["id"],
        title="Mine",
        lesson_date=LESSON_DATE,
        tag_names=["Transport"],
        staff=teacher,
    )

    assert changed["title"] == "Mine"


def test_another_teacher_cannot_edit_the_lesson(
    db: Session, teacher: Staff, other_teacher: Staff
) -> None:
    saved = save(db, teacher)

    with pytest.raises(LessonPermissionError) as error:
        update_lesson(
            db,
            saved["id"],
            title="Not mine",
            lesson_date=LESSON_DATE,
            tag_names=["Transport"],
            staff=other_teacher,
        )

    assert str(error.value) == NO_PERMISSION == "You do not have permission"
    assert get_lesson(db, saved["id"])["title"] == "Catching the bus"


def test_coordinator_can_edit_any_lesson(
    db: Session, teacher: Staff, coordinator: Staff
) -> None:
    saved = save(db, teacher)

    changed = update_lesson(
        db,
        saved["id"],
        title="Checked by coordinator",
        lesson_date=LESSON_DATE,
        tag_names=["Transport"],
        staff=coordinator,
    )

    assert changed["title"] == "Checked by coordinator"
    # The author stays the teacher who wrote it.
    assert changed["created_by"] == teacher.id


def test_another_teacher_cannot_delete_or_add_files(
    db: Session, teacher: Staff, other_teacher: Staff
) -> None:
    saved = save(db, teacher)

    with pytest.raises(LessonPermissionError):
        delete_lesson(db, saved["id"], staff=other_teacher)
    with pytest.raises(LessonPermissionError):
        attach(db, saved["id"], other_teacher)

    assert get_lesson(db, saved["id"])["materials"] == []


def test_another_teacher_can_still_view_the_lesson(
    db: Session, teacher: Staff, other_teacher: Staff
) -> None:
    saved = save(db, teacher)
    material = attach(db, saved["id"], teacher)

    assert get_lesson(db, saved["id"])["title"] == "Catching the bus"
    assert get_material(db, material["id"])["id"] == material["id"]


# UT-43 / AC6: delete hides the lesson and its files


def test_deleted_lesson_leaves_the_list_and_its_files_cannot_be_found(
    db: Session, teacher: Staff
) -> None:
    saved = save(db, teacher)
    material = attach(db, saved["id"], teacher)

    delete_lesson(db, saved["id"], staff=teacher)

    assert saved["id"] not in [lesson["id"] for lesson in list_lessons(db)]
    with pytest.raises(LessonNotFoundError):
        get_lesson(db, saved["id"])
    with pytest.raises(LessonNotFoundError):
        get_material(db, material["id"])


def test_deleted_lesson_keeps_its_row_so_linked_sessions_keep_the_title(
    db: Session, teacher: Staff
) -> None:
    saved = save(db, teacher)

    delete_lesson(db, saved["id"], staff=teacher)

    row = (
        db.execute(select(lessons).where(lessons.c.id == saved["id"])).mappings().one()
    )
    assert row["title"] == "Catching the bus"
    assert row["deleted_at"] is not None


def test_coordinator_can_delete_any_lesson(
    db: Session, teacher: Staff, coordinator: Staff
) -> None:
    saved = save(db, teacher)

    delete_lesson(db, saved["id"], staff=coordinator)

    with pytest.raises(LessonNotFoundError):
        get_lesson(db, saved["id"])


def test_deleted_lesson_cannot_be_edited(db: Session, teacher: Staff) -> None:
    saved = save(db, teacher)
    delete_lesson(db, saved["id"], staff=teacher)

    with pytest.raises(LessonNotFoundError):
        update_lesson(
            db,
            saved["id"],
            title="Back",
            lesson_date=LESSON_DATE,
            tag_names=["Transport"],
            staff=teacher,
        )
