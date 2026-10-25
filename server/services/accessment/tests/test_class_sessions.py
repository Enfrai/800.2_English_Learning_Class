"""Verify daily classroom creation, lesson links, deletion and additive upgrades.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import importlib
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import lesson_client
import pytest
from class_sessions import create_session_router
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from models import (
    Base,
    attendance_records,
    checkin_windows,
    class_sessions,
    session_lesson_links,
)
from schema import prepare_schema
from sqlalchemy import CheckConstraint, MetaData, create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

TODAY = date(2026, 10, 26)
STAFF_ID = uuid4()
LESSON_ID = uuid4()


def schema_metadata() -> MetaData:
    """Copy the schema; PostgreSQL-only interval checks and audit DDL stay in PG tests."""
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        cloned = table.to_metadata(metadata)
        for constraint in list(cloned.constraints):
            if isinstance(constraint, CheckConstraint) and "INTERVAL" in str(
                constraint.sqltext
            ):
                cloned.constraints.remove(constraint)
    return metadata


@dataclass
class ClassApi:
    client: TestClient
    factory: sessionmaker
    engine: Any
    titles: dict[UUID, str]

    def start(self, day: date | None = None, who: str = "teacher") -> Response:
        if day is None:
            return self.client.post("/sessions/today", headers={"Authorization": who})
        return self.client.post(
            "/sessions",
            headers={"Authorization": who},
            json={"session_date": day.isoformat()},
        )

    def detail(self, session_id: str) -> Response:
        return self.client.get(
            f"/sessions/{session_id}", headers={"Authorization": "teacher"}
        )

    def link(self, session_id: str, lesson_id: UUID | None = LESSON_ID) -> Response:
        return self.client.put(
            f"/sessions/{session_id}/lesson",
            headers={"Authorization": "teacher"},
            json={"lesson_id": str(lesson_id) if lesson_id else None},
        )

    def delete(self, session_id: str) -> Response:
        return self.client.delete(
            f"/sessions/{session_id}", headers={"Authorization": "teacher"}
        )

    def attendance(self, session_id: str, status: str = "present") -> UUID:
        with self.factory.begin() as db:
            return db.execute(
                attendance_records.insert()
                .values(
                    session_id=UUID(session_id),
                    learner_id=uuid4(),
                    status=status,
                    recorded_by=STAFF_ID,
                )
                .returning(attendance_records.c.id)
            ).scalar_one()


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ClassApi]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'access.sqlite'}", connect_args={"timeout": 10}
    )

    @event.listens_for(engine, "connect")
    def sqlite_rules(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    metadata = schema_metadata()
    metadata.create_all(engine)
    factory = sessionmaker(engine)
    titles = {LESSON_ID: "Te reo Māori transport"}

    def staff(authorization: str | None = Header(default=None)) -> Any:
        if authorization is None:
            raise HTTPException(401, "Login required")
        return SimpleNamespace(
            staff=SimpleNamespace(id=STAFF_ID, role=authorization),
            authorization=authorization,
        )

    def one_lesson(identifier: UUID, authorization: str) -> str:
        assert authorization in ("teacher", "coordinator")
        if identifier not in titles:
            raise lesson_client.LessonUnavailableError()
        return titles[identifier]

    monkeypatch.setattr(lesson_client, "lesson_title", one_lesson)
    monkeypatch.setattr(
        lesson_client, "lesson_titles", lambda authorization: titles.copy()
    )
    app = FastAPI()
    app.include_router(create_session_router(factory, staff, lambda: TODAY))
    with TestClient(app) as client:
        yield ClassApi(client, factory, engine, titles)
    engine.dispose()


def test_start_today_creates_and_opens_in_under_two_seconds(api: ClassApi) -> None:
    from time import monotonic

    start = monotonic()
    response = api.start()
    assert response.status_code == 200, response.text
    assert (
        response.json()["created"]
        and response.json()["session_date"] == TODAY.isoformat()
    )
    assert api.detail(response.json()["id"]).status_code == 200
    assert monotonic() - start < 2


@pytest.mark.parametrize("role", ["teacher", "coordinator"])
def test_both_staff_roles_manage_shared_classes(api: ClassApi, role: str) -> None:
    session = api.start(who=role).json()
    linked = api.client.put(
        f"/sessions/{session['id']}/lesson",
        headers={"Authorization": role},
        json={"lesson_id": str(LESSON_ID)},
    )
    assert linked.status_code == 200
    assert (
        api.client.delete(
            f"/sessions/{session['id']}", headers={"Authorization": role}
        ).status_code
        == 204
    )


def test_repeat_click_opens_existing_id_without_changing_owner_or_lesson(
    api: ClassApi,
) -> None:
    first = api.start().json()
    api.link(first["id"])
    again = api.start(who="coordinator").json()
    assert again["id"] == first["id"] and again["created"] is False
    assert api.detail(first["id"]).json()["lesson_id"] == str(LESSON_ID)
    with api.factory() as db:
        assert len(db.execute(select(class_sessions)).all()) == 1
        assert db.execute(select(class_sessions.c.created_by)).scalar_one() == STAFF_ID


def test_simultaneous_starts_keep_one_date_and_one_id(api: ClassApi) -> None:
    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(lambda _: api.start().json(), range(6)))
    assert len({reply["id"] for reply in results}) == 1
    assert sum(reply["created"] for reply in results) == 1


def test_database_itself_rejects_duplicate_dates(api: ClassApi) -> None:
    api.start()
    with pytest.raises(IntegrityError), api.factory.begin() as db:
        db.execute(
            class_sessions.insert().values(session_date=TODAY, created_by=uuid4())
        )


def test_list_is_newest_first_and_shows_dates_and_current_lesson_titles(
    api: ClassApi,
) -> None:
    for offset in [2, 0, 1]:
        session = api.start(TODAY - timedelta(days=offset)).json()
        assert api.link(session["id"]).status_code == 200
    reply = api.client.get("/sessions", headers={"Authorization": "teacher"})
    assert reply.status_code == 200
    rows = reply.json()["sessions"]
    assert [item["session_date"] for item in rows] == [
        (TODAY - timedelta(days=offset)).isoformat() for offset in range(3)
    ]
    assert all(item["lesson_title"] == "Te reo Māori transport" for item in rows)
    api.titles[LESSON_ID] = "Updated Māori title"
    assert (
        api.client.get("/sessions", headers={"Authorization": "teacher"}).json()[
            "sessions"
        ][0]["lesson_title"]
        == "Updated Māori title"
    )


def test_link_replace_and_unlink_do_not_modify_lesson_content(api: ClassApi) -> None:
    sid = api.start().json()["id"]
    before = api.titles.copy()
    response = api.link(sid)
    assert response.json()["lesson_title"] == before[LESSON_ID]
    assert api.titles == before
    replacement = uuid4()
    api.titles[replacement] = "Health"
    assert api.link(sid, replacement).json()["lesson_id"] == str(replacement)
    assert api.link(sid, None).json()["lesson_id"] is None
    assert api.client.get(
        f"/sessions/{sid}/lesson", headers={"Authorization": "teacher"}
    ).json() == {"lesson_id": None}


def test_missing_or_deleted_lesson_preserves_class_and_attendance(
    api: ClassApi,
) -> None:
    sid = api.start().json()["id"]
    assert api.link(sid).status_code == 200
    api.attendance(sid)
    api.titles.clear()
    response = api.detail(sid).json()
    assert response["lesson_unavailable"] and response["lesson_title"] is None
    assert response["attendance_count"] == 1
    assert api.link(sid, uuid4()).status_code == 404
    assert api.detail(sid).json()["lesson_id"] == str(LESSON_ID)


@pytest.mark.parametrize("status", ["present", "absent"])
def test_any_attendance_blocks_deletion_with_exact_message(
    api: ClassApi, status: str
) -> None:
    sid = api.start().json()["id"]
    api.attendance(sid, status)
    response = api.delete(sid)
    assert response.status_code == 409
    assert (
        response.json()["detail"] == "This session has attendance and cannot be deleted"
    )
    assert api.detail(sid).json()["can_delete"] is False


def test_empty_class_and_related_qr_links_can_be_deleted_but_lesson_stays(
    api: ClassApi,
) -> None:
    sid = api.start().json()["id"]
    api.link(sid)
    with api.factory.begin() as db:
        db.execute(
            checkin_windows.insert().values(
                session_id=UUID(sid),
                token_hash="token-hash",
                opened_by=STAFF_ID,
                opened_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
    response = api.delete(sid)
    assert response.status_code == 204 and response.content == b""
    assert api.detail(sid).status_code == 404
    assert LESSON_ID in api.titles
    with api.factory() as db:
        assert db.execute(select(session_lesson_links)).all() == []
        assert db.execute(select(checkin_windows)).all() == []
    assert api.start().json()["created"]


def test_future_invalid_and_missing_dates_save_nothing(api: ClassApi) -> None:
    response = api.start(TODAY + timedelta(days=1))
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "Date cannot be in the future"
    for payload in [
        {},
        {"session_date": "bad"},
        {"session_date": "2026-02-30"},
        {"session_date": "2026-10-26", "created_by": str(STAFF_ID)},
    ]:
        assert (
            api.client.post(
                "/sessions", headers={"Authorization": "teacher"}, json=payload
            ).status_code
            == 422
        )
    with api.factory() as db:
        assert db.execute(select(class_sessions)).all() == []


@pytest.mark.parametrize("who", [None, "learner", "visitor", "admin"])
def test_anonymous_and_nonstaff_are_denied_before_data_lookup(
    api: ClassApi, who: str | None
) -> None:
    expected = 401 if who is None else 403
    headers = {} if who is None else {"Authorization": who}
    for method, path, body in [
        ("GET", "/sessions", None),
        ("POST", "/sessions/today", None),
        ("POST", "/sessions", {"session_date": TODAY.isoformat()}),
        ("GET", f"/sessions/{uuid4()}", None),
        ("PUT", f"/sessions/{uuid4()}/lesson", {"lesson_id": None}),
        ("DELETE", f"/sessions/{uuid4()}", None),
    ]:
        assert (
            api.client.request(method, path, headers=headers, json=body).status_code
            == expected
        )


def test_missing_session_and_malformed_ids_are_clear(api: ClassApi) -> None:
    for method, suffix, body in [
        ("GET", "", None),
        ("DELETE", "", None),
        ("PUT", "/lesson", {"lesson_id": None}),
        ("GET", "/lesson", None),
    ]:
        assert (
            api.client.request(
                method,
                f"/sessions/{uuid4()}{suffix}",
                headers={"Authorization": "teacher"},
                json=body,
            ).status_code
            == 404
        )
    assert api.detail("invalid").status_code == 422


def test_lesson_service_failure_does_not_erase_existing_link(
    api: ClassApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid = api.start().json()["id"]
    api.link(sid)

    def unavailable(*args):
        raise lesson_client.LessonServiceError()

    monkeypatch.setattr(lesson_client, "lesson_title", unavailable)
    assert api.link(sid).status_code == 503
    monkeypatch.setattr(lesson_client, "lesson_titles", unavailable)
    assert api.detail(sid).status_code == 503
    assert (
        api.client.get("/sessions", headers={"Authorization": "teacher"}).status_code
        == 503
    )
    # Starting today's class never depends on the Lesson service responding.
    assert api.start().json()["id"] == sid
    with api.factory() as db:
        assert db.scalar(select(session_lesson_links.c.lesson_id)) == LESSON_ID


def test_schema_upgrade_preserves_existing_rows_and_is_repeatable(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.sqlite'}")
    metadata = schema_metadata()
    table = metadata.tables["class_sessions"]
    for index in list(table.indexes):
        if index.name == "uq_class_sessions_date":
            table.indexes.remove(index)
    table.create(engine)
    sid = uuid4()
    with engine.begin() as connection:
        connection.execute(
            class_sessions.insert().values(
                id=sid, session_date=TODAY, created_by=STAFF_ID
            )
        )
    prepare_schema(engine, metadata)
    prepare_schema(engine, metadata)
    assert "session_lesson_links" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(select(class_sessions.c.id)).scalar_one() == sid
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            class_sessions.insert().values(session_date=TODAY, created_by=STAFF_ID)
        )
    engine.dispose()


def test_legacy_duplicate_dates_fail_without_deleting_data(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'duplicates.sqlite'}")
    metadata = schema_metadata()
    table = metadata.tables["class_sessions"]
    for index in list(table.indexes):
        if index.name == "uq_class_sessions_date":
            table.indexes.remove(index)
    table.create(engine)
    with engine.begin() as connection:
        for _ in range(2):
            connection.execute(
                class_sessions.insert().values(session_date=TODAY, created_by=STAFF_ID)
            )
    with pytest.raises(RuntimeError, match="Duplicate class dates"):
        prepare_schema(engine, metadata)
    with engine.connect() as connection:
        assert len(connection.execute(select(class_sessions)).all()) == 2
    engine.dispose()


def test_attendance_and_deletion_use_the_same_class_row_lock() -> None:
    from attendance import check_session_is_running
    from corrections import _session_date
    from sqlalchemy.dialects import postgresql

    class Result:
        def scalar_one_or_none(self):
            return TODAY

    class Database:
        statement = None

        def execute(self, statement):
            self.statement = statement
            return Result()

    for check in [
        lambda db: check_session_is_running(db, uuid4(), TODAY),
        lambda db: _session_date(db, uuid4()),
    ]:
        db = Database()
        check(db)
        assert "FOR UPDATE" in str(db.statement.compile(dialect=postgresql.dialect()))


def test_app_uses_auckland_date_at_utc_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module("app")

    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 25, 12, 30, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(module, "datetime", Clock)
    assert module.club_today() == date(2026, 10, 26)


def test_actual_app_links_creation_attendance_and_deletion(
    api: ClassApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    import user_client

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module("app")
    monkeypatch.setattr(module, "SessionLocal", api.factory)
    monkeypatch.setattr(module, "club_today", lambda: TODAY)
    monkeypatch.setattr(
        user_client,
        "current_staff",
        lambda authorization: user_client.Staff(STAFF_ID, "Test teacher", "teacher"),
    )
    monkeypatch.setattr(user_client, "learner_exists", lambda *args: True)
    client = TestClient(module.app)
    sid = client.post(
        "/sessions/today", headers={"Authorization": "Bearer teacher"}
    ).json()["id"]
    marked = client.post(
        f"/sessions/{sid}/attendance",
        headers={"Authorization": "Bearer teacher"},
        json={"learner_id": str(uuid4())},
    )
    assert marked.status_code == 201
    assert (
        client.get(
            f"/sessions/{sid}/attendance", headers={"Authorization": "Bearer teacher"}
        ).json()["present_count"]
        == 1
    )
    protected = client.delete(
        f"/sessions/{sid}", headers={"Authorization": "Bearer teacher"}
    )
    assert protected.status_code == 409
    assert protected.headers["cache-control"] == "no-store"
    assert protected.headers["x-content-type-options"] == "nosniff"
    past = client.post(
        "/sessions",
        headers={"Authorization": "Bearer teacher"},
        json={"session_date": "2026-10-20"},
    ).json()["id"]
    assert (
        client.post(
            f"/sessions/{past}/attendance",
            headers={"Authorization": "Bearer teacher"},
            json={"learner_id": str(uuid4())},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/sessions/{past}/corrections",
            headers={"Authorization": "Bearer teacher"},
            json={"learner_id": str(uuid4()), "present": True},
        ).status_code
        == 403
    )
