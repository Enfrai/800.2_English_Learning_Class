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
    def configure(raw, record) -> None:
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
