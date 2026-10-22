"""Learner records: add, view and update (US-003).

Author: Pei Wu
Date: 22 Oct 2026
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from models import learners
from sqlalchemy import func, select
from sqlalchemy.orm import Session

MAX_NAME_LENGTH = 100
MAX_CONTACT_LENGTH = 255
MAX_LANGUAGE_LENGTH = 100

NAME_TOO_LONG = f"Name must be {MAX_NAME_LENGTH} characters or fewer"


class LearnerError(Exception):
    """Base class for learner errors that are reported to the user."""


class LearnerValidationError(LearnerError):
    """An input value is missing or breaks a rule."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class LearnerNotFoundError(LearnerError):
    """No learner has the given id."""


class DuplicateLearnerError(LearnerError):
    """Another learner has the same first and family name.

    Two people can share a name, so the caller may repeat the request with
    ``allow_duplicate=True`` after the user confirms.
    """

    def __init__(self, duplicates: list[dict[str, Any]]) -> None:
        super().__init__("A learner with this name already exists")
        self.duplicates = duplicates


def _clean_name(value: str | None, field: str, label: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise LearnerValidationError(field, f"{label} is required")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise LearnerValidationError(field, NAME_TOO_LONG)
    return cleaned


def _clean_optional(
    value: str | None, field: str, label: str, max_length: int
) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise LearnerValidationError(
            field, f"{label} must be {max_length} characters or fewer"
        )
    return cleaned


def clean_learner_fields(
    first_name: str | None,
    family_name: str | None,
    contact: str | None,
    first_language: str | None,
) -> dict[str, str | None]:
    """Trim and check the learner fields; return the values to store."""
    return {
        "first_name": _clean_name(first_name, "first_name", "First name"),
        "family_name": _clean_name(family_name, "family_name", "Family name"),
        "contact": _clean_optional(contact, "contact", "Contact", MAX_CONTACT_LENGTH),
        "first_language": _clean_optional(
            first_language, "first_language", "First language", MAX_LANGUAGE_LENGTH
        ),
    }


def _find_same_name(
    db: Session, first_name: str, family_name: str, exclude_id: UUID | None = None
) -> list[dict[str, Any]]:
    """Return learners with the same first and family name, ignoring case."""
    query = select(learners).where(
        func.lower(learners.c.first_name) == first_name.lower(),
        func.lower(learners.c.family_name) == family_name.lower(),
    )
    if exclude_id is not None:
        query = query.where(learners.c.id != exclude_id)
    return [dict(row) for row in db.execute(query).mappings()]


def add_learner(
    db: Session,
    *,
    first_name: str | None,
    family_name: str | None,
    created_by: UUID,
    contact: str | None = None,
    first_language: str | None = None,
    allow_duplicate: bool = False,
) -> dict[str, Any]:
    """Add a learner and return the saved record.

    The caller owns the transaction and commits it.

    Raises:
        LearnerValidationError: a name is empty or too long, or another
            field is too long. Nothing is saved.
        DuplicateLearnerError: a learner with the same first and family name
            exists and ``allow_duplicate`` is False.
    """
    fields = clean_learner_fields(first_name, family_name, contact, first_language)
    if not allow_duplicate:
        duplicates = _find_same_name(
            db, str(fields["first_name"]), str(fields["family_name"])
        )
        if duplicates:
            raise DuplicateLearnerError(duplicates)
    row = (
        db.execute(
            learners.insert()
            .values(created_by=created_by, **fields)
            .returning(learners)
        )
        .mappings()
        .one()
    )
    return dict(row)


def get_learner(db: Session, learner_id: UUID) -> dict[str, Any]:
    """Return one learner.

    Raises:
        LearnerNotFoundError: no learner has this id.
    """
    row = (
        db.execute(select(learners).where(learners.c.id == learner_id))
        .mappings()
        .first()
    )
    if row is None:
        raise LearnerNotFoundError("Learner not found")
    return dict(row)


def list_learners(db: Session, search: str | None = None) -> list[dict[str, Any]]:
    """Return active learners ordered by family name, then first name.

    ``search`` keeps learners whose full name contains the text, ignoring case.
    """
    query = select(learners).where(learners.c.is_active.is_(True))
    term = (search or "").strip()
    if term:
        full_name = learners.c.first_name + " " + learners.c.family_name
        query = query.where(full_name.icontains(term, autoescape=True))
    query = query.order_by(
        func.lower(learners.c.family_name), func.lower(learners.c.first_name)
    )
    return [dict(row) for row in db.execute(query).mappings()]


def update_learner(
    db: Session,
    learner_id: UUID,
    *,
    first_name: str | None,
    family_name: str | None,
    updated_by: UUID,
    contact: str | None = None,
    first_language: str | None = None,
    allow_duplicate: bool = False,
) -> dict[str, Any]:
    """Replace a learner's details and return the saved record.

    All four detail fields are replaced, so an empty ``contact`` or
    ``first_language`` clears the stored value. The caller owns the
    transaction and commits it.

    Raises:
        LearnerNotFoundError: no learner has this id.
        LearnerValidationError: a value is missing or too long.
        DuplicateLearnerError: the new name matches another learner and
            ``allow_duplicate`` is False.
    """
    current = get_learner(db, learner_id)
    fields = clean_learner_fields(first_name, family_name, contact, first_language)
    new_name = (str(fields["first_name"]).lower(), str(fields["family_name"]).lower())
    old_name = (current["first_name"].lower(), current["family_name"].lower())
    if new_name != old_name and not allow_duplicate:
        duplicates = _find_same_name(
            db,
            str(fields["first_name"]),
            str(fields["family_name"]),
            exclude_id=learner_id,
        )
        if duplicates:
            raise DuplicateLearnerError(duplicates)
    row = (
        db.execute(
            learners.update()
            .where(learners.c.id == learner_id)
            .values(updated_by=updated_by, updated_at=datetime.now(UTC), **fields)
            .returning(learners)
        )
        .mappings()
        .one()
    )
    return dict(row)
