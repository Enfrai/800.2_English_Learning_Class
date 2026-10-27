"""Import integration checks against the identity-verified disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError
from test_learner_csv import document
from test_staff import add_coordinator, headers

from models import learners
from test_postgres import PgContext


def rows(pg: PgContext, name: str) -> list:
    """
    Prepare or exercise rows in the test learner import test scenario.
    """
    with pg.engine.connect() as db:
        return list(
            db.execute(
                select(learners).where(learners.c.family_name == name)
            ).mappings()
        )


def upload(
    pg: PgContext,
    token: str | None,
    content: bytes,
    filename: str = "learners.csv",
    replica: int = 0,
):
    """
    Prepare or exercise upload in the test learner import test scenario.
    """
    return pg.clients[replica].post(
        "/learners/import",
        headers=headers(token),
        files={"file": (filename, content, "text/csv")},
    )


def test_ac1_ten_persisted(pg: PgContext) -> None:
    """
    Verify that ac1 ten persisted.
    """
    actor, token = add_coordinator(pg)
    name = uuid4().hex
    response = upload(
        pg, token, document([[f"Fiction{i}", name, "", ""] for i in range(10)])
    )
    assert response.status_code == 200
    assert response.json() == {
        "imported_count": 10,
        "message": "10 learners imported",
        "duplicates": [],
        "errors": [],
    }
    saved = rows(pg, name)
    assert len(saved) == 10
    assert all(r["created_by"] == actor for r in saved)
    assert response.headers["cache-control"] == "no-store"


def test_ac2_database_and_file_duplicates(pg: PgContext) -> None:
    """
    Verify that ac2 database and file duplicates.
    """
    _, token = add_coordinator(pg)
    name = uuid4().hex
    content = document([["One", name, "", ""], ["Two", name, "", ""]])
    assert upload(pg, token, content).json()["imported_count"] == 2
    with pg.engine.begin() as db:
        db.execute(
            learners.update()
            .where(learners.c.family_name == name)
            .values(is_active=False)
        )
    response = upload(
        pg,
        token,
        document(
            [
                ["one", name.upper(), "", ""],
                ["Two", name, "", ""],
                ["New", name, "", ""],
                [" NEW ", name, "", ""],
            ]
        ),
    )
    result = response.json()
    assert result["imported_count"] == 1
    assert [d["source"] for d in result["duplicates"]] == [
        "database",
        "database",
        "file",
    ]
    assert [d["row_number"] for d in result["duplicates"]] == [2, 3, 5]
    assert len(rows(pg, name)) == 3


def test_ac3_ac4_partial_valid_rows(pg: PgContext) -> None:
    """
    Verify that ac3 ac4 partial valid rows.
    """
    _, token = add_coordinator(pg)
    name = uuid4().hex
    response = upload(
        pg,
        token,
        document(
            [["", name, "", ""], ["界" * 101, name, "", ""], ["Valid", name, "", ""]]
        ),
    )
    result = response.json()
    assert result["imported_count"] == 1
    assert [e["row_number"] for e in result["errors"]] == [2, 3]
    assert result["errors"][1]["message"] == "Name must be 100 characters or fewer"
    assert len(rows(pg, name)) == 1


@pytest.mark.parametrize(
    "kind,status",
    [("extension", 422), ("encoding", 422), ("size", 413), ("syntax", 422)],
)
def test_ac5_no_writes(pg: PgContext, kind: str, status: int) -> None:
    """
    Verify that ac5 no writes.
    """
    _, token = add_coordinator(pg)
    name = uuid4().hex
    content = document([["Valid", name, "", ""]])
    filename = "a.csv"
    if kind == "extension":
        filename = "a.txt"
    if kind == "encoding":
        content += b"\xff"
    if kind == "size":
        content += b" " * 1_048_576
    if kind == "syntax":
        content += b'"unclosed'
    assert upload(pg, token, content, filename).status_code == status
    assert rows(pg, name) == []


@pytest.mark.parametrize("actor,status", [("anonymous", 401), ("teacher", 403)])
def test_permissions(pg: PgContext, actor: str, status: int) -> None:
    """
    Verify that permissions.
    """
    token = pg.login(0).json()["sessionid"] if actor == "teacher" else None
    response = upload(pg, token, document([]))
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "origin,status",
    [(None, 403), ("https://evil.invalid", 403), ("http://testserver", 200)],
)
def test_cookie_csrf(pg: PgContext, origin: str | None, status: int) -> None:
    """
    Verify that cookie csrf.
    """
    _, token = add_coordinator(pg)
    name = uuid4().hex
    request_headers = {"Cookie": f"ako_session={token}"}
    if origin:
        request_headers["Origin"] = origin
    response = pg.clients[0].post(
        "/learners/import",
        headers=request_headers,
        files={"file": ("a.csv", document([["Valid", name, "", ""]]), "text/csv")},
    )
    assert response.status_code == status
    assert len(rows(pg, name)) == int(status == 200)


def test_database_failure_rolls_back_batch(pg: PgContext) -> None:
    """
    Verify that database failure rolls back batch.
    """
    _, token = add_coordinator(pg)
    name = uuid4().hex
    inserted = 0

    def fail_second(conn, cursor, statement, parameters, context, executemany):
        """
        Fail the second learner write to verify that the import batch rolls back.
        """
        nonlocal inserted
        if statement.startswith("INSERT INTO learners"):
            inserted += 1
            if inserted == 2:
                raise OperationalError("hidden", {}, Exception("test failure"))

    event.listen(pg.engine, "before_cursor_execute", fail_second)
    try:
        response = upload(
            pg, token, document([["One", name, "", ""], ["Two", name, "", ""]])
        )
    finally:
        event.remove(pg.engine, "before_cursor_execute", fail_second)
    assert response.status_code == 500
    assert "No learners were imported" in response.json()["detail"]
    assert rows(pg, name) == []


def test_concurrent_imports_across_replicas(pg: PgContext) -> None:
    """
    Verify that concurrent imports across replicas.
    """
    _, token = add_coordinator(pg)
    content = document([["Concurrent", uuid4().hex, "", ""]])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda replica: upload(pg, token, content, replica=replica), [0, 1]
            )
        )
    assert all(r.status_code == 200 for r in results)
    assert sorted(r.json()["imported_count"] for r in results) == [0, 1]
