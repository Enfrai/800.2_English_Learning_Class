"""Learner records: add, view and update (US-003), and find a learner by
the name they type when signing in with the QR code (US-012).

Author: Pei Wu
Date: 22 Oct 2026
Updated: 25 Oct 2026 (US-012 sign-in lookup)
"""

import unicodedata
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
        """
        Initialize LearnerValidationError and retain the supplied constructor state.
        """
        super().__init__(message)
        self.field = field
        self.message = message


class LearnerNotFoundError(LearnerError):
    """No learner has the given id."""


class AmbiguousLearnerNameError(LearnerError):
    """More than one active learner has the typed name (US-012)."""


class DuplicateLearnerError(LearnerError):
    """Another learner has the same first and family name.

    Two people can share a name, so the caller may repeat the request with
    ``allow_duplicate=True`` after the user confirms.
    """

    def __init__(self, duplicates: list[dict[str, Any]]) -> None:
        """
        Initialize DuplicateLearnerError and retain the supplied constructor state.
        """
        super().__init__("A learner with this name already exists")
        self.duplicates = duplicates


def _clean_name(value: str | None, field: str, label: str) -> str:
    """
    Trim and validate a required learner name field.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        raise LearnerValidationError(field, f"{label} is required")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise LearnerValidationError(field, NAME_TOO_LONG)
    return cleaned


def _clean_optional(
    value: str | None, field: str, label: str, max_length: int
) -> str | None:
    """
    Normalize and validate an optional learner contact or language field.
    """
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


def _sign_in_key(value: str) -> str:
    """Lower case, single spaces, and no macrons or other accents."""
    decomposed = unicodedata.normalize("NFKD", value)
    letters = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(letters.casefold().split())


def find_learner_for_sign_in(
    db: Session, first_name: str | None, family_name: str | None
) -> dict[str, Any]:
    """Return the one active learner whose name matches what was typed (US-012).

    Matching ignores letter case, extra spaces and macrons, because a phone
    keyboard may not offer macrons; stored names are never changed. Only the
    matched learner's id and name are returned, never the class list.

    Raises:
        LearnerNotFoundError: no active learner has this name, or a name part
            is empty or too long.
        AmbiguousLearnerNameError: several active learners have this name, so
            the teacher must tick the right one.
    """
    first, family = _sign_in_key(first_name or ""), _sign_in_key(family_name or "")
    if not first or not family or max(len(first), len(family)) > MAX_NAME_LENGTH:
        raise LearnerNotFoundError("Learner not found")
    # Accents cannot be ignored in SQL without an extension, so compare in
    # Python. The club's active list is small (about 50 learners).
    rows = db.execute(
        select(learners.c.id, learners.c.first_name, learners.c.family_name).where(
            learners.c.is_active.is_(True)
        )
    ).mappings()
    matches = [
        dict(row)
        for row in rows
        if _sign_in_key(row["first_name"]) == first
        and _sign_in_key(row["family_name"]) == family
    ]
    if not matches:
        raise LearnerNotFoundError("Learner not found")
    if len(matches) > 1:
        raise AmbiguousLearnerNameError("Several learners have this name")
    return matches[0]
