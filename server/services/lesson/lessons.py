"""Lessons: save, list, edit and delete, with topic tags and files (US-006).

Lessons are shared, so every logged-in teacher and coordinator can see and
download them. Only the author or a coordinator can change or delete one
(UI design document, roles table). Deleting only hides a lesson and its
files (``deleted_at``), so sessions that linked it keep its title.

Teacher access to lesson materials (the story after US-006): the list
also gives each lesson's file count and Māori content review status. Staff
see every lesson; the review label tells them when Māori content is not yet
reviewed (US-008 records the review).

Author: Sandhya Tiwari
Date: 23 Oct 2026
Updated: 24 Oct 2026 (file counts for the lesson library)
"""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from models import lesson_materials, lesson_tags, lessons, tags
from user_client import Staff

MAX_TITLE_LENGTH = 255

# Confirmed by the Story Owner on 23 Oct 2026, in display order.
TOPIC_TAGS = (
    "Transport",
    "Health",
    "Shopping",
    "Culture",
    "History",
    "Accommodation",
    "Lifestyle",
)

# Message catalogue, UI design document section 7 and Test Plan UT-39.
TITLE_REQUIRED = "Title is required"
TITLE_TOO_LONG = f"Title must be {MAX_TITLE_LENGTH} characters or fewer"
DATE_REQUIRED = "Lesson date is required"
TAG_REQUIRED = "Choose at least one topic tag"
TAG_UNKNOWN = "Choose topic tags from the list"
NO_PERMISSION = "You do not have permission"


class LessonError(Exception):
    """Base class for lesson errors that are reported to the user."""


class LessonValidationError(LessonError):
    """An input value is missing or breaks a rule."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class LessonNotFoundError(LessonError):
    """No lesson (or file) has the given id, or it was deleted."""


class LessonPermissionError(LessonError):
    """Only the author or a coordinator can change this lesson."""

    def __init__(self) -> None:
        super().__init__(NO_PERMISSION)


def seed_tags(db: Session) -> None:
    """Add any missing topic tags. Safe to run on every start and replica."""
    db.execute(
        insert(tags)
        .values([{"name": name} for name in TOPIC_TAGS])
        .on_conflict_do_nothing(index_elements=["name"])
    )


def list_tags(db: Session) -> list[str]:
    """Return the tag names in the agreed order; any others follow by name."""
    names = db.execute(select(tags.c.name)).scalars().all()
    order = {name: index for index, name in enumerate(TOPIC_TAGS)}
    return sorted(names, key=lambda name: (order.get(name, len(order)), name))


def clean_lesson_fields(
    title: str | None, lesson_date: date | None, tag_names: list[str] | None
) -> dict[str, Any]:
    """Trim and check the lesson fields; return the values to store.

    The title is kept exactly as typed apart from outer spaces, so macrons
    such as "Te reo Māori" are stored and shown unchanged (NFR-10).
    """
    cleaned_title = (title or "").strip()
    if not cleaned_title:
        raise LessonValidationError("title", TITLE_REQUIRED)
    if len(cleaned_title) > MAX_TITLE_LENGTH:
        raise LessonValidationError("title", TITLE_TOO_LONG)
    if lesson_date is None:
        raise LessonValidationError("lesson_date", DATE_REQUIRED)
    # Keep the first of any repeats, in the order chosen.
    names = list(
        dict.fromkeys(name.strip() for name in tag_names or [] if name.strip())
    )
    if not names:
        raise LessonValidationError("tags", TAG_REQUIRED)
    return {"title": cleaned_title, "lesson_date": lesson_date, "tags": names}


def _tag_ids(db: Session, names: list[str]) -> list[UUID]:
    rows = db.execute(select(tags.c.id, tags.c.name).where(tags.c.name.in_(names)))
    by_name = {row.name: row.id for row in rows}
    if len(by_name) != len(names):
        raise LessonValidationError("tags", TAG_UNKNOWN)
    return [by_name[name] for name in names]


def _set_tags(db: Session, lesson_id: UUID, names: list[str]) -> None:
    tag_ids = _tag_ids(db, names)
    db.execute(lesson_tags.delete().where(lesson_tags.c.lesson_id == lesson_id))
    db.execute(
        lesson_tags.insert(),
        [{"lesson_id": lesson_id, "tag_id": tag_id} for tag_id in tag_ids],
    )


def _tags_by_lesson(db: Session, lesson_ids: list[UUID]) -> dict[UUID, list[str]]:
    found: dict[UUID, list[str]] = {lesson_id: [] for lesson_id in lesson_ids}
    if not lesson_ids:
        return found
    rows = db.execute(
        select(lesson_tags.c.lesson_id, tags.c.name)
        .join(tags, tags.c.id == lesson_tags.c.tag_id)
        .where(lesson_tags.c.lesson_id.in_(lesson_ids))
    )
    order = {name: index for index, name in enumerate(TOPIC_TAGS)}
    for row in rows:
        found[row.lesson_id].append(row.name)
    for names in found.values():
        names.sort(key=lambda name: (order.get(name, len(order)), name))
    return found


def _materials(db: Session, lesson_id: UUID) -> list[dict[str, Any]]:
    query = (
        select(lesson_materials)
        .where(
            lesson_materials.c.lesson_id == lesson_id,
            lesson_materials.c.deleted_at.is_(None),
        )
        .order_by(lesson_materials.c.created_at, lesson_materials.c.file_name)
    )
    return [dict(row) for row in db.execute(query).mappings()]


def _live_lesson(
    db: Session, lesson_id: UUID, for_update: bool = False
) -> dict[str, Any]:
    query = select(lessons).where(
        lessons.c.id == lesson_id, lessons.c.deleted_at.is_(None)
    )
    if for_update:
        query = query.with_for_update()
    row = db.execute(query).mappings().first()
    if row is None:
        raise LessonNotFoundError("Lesson not found")
    return dict(row)


def can_change(lesson: dict[str, Any], staff: Staff) -> bool:
    """The author or any coordinator may change or delete a lesson."""
    return staff.is_coordinator or lesson["created_by"] == staff.id


def _check_can_change(lesson: dict[str, Any], staff: Staff) -> None:
    if not can_change(lesson, staff):
        raise LessonPermissionError()


def add_lesson(
    db: Session,
    *,
    title: str | None,
    lesson_date: date | None,
    tag_names: list[str] | None,
    created_by: UUID,
) -> dict[str, Any]:
    """Save a new lesson with its tags and return it.

    The caller owns the transaction and commits it.

    Raises:
        LessonValidationError: the title, date or tags break a rule.
            Nothing is saved.
    """
    fields = clean_lesson_fields(title, lesson_date, tag_names)
    row = (
        db.execute(
            lessons.insert()
            .values(
                title=fields["title"],
                lesson_date=fields["lesson_date"],
                created_by=created_by,
            )
            .returning(lessons)
        )
        .mappings()
        .one()
    )
    _set_tags(db, row["id"], fields["tags"])
    return {**row, "tags": fields["tags"], "materials": [], "material_count": 0}


def list_lessons(db: Session) -> list[dict[str, Any]]:
    """Return lessons that are not deleted, newest lesson date first."""
    query = (
        select(lessons)
        .where(lessons.c.deleted_at.is_(None))
        .order_by(lessons.c.lesson_date.desc(), lessons.c.created_at.desc())
    )
    rows = [dict(row) for row in db.execute(query).mappings()]
    ids = [row["id"] for row in rows]
    tags_by_lesson = _tags_by_lesson(db, ids)
    counts = _material_counts(db, ids)
    return [
        {
            **row,
            "tags": tags_by_lesson[row["id"]],
            "material_count": counts.get(row["id"], 0),
        }
        for row in rows
    ]


def _material_counts(db: Session, lesson_ids: list[UUID]) -> dict[UUID, int]:
    """Number of files that can be downloaded, per lesson."""
    if not lesson_ids:
        return {}
    rows = db.execute(
        select(lesson_materials.c.lesson_id, func.count())
        .where(
            lesson_materials.c.lesson_id.in_(lesson_ids),
            lesson_materials.c.deleted_at.is_(None),
        )
        .group_by(lesson_materials.c.lesson_id)
    )
    return {lesson_id: count for lesson_id, count in rows}


def get_lesson(db: Session, lesson_id: UUID) -> dict[str, Any]:
    """Return one lesson with its tags and files.

    Raises:
        LessonNotFoundError: no lesson has this id, or it was deleted.
    """
    lesson = _live_lesson(db, lesson_id)
    materials = _materials(db, lesson_id)
    return {
        **lesson,
        "tags": _tags_by_lesson(db, [lesson_id])[lesson_id],
        "materials": materials,
        "material_count": len(materials),
    }


def update_lesson(
    db: Session,
    lesson_id: UUID,
    *,
    title: str | None,
    lesson_date: date | None,
    tag_names: list[str] | None,
    staff: Staff,
) -> dict[str, Any]:
    """Replace a lesson's title, date and tags. Its files are not touched.

    Raises:
        LessonNotFoundError: no lesson has this id, or it was deleted.
        LessonPermissionError: the user is not the author or a coordinator.
        LessonValidationError: a value breaks a rule. Nothing is changed.
    """
    lesson = _live_lesson(db, lesson_id, for_update=True)
    _check_can_change(lesson, staff)
    fields = clean_lesson_fields(title, lesson_date, tag_names)
    db.execute(
        lessons.update()
        .where(lessons.c.id == lesson_id)
        .values(
            title=fields["title"],
            lesson_date=fields["lesson_date"],
            updated_at=datetime.now(UTC),
        )
    )
    _set_tags(db, lesson_id, fields["tags"])
    return get_lesson(db, lesson_id)


def delete_lesson(db: Session, lesson_id: UUID, *, staff: Staff) -> None:
    """Hide a lesson and its files. They leave the list and cannot be downloaded.

    Raises:
        LessonNotFoundError: no lesson has this id, or it was already deleted.
        LessonPermissionError: the user is not the author or a coordinator.
    """
    lesson = _live_lesson(db, lesson_id, for_update=True)
    _check_can_change(lesson, staff)
    now = datetime.now(UTC)
    db.execute(
        lessons.update()
        .where(lessons.c.id == lesson_id)
        .values(deleted_at=now, updated_at=now)
    )
    db.execute(
        lesson_materials.update()
        .where(
            lesson_materials.c.lesson_id == lesson_id,
            lesson_materials.c.deleted_at.is_(None),
        )
        .values(deleted_at=now)
    )


def check_can_add_material(db: Session, lesson_id: UUID, *, staff: Staff) -> None:
    """Check before a file is stored, so a refused upload never reaches disk."""
    _check_can_change(_live_lesson(db, lesson_id), staff)


def add_material(
    db: Session,
    lesson_id: UUID,
    *,
    file_name: str,
    storage_key: str,
    mime_type: str,
    file_size: int,
    share_with_learners: bool,
    staff: Staff,
) -> dict[str, Any]:
    """Record a stored file on a lesson and return it.

    Raises:
        LessonNotFoundError: no lesson has this id, or it was deleted.
        LessonPermissionError: the user is not the author or a coordinator.
    """
    lesson = _live_lesson(db, lesson_id, for_update=True)
    _check_can_change(lesson, staff)
    row = (
        db.execute(
            lesson_materials.insert()
            .values(
                lesson_id=lesson_id,
                file_name=file_name,
                storage_key=storage_key,
                mime_type=mime_type,
                file_size=file_size,
                share_with_learners=share_with_learners,
                uploaded_by=staff.id,
            )
            .returning(lesson_materials)
        )
        .mappings()
        .one()
    )
    db.execute(
        lessons.update()
        .where(lessons.c.id == lesson_id)
        .values(updated_at=datetime.now(UTC))
    )
    return dict(row)


def get_material(db: Session, material_id: UUID) -> dict[str, Any]:
    """Return a file that can be downloaded: neither it nor its lesson is deleted.

    Raises:
        LessonNotFoundError: no such file, or it or its lesson was deleted.
    """
    row = (
        db.execute(
            select(lesson_materials)
            .join(lessons, lessons.c.id == lesson_materials.c.lesson_id)
            .where(
                lesson_materials.c.id == material_id,
                lesson_materials.c.deleted_at.is_(None),
                lessons.c.deleted_at.is_(None),
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise LessonNotFoundError("File not found")
    return dict(row)


def _material_for_change(
    db: Session, material_id: UUID, staff: Staff
) -> dict[str, Any]:
    material = get_material(db, material_id)
    _check_can_change(_live_lesson(db, material["lesson_id"], for_update=True), staff)
    return material


def set_share_with_learners(
    db: Session, material_id: UUID, *, share: bool, staff: Staff
) -> dict[str, Any]:
    """Change a file's "Share with learners" tick (used by US-013).

    Raises:
        LessonNotFoundError: no such file, or it or its lesson was deleted.
        LessonPermissionError: the user is not the author or a coordinator.
    """
    _material_for_change(db, material_id, staff)
    row = (
        db.execute(
            lesson_materials.update()
            .where(lesson_materials.c.id == material_id)
            .values(share_with_learners=share)
            .returning(lesson_materials)
        )
        .mappings()
        .one()
    )
    return dict(row)


def remove_material(db: Session, material_id: UUID, *, staff: Staff) -> None:
    """Hide one file of a lesson so it can no longer be downloaded.

    Raises:
        LessonNotFoundError: no such file, or it or its lesson was deleted.
        LessonPermissionError: the user is not the author or a coordinator.
    """
    material = _material_for_change(db, material_id, staff)
    now = datetime.now(UTC)
    db.execute(
        lesson_materials.update()
        .where(lesson_materials.c.id == material_id)
        .values(deleted_at=now)
    )
    db.execute(
        lessons.update()
        .where(lessons.c.id == material["lesson_id"])
        .values(updated_at=now)
    )
