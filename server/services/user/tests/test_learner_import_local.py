"""SQLite route checks; these do not verify PostgreSQL advisory-lock semantics."""

from uuid import uuid4

import pytest
from sqlalchemy import event, select
from test_learner_csv import document

from models import learners
from test_auth import AuthContext


@pytest.mark.parametrize(
    "role,status", [("coordinator", 200), ("teacher", 403), (None, 401)]
)
def test_local_import_access(
    context: AuthContext, role: str | None, status: int
) -> None:
    # Only emulate SQL function availability, never PostgreSQL locking behavior.
    """
    Verify that local import access.
    """
    def configure(raw, record) -> None:
        """
        Prepare or exercise configure in the test learner import local test scenario.
        """
        raw.create_function("gen_random_uuid", 0, lambda: uuid4().hex)
        raw.create_function("pg_advisory_xact_lock", 1, lambda key: None)

    event.listen(context["engine"], "connect", configure)
    context["engine"].dispose()
    learners.create(context["engine"])
    if role:
        with context["factory"].begin() as db:
            db.execute(context["users"].update().values(role=role))
    response = context["client"].post(
        "/learners/import",
        headers={"Authorization": f"Bearer {context['token']}"} if role else {},
        files={
            "file": ("a.csv", document([["Fiction", "Example", "", ""]]), "text/csv")
        },
    )
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    with context["engine"].connect() as db:
        assert len(db.execute(select(learners)).all()) == int(status == 200)
    if status == 200:
        assert response.json()["message"] == "1 learners imported"


@pytest.mark.parametrize(
    "origin,status",
    [(None, 403), ("https://evil.invalid", 403), ("http://testserver", 422)],
)
def test_local_cookie_validation(
    context: AuthContext, origin: str | None, status: int
) -> None:
    """
    Verify that local cookie validation.
    """
    with context["factory"].begin() as db:
        db.execute(context["users"].update().values(role="coordinator"))
    headers = {"Cookie": f"ako_session={context['token']}"}
    if origin:
        headers["Origin"] = origin
    response = context["client"].post(
        "/learners/import",
        headers=headers,
        files={"file": ("bad.txt", b"invalid", "text/plain")},
    )
    assert response.status_code == status


@pytest.mark.parametrize("extra_bytes,status", [(0, 200), (1, 413)])
def test_multipart_file_boundary(
    context: AuthContext, extra_bytes: int, status: int
) -> None:
    """Multipart overhead must not count toward the application's CSV byte cap."""

    def configure(raw, record) -> None:
        """
        Prepare or exercise configure in the test learner import local test scenario.
        """
        raw.create_function("gen_random_uuid", 0, lambda: uuid4().hex)
        raw.create_function("pg_advisory_xact_lock", 1, lambda key: None)

    event.listen(context["engine"], "connect", configure)
    context["engine"].dispose()
    learners.create(context["engine"])
    with context["factory"].begin() as db:
        db.execute(context["users"].update().values(role="coordinator"))
    prefix = b"first_name,family_name,first_language,contact\nFiction,Boundary,,"
    content = prefix + b" " * (1_048_576 + extra_bytes - len(prefix))
    response = context["client"].post(
        "/learners/import",
        headers={"Authorization": f"Bearer {context['token']}"},
        files={"file": ("boundary.csv", content, "text/csv")},
    )
    assert response.status_code == status
    assert len(response.request.content) > len(content)
    assert len(response.request.content) < 2 * 1_048_576
    with context["engine"].connect() as db:
        assert len(db.execute(select(learners)).all()) == int(status == 200)
    if status == 413:
        assert response.json() == {
            "detail": "CSV file must be 1,048,576 bytes or fewer"
        }
