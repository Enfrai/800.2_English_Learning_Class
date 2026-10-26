"""Verify learner history, inclusive filters, corrections and authenticated access.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import attendance_history as history
import pytest
import user_client
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from models import attendance_records, class_sessions
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.sqlite'}")
    class_sessions.create(engine)
    attendance_records.create(engine)
    factory = sessionmaker(engine)
    learner, other = uuid4(), uuid4()
    sessions = [uuid4() for _ in range(9)]
    with factory.begin() as db:
        for i, sid in enumerate(sessions):
            db.execute(
                class_sessions.insert().values(
                    id=sid,
                    session_date=date(2026, 10, 19 + i),
                    created_by=uuid4(),
                    status="scheduled",
                )
            )
        for i in (1, 3, 5):
            db.execute(
                attendance_records.insert().values(
                    session_id=sessions[i],
                    learner_id=learner,
                    status="present",
                    recorded_by=uuid4(),
                )
            )
        db.execute(
            attendance_records.insert().values(
                session_id=sessions[2],
                learner_id=learner,
                status="absent",
                recorded_by=uuid4(),
            )
        )
        db.execute(
            attendance_records.insert().values(
                session_id=sessions[4],
                learner_id=other,
                status="present",
                recorded_by=uuid4(),
            )
        )
    body = {
        "id": str(learner),
        "first_name": "Māia",
        "family_name": "Example",
        "created_at": "2026-10-19T12:00:00Z",
        "contact": "private@example.test",
    }
    calls = []

    def request(method, path, authorization):
        calls.append((method, path, authorization))
        return 200, body.copy()

    monkeypatch.setattr(user_client, "_request", request)

    def staff(authorization: str | None = Header(default=None)):
        if not authorization or authorization == "Bearer expired":
            raise HTTPException(401, "Login required")
        return SimpleNamespace(
            staff=SimpleNamespace(role=authorization.removeprefix("Bearer ")),
            authorization=authorization,
        )

    app = FastAPI()
    app.include_router(
        history.create_history_router(
            factory, staff, lambda: date(2026, 10, 26), ZoneInfo("Pacific/Auckland")
        )
    )
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            factory=factory,
            engine=engine,
            learner=learner,
            other=other,
            sessions=sessions,
            body=body,
            calls=calls,
        )
    engine.dispose()


def get(api, role="coordinator", **params):
    return api.client.get(
        f"/learners/{api.learner}/attendance-history",
        params=params,
        headers={"Authorization": f"Bearer {role}"},
    )


def test_ac1_three_of_five_newest_first_and_minimal_data(api):
    response = get(api, end_date="2026-10-24")
    body = response.json()
    assert response.status_code == 200
    assert (body["present_count"], body["total_count"]) == (3, 5)
    assert [r["session_date"] for r in body["sessions"]] == [
        f"2026-10-{d}" for d in range(24, 19, -1)
    ]
    assert [r["status"] for r in body["sessions"]] == [
        "Present",
        "Absent",
        "Present",
        "Absent",
        "Present",
    ]
    assert body["learner"] == {"id": str(api.learner), "name": "Māia Example"}
    assert "private@example.test" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert api.calls == [("GET", f"/learners/{api.learner}", "Bearer coordinator")]


@pytest.mark.parametrize(
    "params,present,total",
    [
        ({"start_date": "2026-10-21", "end_date": "2026-10-23"}, 1, 3),
        ({"start_date": "2026-10-20", "end_date": "2026-10-20"}, 1, 1),
        ({"start_date": "2026-10-24"}, 1, 2),
        ({"end_date": "2026-10-21"}, 1, 2),
        ({"start_date": "2026-11-01"}, 0, 0),
        ({"end_date": "2026-10-01"}, 0, 0),
        ({}, 3, 6),
    ],
)
def test_ac2_optional_inclusive_dates_and_matching_counts(api, params, present, total):
    body = get(api, **params).json()
    assert (body["present_count"], body["total_count"]) == (present, total)
    assert body["has_records"] is True


def test_ac3_no_records_is_empty_even_if_other_learners_attended(api):
    with api.factory.begin() as db:
        db.execute(
            attendance_records.delete().where(
                attendance_records.c.learner_id == api.learner
            )
        )
    body = get(api).json()
    assert body["has_records"] is False
    assert body["sessions"] == []
    assert body["total_count"] == body["present_count"] == 0


def test_absent_only_history_is_not_unrecorded(api):
    with api.factory.begin() as db:
        db.execute(
            attendance_records.update()
            .where(attendance_records.c.learner_id == api.learner)
            .values(status="absent")
        )
    body = get(api).json()
    assert body["has_records"] is True
    assert (body["present_count"], body["total_count"]) == (0, 6)


def test_ac4_teacher_reads_same_history_and_cannot_write(api):
    assert get(api, "teacher").json() == get(api).json()
    for method in ("post", "put", "patch", "delete"):
        assert (
            getattr(api.client, method)(
                f"/learners/{api.learner}/attendance-history",
                headers={"Authorization": "Bearer teacher"},
            ).status_code
            == 405
        )


@pytest.mark.parametrize("role", ["learner", "visitor", "admin", "unknown"])
def test_other_roles_denied_before_learner_lookup(api, role):
    assert get(api, role).status_code == 403
    assert not api.calls


def test_anonymous_and_expired_denied(api):
    assert (
        api.client.get(f"/learners/{api.learner}/attendance-history").status_code == 401
    )
    assert get(api, "expired").status_code == 401
    assert not api.calls


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2026-10-24", "end_date": "2026-10-20"},
        {"start_date": "invalid"},
        {"end_date": "2026-02-30"},
        {"start_date": ""},
        {"end_date": "2026-10-24T12:00:00Z"},
    ],
)
def test_invalid_dates_rejected_before_lookup(api, params):
    assert get(api, **params).status_code == 422
    assert not api.calls


def test_invalid_identifier(api):
    assert (
        api.client.get(
            "/learners/bad/attendance-history",
            headers={"Authorization": "Bearer teacher"},
        ).status_code
        == 422
    )
    assert not api.calls


def test_today_waits_for_close_future_never_counts(api):
    assert get(api).json()["total_count"] == 6
    with api.factory.begin() as db:
        db.execute(
            class_sessions.update()
            .where(class_sessions.c.id.in_(api.sessions[7:]))
            .values(status="closed")
        )
    body = get(api).json()
    assert body["total_count"] == 7
    assert body["sessions"][0]["session_date"] == "2026-10-26"


def test_correction_and_removal_refresh_counts(api):
    with api.factory.begin() as db:
        db.execute(
            attendance_records.update()
            .where(attendance_records.c.session_id == api.sessions[2])
            .values(status="present")
        )
    assert get(api).json()["present_count"] == 4
    with api.factory.begin() as db:
        db.execute(
            attendance_records.delete().where(
                attendance_records.c.session_id == api.sessions[2]
            )
        )
    assert get(api).json()["present_count"] == 3


def test_explicit_records_before_creation_survive_but_unrelated_classes_do_not(api):
    api.body["created_at"] = "2026-10-25T00:00:00+13:00"
    body = get(api).json()
    assert body["total_count"] == 5
    assert "2026-10-23" not in [r["session_date"] for r in body["sessions"]]


def test_single_select_without_database_mutation(api):
    queries = []

    def capture(conn, cursor, statement, parameters, context, many):
        queries.append(statement)

    event.listen(api.engine, "before_cursor_execute", capture)
    get(api)
    event.remove(api.engine, "before_cursor_execute", capture)
    assert len(queries) == 1
    assert queries[0].lstrip().upper().startswith("SELECT")


@pytest.mark.parametrize(
    "status,expected", [(401, 401), (404, 404), (403, 503), (500, 503), (200, 503)]
)
def test_safe_upstream_errors(api, monkeypatch, status, expected):
    monkeypatch.setattr(
        user_client,
        "_request",
        lambda *a: (status, {"detail": "private database details"}),
    )
    response = get(api)
    assert response.status_code == expected
    assert "private database details" not in response.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", str(uuid4())),
        ("first_name", None),
        ("family_name", ""),
        ("created_at", "bad"),
        ("created_at", "2026-10-20T00:00:00"),
    ],
)
def test_invalid_learner_response(api, field, value):
    api.body[field] = value
    assert get(api).status_code == 503


def test_offline_user_service(api, monkeypatch):
    def offline(*args):
        raise user_client.UserServiceError("private endpoint")

    monkeypatch.setattr(user_client, "_request", offline)
    response = get(api)
    assert response.status_code == 503
    assert "private endpoint" not in response.text


def test_inactive_learner_history_is_kept(api):
    api.body["is_active"] = False
    assert get(api).status_code == 200


def test_real_application_registers_history_and_no_store_for_denials(api, monkeypatch):
    import importlib

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    application = importlib.import_module("app")
    monkeypatch.setattr(application, "prepare_schema", lambda engine: None)
    with TestClient(application.app) as client:
        response = client.get(f"/learners/{api.learner}/attendance-history")
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
    paths = application.app.openapi()["paths"]
    assert "/learners/{learner_id}/attendance-history" in paths
