"""Unit tests for finding a learner by the name typed at QR sign-in (US-012).

Covers the name matching behind Test Plan UT-65 and the internal endpoint
that only the Accessment Service may call. Team decision (25 Oct 2026):
a name shared by several learners is never guessed.

Author: Pei Wu
Date: 25 Oct 2026
"""

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from learners import (
    AmbiguousLearnerNameError,
    LearnerNotFoundError,
    add_learner,
    find_learner_for_sign_in,
)
from models import learners
from test_postgres import PgContext

KEY = "test-internal-key"


def add(db: Session, staff_id: UUID, first: str, family: str) -> UUID:
    """
    Prepare or exercise add in the test sign in lookup test scenario.
    """
    return add_learner(
        db,
        first_name=first,
        family_name=family,
        created_by=staff_id,
        allow_duplicate=True,
    )["id"]


def unique(name: str) -> str:
    """Learner rows persist within a run, so each test uses its own names."""
    return f"{name}{uuid4().hex[:6]}"


# Matching the typed name


@pytest.mark.parametrize(
    ("typed_first", "type_family"),
    [
        ("Tāne", lambda family: family),
        ("tane", lambda family: family.upper().replace("Ā", "A")),
        ("  Tāne ", lambda family: f"  {family}  "),
        ("TĀNE", lambda family: family.lower()),
    ],
    ids=["exact", "no macrons, other case", "extra spaces", "macrons, other case"],
)
def test_name_matches_ignoring_case_spaces_and_macrons(
    db: Session,
    staff_id: UUID,
    typed_first: str,
    type_family: Callable[[str], str],
) -> None:
    """
    Verify that name matches ignoring case spaces and macrons.
    """
    family = unique("Māhina")
    learner_id = add(db, staff_id, "Tāne", family)

    found = find_learner_for_sign_in(db, typed_first, type_family(family))

    assert found == {"id": learner_id, "first_name": "Tāne", "family_name": family}


def test_only_the_matched_learner_is_returned_never_the_list(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that only the matched learner is returned never the list.
    """
    family = unique("Walker")
    add(db, staff_id, "Mere", family)
    add(db, staff_id, "Sione", family)

    found = find_learner_for_sign_in(db, "Mere", family)

    assert set(found) == {"id", "first_name", "family_name"}
    assert found["first_name"] == "Mere"


def test_name_shared_by_several_learners_is_never_guessed(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that name shared by several learners is never guessed.
    """
    family = unique("Walker")
    add(db, staff_id, "Mere", family)
    add(db, staff_id, "Mere", family)

    with pytest.raises(AmbiguousLearnerNameError):
        find_learner_for_sign_in(db, "mere", family)


def test_inactive_learner_is_not_found_and_does_not_make_a_name_ambiguous(
    db: Session, staff_id: UUID
) -> None:
    """
    Verify that inactive learner is not found and does not make a name ambiguous.
    """
    family = unique("Silva")
    former = add(db, staff_id, "Ana", family)
    current = add(db, staff_id, "Ana", family)
    db.execute(learners.update().where(learners.c.id == former).values(is_active=False))

    assert find_learner_for_sign_in(db, "Ana", family)["id"] == current


@pytest.mark.parametrize(
    ("first", "family"),
    [("Nobody", "Here"), ("", "Walker"), ("Mere", None), ("a" * 101, "Walker")],
)
def test_unknown_empty_or_too_long_name_is_not_found(
    db: Session, staff_id: UUID, first: str | None, family: str | None
) -> None:
    """
    Verify that unknown empty or too long name is not found.
    """
    add(db, staff_id, "Mere", "Walker")

    with pytest.raises(LearnerNotFoundError):
        find_learner_for_sign_in(db, first, family)


def test_part_of_a_name_does_not_match(db: Session, staff_id: UUID) -> None:
    """
    Verify that part of a name does not match.
    """
    family = unique("Ngata")
    add(db, staff_id, "Aroha", family)

    with pytest.raises(LearnerNotFoundError):
        find_learner_for_sign_in(db, "Aro", family)


# The internal endpoint (Accessment Service only)


def add_in_pg(pg: PgContext, first: str, family: str) -> UUID:
    """
    Prepare or exercise add in pg in the test sign in lookup test scenario.
    """
    learner_id = uuid4()
    with pg.engine.begin() as db:
        db.execute(
            learners.insert().values(
                id=learner_id,
                first_name=first,
                family_name=family,
                created_by=pg.user_id,
            )
        )
    return learner_id


def match(pg: PgContext, key: str | None, first: str, family: str) -> object:
    """
    Prepare or exercise match in the test sign in lookup test scenario.
    """
    headers = {"Cookie": ""} | ({"X-Internal-Key": key} if key else {})
    return pg.clients[0].post(
        "/internal/learners/match",
        json={"first_name": first, "family_name": family},
        headers=headers,
    )


@pytest.fixture
def keyed_pg(pg: PgContext) -> PgContext:
    """
    Provide postgreSQL fixture configured with matching internal API keys.
    """
    for app_module in (pg.a, pg.b):
        app_module.INTERNAL_API_KEY = KEY
    return pg


def test_endpoint_returns_the_matched_learner_with_the_key(
    keyed_pg: PgContext,
) -> None:
    """
    Verify that endpoint returns the matched learner with the key.
    """
    family = unique("Māhina")
    learner_id = add_in_pg(keyed_pg, "Tāne", family)

    response = match(keyed_pg, KEY, "tane", family)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(learner_id),
        "first_name": "Tāne",
        "family_name": family,
    }


@pytest.mark.parametrize("key", [None, "wrong-key"])
def test_endpoint_refuses_a_missing_or_wrong_key(
    keyed_pg: PgContext, key: str | None
) -> None:
    """
    Verify that endpoint refuses a missing or wrong key.
    """
    family = unique("Ngata")
    add_in_pg(keyed_pg, "Aroha", family)

    response = match(keyed_pg, key, "Aroha", family)

    assert response.status_code == 403
    assert response.json() == {"detail": "Internal access only"}


def test_endpoint_is_closed_when_no_key_is_configured(pg: PgContext) -> None:
    """
    Verify that endpoint is closed when no key is configured.
    """
    pg.a.INTERNAL_API_KEY = ""

    assert match(pg, "", "Aroha", "Ngata").status_code == 403
    assert match(pg, "anything", "Aroha", "Ngata").status_code == 403


def test_endpoint_reports_not_found_and_shared_names(keyed_pg: PgContext) -> None:
    """
    Verify that endpoint reports not found and shared names.
    """
    family = unique("Walker")
    add_in_pg(keyed_pg, "Mere", family)
    add_in_pg(keyed_pg, "Mere", family)

    assert match(keyed_pg, KEY, "Nobody", family).status_code == 404
    shared = match(keyed_pg, KEY, "Mere", family)
    assert shared.status_code == 409
    assert shared.json() == {"detail": "Several learners have this name"}
