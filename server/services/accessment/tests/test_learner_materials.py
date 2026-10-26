"""Verify material grants and classroom routes with locked QR sign-in.

Author: Sandhya Tiwari
Date: 26 Oct 2026
Updated: Shuohui Liu, 26 Oct 2026
"""

import importlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from uuid import uuid4

import learner_materials as materials
import lesson_client
import pytest
from class_sessions import create_session_router
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient
from models import (
    attendance_records,
    class_sessions,
    learner_material_grants,
    session_lesson_links,
    signin_failures,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

NOW = datetime(2026, 10, 26, 0, tzinfo=UTC)


@pytest.fixture
def material_api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'access.sqlite'}")
    for table in (
        class_sessions,
        attendance_records,
        signin_failures,
        session_lesson_links,
        learner_material_grants,
    ):
        table.create(engine)
    factory = sessionmaker(engine)
    sid, lid = uuid4(), uuid4()
    with factory.begin() as db:
        db.execute(
            class_sessions.insert().values(
                id=sid, session_date=NOW.date(), created_by=uuid4()
            )
        )
        db.execute(session_lesson_links.insert().values(session_id=sid, lesson_id=lid))
    monkeypatch.setattr(materials, "now", lambda: NOW)
    def auth():
        raise HTTPException(401, "Login required")

    app = FastAPI()
    app.include_router(materials.create_materials_router(factory))
    app.include_router(create_session_router(factory, auth, lambda: NOW.date()))
    client = TestClient(app)
    response = Response()
    with factory.begin() as db:
        materials.issue_grant(db, sid, response)
    token = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    client.cookies.set(materials.COOKIE, token)
    yield SimpleNamespace(
        client=client,
        factory=factory,
        sid=sid,
        lid=lid,
        token=token,
        cookie=response.headers["set-cookie"],
        auth=auth,
        app=app,
    )
    client.close()
    engine.dispose()


def test_grant_is_random_hashed_httponly_and_not_a_staff_login(material_api):
    a = material_api
    assert len(a.token) == 43
    assert (
        "HttpOnly" in a.cookie
        and "SameSite=lax" in a.cookie
        and "Max-Age=86400" in a.cookie
    )
    with a.factory() as db:
        stored = db.execute(select(learner_material_grants)).mappings().one()
        assert stored["token_hash"] == materials.digest(a.token)
        assert a.token not in str(stored)
    assert (
        a.client.put(
            f"/sessions/{a.sid}/lesson", json={"lesson_id": str(a.lid)}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("token", [None, "", "guessed", "x" * 43, "x" * 257])
def test_no_access_without_valid_signin(material_api, token):
    a = material_api
    a.client.cookies.clear()
    if token:
        a.client.cookies.set(materials.COOKIE, token)
    reply = a.client.get("/learner/materials")
    assert reply.status_code == 401
    assert "file_name" not in reply.text
    assert (
        a.client.get(
            f"/learner/materials/{uuid4()}/download", follow_redirects=False
        ).headers["location"]
        == "/sign-in"
    )


@pytest.mark.parametrize(
    "hours,status", [(0, 200), (20, 200), (23.999, 200), (24, 401), (25, 401)]
)
def test_access_expires_at_24_hours_without_refreshing(
    material_api, monkeypatch, hours, status
):
    a = material_api
    monkeypatch.setattr(materials, "now", lambda: NOW + timedelta(hours=hours))
    monkeypatch.setattr(
        materials,
        "lesson_request",
        lambda path: (b'{"materials":[],"message":"No materials for today"}', {}),
    )
    reply = a.client.get("/learner/materials")
    assert reply.status_code == status
    assert "set-cookie" not in reply.headers


def test_listing_is_scoped_to_linked_lesson_and_no_personal_data(
    material_api, monkeypatch
):
    a = material_api
    paths = []

    def upstream(path):
        paths.append(path)
        return json.dumps(
            {
                "materials": [
                    {
                        "id": str(uuid4()),
                        "file_name": "Te reo Māori.pdf",
                        "file_size": 8,
                    }
                ],
                "message": "",
            }
        ).encode(), {}

    monkeypatch.setattr(materials, "lesson_request", upstream)
    reply = a.client.get("/learner/materials")
    assert reply.status_code == 200
    assert paths == [f"/internal/lessons/{a.lid}/shared-materials"]
    assert reply.json()["materials"][0]["file_name"] == "Te reo Māori.pdf"
    assert set(reply.json()) == {"session_date", "materials", "message"}


def test_no_link_never_calls_lesson_service(material_api, monkeypatch):
    a = material_api
    with a.factory.begin() as db:
        db.execute(session_lesson_links.delete())
    monkeypatch.setattr(
        materials,
        "lesson_request",
        lambda path: pytest.fail("No upstream request expected"),
    )
    assert (
        a.client.get("/learner/materials").json()["message"] == "No materials for today"
    )
    assert a.client.get(f"/learner/materials/{uuid4()}/download").status_code == 404


def test_hidden_review_message_passes_through(material_api, monkeypatch):
    monkeypatch.setattr(
        materials,
        "lesson_request",
        lambda path: (b'{"materials":[],"message":"Materials will be added soon"}', {}),
    )
    assert (
        material_api.client.get("/learner/materials").json()["message"]
        == "Materials will be added soon"
    )


def test_download_uses_grant_lesson_and_original_headers(material_api, monkeypatch):
    a = material_api
    mid = uuid4()

    def upstream(path):
        assert path == f"/internal/lessons/{a.lid}/shared-materials/{mid}"
        return b"%PDF-content", {
            "Content-Type": "application/pdf",
            "Content-Disposition": "attachment; filename*=UTF-8''M%C4%81ori.pdf",
            "Set-Cookie": "bad=value",
        }

    monkeypatch.setattr(materials, "lesson_request", upstream)
    reply = a.client.get(f"/learner/materials/{mid}/download")
    assert reply.content == b"%PDF-content"
    assert "M%C4%81ori.pdf" in reply.headers["content-disposition"]
    assert reply.headers["cache-control"] == "no-store"
    assert reply.headers["x-content-type-options"] == "nosniff"
    assert "set-cookie" not in reply.headers


def test_link_get_put_unlink_and_missing_session(material_api, monkeypatch):
    a = material_api
    a.app.dependency_overrides[a.auth] = lambda: SimpleNamespace(
        staff=SimpleNamespace(id=uuid4(), role="teacher"), authorization="Bearer teacher"
    )
    monkeypatch.setattr(lesson_client, "lesson_title", lambda *args: "Linked lesson")
    assert a.client.get(f"/sessions/{a.sid}/lesson").json() == {"lesson_id": str(a.lid)}
    other = uuid4()
    assert a.client.put(
        f"/sessions/{a.sid}/lesson", json={"lesson_id": str(other)}
    ).json()["lesson_id"] == str(other)
    assert a.client.put(
        f"/sessions/{a.sid}/lesson", json={"lesson_id": None}
    ).json()["lesson_id"] is None
    assert a.client.put(f"/sessions/{uuid4()}/lesson", json={}).status_code == 404
    assert a.client.get(f"/sessions/{uuid4()}/lesson").status_code == 404
    assert (
        a.client.put(f"/sessions/{a.sid}/lesson", json={"lesson_id": "bad"}).status_code
        == 422
    )


def test_failed_link_validation_keeps_existing_link(material_api, monkeypatch):
    a = material_api
    a.app.dependency_overrides[a.auth] = lambda: SimpleNamespace(
        staff=SimpleNamespace(id=uuid4(), role="teacher"), authorization="Bearer teacher"
    )

    def unavailable(*args):
        raise lesson_client.LessonUnavailableError()

    monkeypatch.setattr(lesson_client, "lesson_title", unavailable)
    assert (
        a.client.put(
            f"/sessions/{a.sid}/lesson", json={"lesson_id": str(uuid4())}
        ).status_code
        == 404
    )
    with a.factory() as db:
        assert (
            db.execute(select(session_lesson_links.c.lesson_id)).scalar_one() == a.lid
        )


@pytest.mark.parametrize(
    "failure,status",
    [
        (HTTPError("http://test", 404, "missing", {}, None), 404),
        (HTTPError("http://test", 403, "denied", {}, None), 503),
        (URLError("down"), 503),
        (TimeoutError(), 503),
    ],
)
def test_upstream_errors_fail_closed(monkeypatch, failure, status):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-key")

    def unavailable(*args, **kwargs):
        raise failure

    monkeypatch.setattr(materials, "urlopen", unavailable)
    with pytest.raises(HTTPException) as result:
        materials.lesson_request("/internal/test")
    assert result.value.status_code == status


def test_internal_key_required_and_forwarded(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    with pytest.raises(HTTPException):
        materials.lesson_request("/internal/test")
    monkeypatch.setenv("INTERNAL_API_KEY", "test-key")

    class Reply:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b"{}"

    def upstream(request, timeout):
        assert request.get_header("X-internal-key") == "test-key"
        assert timeout == 10
        return Reply()

    monkeypatch.setattr(materials, "urlopen", upstream)
    assert materials.lesson_request("/internal/test")[0] == b"{}"


def test_signin_mints_grant_in_same_transaction(material_api, monkeypatch):
    a = material_api
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module("app")
    monkeypatch.setattr(module, "SessionLocal", a.factory)
    monkeypatch.setattr(module, "club_today", lambda: NOW.date())
    checkin = SimpleNamespace(session_id=a.sid, session_date=NOW.date())
    monkeypatch.setattr(module, "open_checkin", lambda token, now: checkin)
    monkeypatch.setattr(
        module.user_client,
        "find_learner_for_sign_in",
        lambda first, last: {"id": str(uuid4())},
    )

    def signin(db, window, learner_id, today, *, now=None):
        db.execute(
            attendance_records.insert().values(
                session_id=window.session_id,
                learner_id=learner_id,
                status="present",
                recorded_by=uuid4(),
            )
        )

    monkeypatch.setattr(module, "sign_in", signin)
    client = TestClient(module.app)
    reply = client.post(
        "/checkin/test/sign-in", json={"first_name": "Aroha", "family_name": "Test"}
    )
    assert reply.status_code == 201 and "ako_materials=" in reply.headers["set-cookie"]
    with a.factory() as db:
        assert len(db.execute(select(attendance_records)).all()) == 1
    assert client.get("/learner/materials").status_code == 503  # no live Lesson service


def test_grants_random_cleanup_and_secure_cookie(material_api, monkeypatch):
    a = material_api
    monkeypatch.setattr(materials, "now", lambda: NOW + timedelta(days=2))
    response = Response()
    with a.factory.begin() as db:
        materials.issue_grant(db, a.sid, response, secure=True)
    assert "Secure" in response.headers["set-cookie"]
    with a.factory() as db:
        rows = db.execute(select(learner_material_grants)).mappings().all()
        assert len(rows) == 1
        assert rows[0]["token_hash"] != materials.digest(a.token)


def test_malformed_lesson_response_fails_closed(material_api, monkeypatch):
    monkeypatch.setattr(materials, "lesson_request", lambda path: (b"not json", {}))
    assert material_api.client.get("/learner/materials").status_code == 503


def test_signin_rolls_back_attendance_when_grant_cannot_be_saved(
    material_api, monkeypatch
):
    a = material_api
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module("app")
    monkeypatch.setattr(module, "SessionLocal", a.factory)
    monkeypatch.setattr(module, "club_today", lambda: NOW.date())
    monkeypatch.setattr(
        module,
        "open_checkin",
        lambda token, now: SimpleNamespace(session_id=a.sid, session_date=NOW.date()),
    )
    monkeypatch.setattr(
        module.user_client,
        "find_learner_for_sign_in",
        lambda first, last: {"id": str(uuid4())},
    )

    def signin(db, window, learner_id, today, *, now=None):
        db.execute(
            attendance_records.insert().values(
                session_id=window.session_id,
                learner_id=learner_id,
                status="present",
                recorded_by=uuid4(),
            )
        )

    def failed_grant(*args, **kwargs):
        raise RuntimeError("Database failure")

    monkeypatch.setattr(module, "sign_in", signin)
    monkeypatch.setattr(module, "issue_grant", failed_grant)
    client = TestClient(module.app, raise_server_exceptions=False)
    assert (
        client.post(
            "/checkin/test/sign-in",
            json={"first_name": "Test", "family_name": "Learner"},
        ).status_code
        == 500
    )
    with a.factory() as db:
        assert db.execute(select(attendance_records)).all() == []


def test_unauthenticated_material_responses_are_not_cacheable(
    material_api, monkeypatch
):
    a = material_api
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module("app")
    monkeypatch.setattr(module, "SessionLocal", a.factory)
    client = TestClient(module.app)
    response = client.get("/learner/materials")
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_closed_class_does_not_revoke_material_access(material_api, monkeypatch):
    a = material_api
    with a.factory.begin() as db:
        db.execute(
            class_sessions.update()
            .where(class_sessions.c.id == a.sid)
            .values(status="closed", closed_at=NOW)
        )
    monkeypatch.setattr(
        materials,
        "lesson_request",
        lambda path: (b'{"materials":[],"message":"No materials for today"}', {}),
    )
    assert a.client.get("/learner/materials").status_code == 200
