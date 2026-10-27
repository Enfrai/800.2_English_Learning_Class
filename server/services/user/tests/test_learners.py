"""Unit tests for learner records (US-003).

Cases UT-13 to UT-19 from the Test Plan, section 4.2. All names are made up.

Author: Pei Wu
Date: 23 Oct 2026
"""

import importlib
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from learners import (
    DuplicateLearnerError,
    LearnerNotFoundError,
    LearnerValidationError,
    add_learner,
    get_learner,
    list_learners,
    update_learner,
)
from models import learners

PRIVATE_FIELDS = ("date_of_birth", "address", "id_number", "photo")


# UT-13 (US-003 AC1)


def test_learner_with_first_and_family_name_is_saved_and_listed(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that learner with first and family name is saved and listed.
    """
    saved = add_learner(
        db, first_name="Mere", family_name="Walker", created_by=staff_id
    )

    assert saved["first_name"] == "Mere"
    assert saved["family_name"] == "Walker"
    assert saved["is_active"] is True
    assert [row["id"] for row in list_learners(db)] == [saved["id"]]


def test_optional_details_are_saved_and_blank_ones_are_left_empty(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that optional details are saved and blank ones are left empty.
    """
    saved = add_learner(
        db,
        first_name="Sione",
        family_name="Taufa",
        contact="  021 555 0101  ",
        first_language="   ",
        created_by=staff_id,
    )

    assert saved["contact"] == "021 555 0101"
    assert saved["first_language"] is None


def test_learner_list_is_ordered_by_family_name_then_first_name(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that learner list is ordered by family name then first name.
    """
    for first_name, family_name in [
        ("Wiremu", "Smith"),
        ("Ana", "Brown"),
        ("Ben", "Smith"),
    ]:
        add_learner(
            db, first_name=first_name, family_name=family_name, created_by=staff_id
        )

    names = [(row["first_name"], row["family_name"]) for row in list_learners(db)]

    assert names == [("Ana", "Brown"), ("Ben", "Smith"), ("Wiremu", "Smith")]


def test_learner_search_matches_part_of_the_full_name_ignoring_case(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that learner search matches part of the full name ignoring case.
    """
    add_learner(db, first_name="Hana", family_name="Ngata", created_by=staff_id)
    add_learner(db, first_name="Peter", family_name="Jones", created_by=staff_id)

    found = list_learners(db, search="HANA NG")

    assert [row["first_name"] for row in found] == ["Hana"]


# UT-14 (US-003 AC2)


@pytest.mark.parametrize(
    ("first_name", "family_name", "field", "message"),
    [
        ("", "Walker", "first_name", "First name is required"),
        ("   ", "Walker", "first_name", "First name is required"),
        (None, "Walker", "first_name", "First name is required"),
        ("Mere", "", "family_name", "Family name is required"),
        ("Mere", "   ", "family_name", "Family name is required"),
        ("Mere", None, "family_name", "Family name is required"),
    ],
)
def test_empty_name_is_refused_and_nothing_is_saved(
    db: Session,
    staff_id: UUID,
    first_name: str | None,
    family_name: str | None,
    field: str,
    message: str,
) -> None:
    """
    Verify that empty name is refused and nothing is saved.
    """
    with pytest.raises(LearnerValidationError) as error:
        add_learner(
            db, first_name=first_name, family_name=family_name, created_by=staff_id
        )

    assert error.value.field == field
    assert error.value.message == message
    assert list_learners(db) == []


# UT-15 (US-003 AC5)


@pytest.mark.parametrize("field", ["first_name", "family_name"])
def test_name_of_100_characters_is_accepted(
    db: Session, staff_id: UUID, field: str
) -> None:
    """
    Verify that name of 100 characters is accepted.
    """
    names = {"first_name": "Mere", "family_name": "Walker", field: "a" * 100}

    saved = add_learner(db, created_by=staff_id, **names)

    assert saved[field] == "a" * 100


@pytest.mark.parametrize("field", ["first_name", "family_name"])
def test_name_of_101_characters_is_rejected(
    db: Session, staff_id: UUID, field: str
) -> None:
    """
    Verify that name of 101 characters is rejected.
    """
    names = {"first_name": "Mere", "family_name": "Walker", field: "a" * 101}

    with pytest.raises(LearnerValidationError) as error:
        add_learner(db, created_by=staff_id, **names)

    assert error.value.field == field
    assert error.value.message == "Name must be 100 characters or fewer"
    assert list_learners(db) == []


def test_name_length_is_counted_after_trimming_spaces(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that name length is counted after trimming spaces.
    """
    saved = add_learner(
        db, first_name=f"  {'a' * 100}  ", family_name="Walker", created_by=staff_id
    )

    assert saved["first_name"] == "a" * 100


# UT-16 (US-003 AC4)


def test_same_name_gives_a_warning_and_nothing_is_saved(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that same name gives a warning and nothing is saved.
    """
    first = add_learner(
        db, first_name="Mere", family_name="Walker", created_by=staff_id
    )

    with pytest.raises(DuplicateLearnerError) as error:
        add_learner(db, first_name="mere", family_name="WALKER", created_by=staff_id)

    assert str(error.value) == "A learner with this name already exists"
    assert [row["id"] for row in error.value.duplicates] == [first["id"]]
    assert len(list_learners(db)) == 1


def test_same_name_can_be_added_anyway_and_gives_two_records(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that same name can be added anyway and gives two records.
    """
    first = add_learner(
        db, first_name="Mere", family_name="Walker", created_by=staff_id
    )

    second = add_learner(
        db,
        first_name="Mere",
        family_name="Walker",
        allow_duplicate=True,
        created_by=staff_id,
    )

    assert second["id"] != first["id"]
    assert len(list_learners(db)) == 2


def test_renaming_to_another_learners_name_gives_a_warning(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that renaming to another learners name gives a warning.
    """
    add_learner(db, first_name="Mere", family_name="Walker", created_by=staff_id)
    other = add_learner(db, first_name="Ana", family_name="Brown", created_by=staff_id)

    with pytest.raises(DuplicateLearnerError):
        update_learner(
            db,
            other["id"],
            first_name="Mere",
            family_name="Walker",
            updated_by=staff_id,
        )

    assert get_learner(db, other["id"])["first_name"] == "Ana"


def test_saving_a_learner_with_an_unchanged_name_gives_no_warning(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that saving a learner with an unchanged name gives no warning.
    """
    add_learner(db, first_name="Mere", family_name="Walker", created_by=staff_id)
    second = add_learner(
        db,
        first_name="Mere",
        family_name="Walker",
        allow_duplicate=True,
        created_by=staff_id,
    )

    updated = update_learner(
        db,
        second["id"],
        first_name="Mere",
        family_name="Walker",
        contact="mere@example.com",
        updated_by=staff_id,
    )

    assert updated["contact"] == "mere@example.com"


# UT-17 (US-003 AC3)


def test_changing_first_language_keeps_the_other_fields(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that changing first language keeps the other fields.
    """
    saved = add_learner(
        db,
        first_name="Sione",
        family_name="Taufa",
        contact="021 555 0101",
        first_language="Tongan",
        created_by=staff_id,
    )

    update_learner(
        db,
        saved["id"],
        first_name="Sione",
        family_name="Taufa",
        contact="021 555 0101",
        first_language="Samoan",
        updated_by=staff_id,
    )
    shown = get_learner(db, saved["id"])

    assert shown["first_language"] == "Samoan"
    assert shown["first_name"] == "Sione"
    assert shown["family_name"] == "Taufa"
    assert shown["contact"] == "021 555 0101"
    assert shown["updated_by"] == staff_id


def test_update_is_validated_like_a_new_learner(db: Session, staff_id: UUID) -> None:
    """
    Verify that update is validated like a new learner.
    """
    saved = add_learner(
        db, first_name="Mere", family_name="Walker", created_by=staff_id
    )

    with pytest.raises(LearnerValidationError) as error:
        update_learner(
            db, saved["id"], first_name="", family_name="Walker", updated_by=staff_id
        )

    assert error.value.message == "First name is required"
    assert get_learner(db, saved["id"])["first_name"] == "Mere"


def test_unknown_learner_is_reported_as_not_found(db: Session, staff_id: UUID) -> None:
    """
    Verify that unknown learner is reported as not found.
    """
    with pytest.raises(LearnerNotFoundError):
        get_learner(db, uuid4())
    with pytest.raises(LearnerNotFoundError):
        update_learner(
            db, uuid4(), first_name="Mere", family_name="Walker", updated_by=staff_id
        )


# UT-18 (US-003, NFR-05)


def test_learner_table_has_no_private_fields() -> None:
    """
    Verify that learner table has no private fields.
    """
    assert not set(PRIVATE_FIELDS) & set(learners.c.keys())


def test_private_fields_in_a_request_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Importing app creates an engine but does not connect, so a dummy URL is fine.
    """
    Verify that private fields in a request are ignored.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused@localhost/unused")
    app = importlib.import_module("app")

    payload = app.LearnerIn.model_validate(
        {
            "first_name": "Mere",
            "family_name": "Walker",
            "date_of_birth": "2000-01-01",
            "address": "1 Queen Street",
            "id_number": "AB123456",
            "photo": "photo.jpg",
        }
    )

    assert not set(PRIVATE_FIELDS) & set(payload.model_dump())


# UT-19 (NFR-10)


@pytest.mark.parametrize(
    ("first_name", "family_name"),
    [("Tāne", "Māhina"), ("Siobhán", "O'Neill")],
)
def test_names_with_macrons_and_apostrophes_are_kept_exactly(
    db: Session, staff_id: UUID, first_name: str, family_name: str
) -> None:
    """
    Verify that names with macrons and apostrophes are kept exactly.
    """
    saved = add_learner(
        db, first_name=first_name, family_name=family_name, created_by=staff_id
    )
    shown = get_learner(db, saved["id"])

    assert (shown["first_name"], shown["family_name"]) == (first_name, family_name)
    assert [row["family_name"] for row in list_learners(db, search=family_name)] == [
        family_name
    ]
