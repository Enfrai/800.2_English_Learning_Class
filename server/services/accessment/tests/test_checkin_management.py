"""Verify US-011 window lifecycle, QR isolation, role checks and sign-in races.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import importlib
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import checkin_management as management
import pytest
import user_client
from checkin import (
    CheckinClosedError,
    CheckinExpiredError,
    CheckinUnavailableError,
    find_open_checkin,
    hash_token,
    sign_in,
)
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from models import (
    attendance_records,
    checkin_windows,
    class_sessions,
    learner_material_grants,
)
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from test_class_sessions import schema_metadata

DAY = date(2026, 10, 26)
NOW = datetime(2026, 10, 26, 0, tzinfo=UTC)
OWNER = uuid4()


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKIN_TOKEN_SECRET", "a-shared-random-test-secret")
    monkeypatch.setenv("CHECKIN_PUBLIC_ORIGIN", "http://192.168.1.20:8080")
    monkeypatch.setenv("CLUB_TIMEZONE", "Pacific/Auckland")
    engine = create_engine(f"sqlite:///{tmp_path / 'qr.sqlite'}")
    schema_metadata().create_all(engine)
    factory = sessionmaker(engine)
    sid = uuid4()
    with factory.begin() as db:
        db.execute(
            class_sessions.insert().values(id=sid, session_date=DAY, created_by=OWNER)
        )
    clock = [NOW]

    def today():
        return clock[0].astimezone(ZoneInfo("Pacific/Auckland")).date()

    def staff(authorization: str | None = Header(default=None)):
        if not authorization:
            raise HTTPException(401, "Login required")
        return SimpleNamespace(
            staff=SimpleNamespace(id=OWNER, role=authorization),
            authorization=authorization,
        )

    app = FastAPI()
    app.include_router(
        management.create_checkin_router(factory, staff, today, lambda: clock[0])
    )
    client = TestClient(app)

    def call(method="GET", identifier=None, role="teacher"):
        return client.request(
            method,
            f"/sessions/{identifier or sid}/check-in",
            headers={"Authorization": role} if role else {},
        )

    yield SimpleNamespace(
        client=client,
        factory=factory,
        sid=sid,
        clock=clock,
        today=today,
        call=call,
        engine=engine,
    )
    client.close()
    engine.dispose()


def token(data):
    return data["sign_in_url"].rsplit("/", 1)[1]


def test_open_displays_scannable_svg_and_link_within_two_seconds(api):
    begin = monotonic()
    response = api.call("POST")
    assert monotonic() - begin < 2
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "open" and data["can_open"]
    assert data["session_date"] == DAY.isoformat()
    assert data["sign_in_url"].startswith("http://192.168.1.20:8080/sign-in/")
    assert len(token(data)) == 43 and DAY.isoformat() not in data["sign_in_url"]
    svg = ET.fromstring(data["qr_svg"])
    assert svg.tag.endswith("svg")
    assert svg.find("{http://www.w3.org/2000/svg}path") is not None
    with api.factory() as db:
        row = db.execute(select(checkin_windows)).mappings().one()
        assert row["token_hash"] == hash_token(token(data))
        assert token(data) not in str(row)


def test_status_and_repeated_open_reuse_token_owner_and_expiry(api):
    first = api.call("POST").json()
    api.clock[0] += timedelta(minutes=30)
    assert api.call().json()["sign_in_url"] == first["sign_in_url"]
    again = api.call("POST", role="coordinator").json()
    assert (
        again["sign_in_url"] == first["sign_in_url"]
        and again["expires_at"] == first["expires_at"]
    )
    with api.factory() as db:
        assert len(db.execute(select(checkin_windows)).all()) == 1


def test_replicas_can_recover_same_token_without_storing_it(api):
    first = api.call("POST").json()
    with api.factory() as db:
        window = db.execute(select(checkin_windows)).mappings().one()
    assert management.token_for(window["id"], api.sid) == token(first)
    other = uuid4()
    assert management.token_for(window["id"], other) != token(first)


def test_different_class_codes_never_cross_sessions(api):
    first = api.call("POST").json()
    other = uuid4()
    # Model permits only one class per date; another school day gets its own code.
    with api.factory.begin() as db:
        db.execute(
            class_sessions.insert().values(
                id=other, session_date=DAY + timedelta(days=1), created_by=OWNER
            )
        )
    api.clock[0] += timedelta(days=1)
    second = api.call("POST", other).json()
    assert token(first) != token(second)
    with api.factory() as db:
        found = find_open_checkin(
            db, token(second), now=api.clock[0], today=api.today()
        )
        assert found.session_id == other
        with pytest.raises(CheckinUnavailableError):
            find_open_checkin(db, token(first), now=api.clock[0], today=api.today())


def test_close_is_immediate_idempotent_and_reopening_invalidates_old_token(api):
    first = api.call("POST").json()
    assert api.call("DELETE").json()["state"] == "closed"
    assert api.call("DELETE").json()["state"] == "closed"
    with api.factory() as db:
        with pytest.raises(CheckinClosedError):
            find_open_checkin(db, token(first), now=NOW, today=DAY)
    second = api.call("POST").json()
    assert second["state"] == "open"
    assert token(first) != token(second)
    assert api.call().json()["sign_in_url"] == second["sign_in_url"]


def test_exact_four_hour_boundary_and_new_open_does_not_revive_old_code(api):
    first = api.call("POST").json()
    api.clock[0] = NOW + timedelta(hours=3, minutes=59, seconds=59)
    assert api.call().json()["state"] == "open"
    api.clock[0] = NOW + timedelta(hours=4)
    result = api.call().json()
    assert result["state"] == "expired" and result["qr_svg"] is None
    with api.factory() as db:
        with pytest.raises(CheckinExpiredError):
            find_open_checkin(db, token(first), now=api.clock[0], today=DAY)
    assert token(api.call("POST").json()) != token(first)


def test_club_midnight_is_an_earlier_deadline(api):
    api.clock[0] = datetime(2026, 10, 26, 10, 50, tzinfo=UTC)
    data = api.call("POST").json()
    assert datetime.fromisoformat(data["expires_at"]) == datetime(
        2026, 10, 26, 11, tzinfo=UTC
    )
    api.clock[0] += timedelta(minutes=10)
    assert api.call().json()["state"] == "expired"
    assert api.call("POST").status_code == 409


@pytest.mark.parametrize("offset", [-1, 1])
def test_non_today_class_cannot_open(api, offset):
    other = uuid4()
    with api.factory.begin() as db:
        db.execute(
            class_sessions.insert().values(
                id=other, session_date=DAY + timedelta(days=offset), created_by=OWNER
            )
        )
    assert not api.call(identifier=other).json()["can_open"]
    assert api.call("POST", other).status_code == 409


def test_closed_class_cannot_open_or_keep_valid_link(api):
    data = api.call("POST").json()
    with api.factory.begin() as db:
        db.execute(class_sessions.update().values(status="closed"))
    assert api.call("POST").status_code == 409
    with api.factory() as db:
        with pytest.raises(CheckinClosedError):
            find_open_checkin(db, token(data), now=NOW, today=DAY)


@pytest.mark.parametrize(
    "role,status", [(None, 401), ("learner", 403), ("visitor", 403), ("admin", 403)]
)
def test_unauthorized_staff_calls_never_read_or_write(api, role, status):
    statements = []

    def trace(*args):
        statements.append(args[2])

    event.listen(api.engine, "before_cursor_execute", trace)
    try:
        for method in ("GET", "POST", "DELETE"):
            assert api.call(method, role=role).status_code == status
    finally:
        event.remove(api.engine, "before_cursor_execute", trace)
    assert statements == []


@pytest.mark.parametrize("role", ["teacher", "coordinator"])
def test_both_staff_roles_manage_checkin(api, role):
    assert api.call("POST", role=role).status_code == 200
    assert api.call("GET", role=role).json()["state"] == "open"
    assert api.call("DELETE", role=role).json()["state"] == "closed"


@pytest.mark.parametrize(
    "origin",
    [
        "javascript:alert(1)",
        "http://user:pass@host",
        "https://host/path",
        "https://host?x=y",
        "https://host#",
        "http://host:invalid",
        " https://host",
    ],
)
def test_bad_deployment_origin_saves_no_window(api, monkeypatch, origin):
    monkeypatch.setenv("CHECKIN_PUBLIC_ORIGIN", origin)
    assert api.call("POST").status_code == 503
    with api.factory() as db:
        assert db.execute(select(checkin_windows)).all() == []


def test_missing_secret_and_rotated_secret_fail_safely(api, monkeypatch):
    monkeypatch.delenv("CHECKIN_TOKEN_SECRET")
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    assert api.call("POST").status_code == 503
    monkeypatch.setenv("CHECKIN_TOKEN_SECRET", "first-key")
    api.call("POST")
    monkeypatch.setenv("CHECKIN_TOKEN_SECRET", "second-key")
    assert api.call().json()["state"] == "unavailable"
    assert api.call("POST").status_code == 409
    assert api.call("DELETE").status_code == 200
    assert api.call("POST").json()["state"] == "open"


def test_missing_class_returns_404(api):
    for method in ("GET", "POST", "DELETE"):
        assert api.call(method, uuid4()).status_code == 404


def test_prefetched_signin_cannot_write_after_close(api):
    data = api.call("POST").json()
    with api.factory() as db:
        opened = find_open_checkin(db, token(data), now=NOW, today=DAY)
    api.clock[0] += timedelta(seconds=1)
    api.call("DELETE")
    with api.factory.begin() as db:
        with pytest.raises(CheckinClosedError):
            sign_in(db, opened, uuid4(), DAY, now=NOW)
    with api.factory() as db:
        assert db.execute(select(attendance_records)).all() == []


def test_prefetched_signin_cannot_write_after_expiry(api):
    data = api.call("POST").json()
    with api.factory() as db:
        opened = find_open_checkin(db, token(data), now=NOW, today=DAY)
    with api.factory.begin() as db:
        with pytest.raises(CheckinExpiredError):
            sign_in(db, opened, uuid4(), DAY, now=NOW + timedelta(hours=4))


def test_public_signin_updates_same_attendance_and_material_grant(api, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module("app")
    monkeypatch.setattr(module, "SessionLocal", api.factory)
    monkeypatch.setattr(module, "club_today", api.today)

    class Clock:
        @staticmethod
        def now(tz):
            return api.clock[0].astimezone(tz)

    monkeypatch.setattr(module, "datetime", Clock)
    learner = uuid4()
    monkeypatch.setattr(
        user_client, "find_learner_for_sign_in", lambda *args: {"id": str(learner)}
    )
    monkeypatch.setattr(
        user_client,
        "current_staff",
        lambda _: user_client.Staff(OWNER, "Teacher", "teacher"),
    )
    client = TestClient(module.app)
    data = client.post(
        f"/sessions/{api.sid}/check-in", headers={"Authorization": "Bearer staff"}
    ).json()
    response = client.post(
        f"/checkin/{token(data)}/sign-in",
        json={"first_name": "Māia", "family_name": "Test"},
    )
    assert (
        response.status_code == 201
        and "ako_materials=" in response.headers["set-cookie"]
    )
    assert (
        client.get(
            f"/sessions/{api.sid}/attendance", headers={"Authorization": "Bearer staff"}
        ).json()["present_count"]
        == 1
    )
    with api.factory() as db:
        assert (
            db.execute(select(attendance_records.c.recorded_by)).scalar_one() == OWNER
        )
        assert db.execute(select(learner_material_grants)).first() is not None
    assert (
        client.post(
            f"/checkin/{token(data)}/sign-in",
            json={"first_name": "Māia", "family_name": "Test"},
        ).status_code
        == 409
    )
    api.call("DELETE")
    assert (
        client.post(
            f"/checkin/{token(data)}/sign-in",
            json={"first_name": "Māia", "family_name": "Test"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/sessions/{api.sid}/check-in", headers={"Authorization": "Bearer staff"}
        ).headers["cache-control"]
        == "no-store"
    )
    client.close()


@pytest.mark.parametrize("change", ["close", "expire"])
def test_public_request_rechecks_after_slow_name_lookup(api, monkeypatch, change):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module("app")
    monkeypatch.setattr(module, "SessionLocal", api.factory)
    monkeypatch.setattr(module, "club_today", api.today)

    class Clock:
        @staticmethod
        def now(tz):
            return api.clock[0].astimezone(tz)

    monkeypatch.setattr(module, "datetime", Clock)
    data = api.call("POST").json()

    def lookup(*args):
        if change == "close":
            assert api.call("DELETE").status_code == 200
        else:
            api.clock[0] += timedelta(hours=4)
        return {"id": str(uuid4())}

    monkeypatch.setattr(user_client, "find_learner_for_sign_in", lookup)
    client = TestClient(module.app)
    response = client.post(
        f"/checkin/{token(data)}/sign-in",
        json={"first_name": "Māia", "family_name": "Test"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Check-in is closed. Please ask the teacher"
    with api.factory() as db:
        assert db.execute(select(attendance_records)).all() == []
        assert db.execute(select(learner_material_grants)).all() == []
    client.close()


def test_existing_wrong_name_limit_still_applies_without_attendance(api, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module("app")
    monkeypatch.setattr(module, "SessionLocal", api.factory)
    monkeypatch.setattr(module, "club_today", api.today)

    class Clock:
        @staticmethod
        def now(tz):
            return api.clock[0].astimezone(tz)

    monkeypatch.setattr(module, "datetime", Clock)

    def unknown(*args):
        raise user_client.SignInNameNotFoundError()

    monkeypatch.setattr(user_client, "find_learner_for_sign_in", unknown)
    data = api.call("POST").json()
    client = TestClient(module.app)
    for _ in range(10):
        assert (
            client.post(
                f"/checkin/{token(data)}/sign-in",
                json={"first_name": "Wrong", "family_name": "Name"},
            ).status_code
            == 404
        )
    assert (
        client.post(
            f"/checkin/{token(data)}/sign-in",
            json={"first_name": "Wrong", "family_name": "Name"},
        ).status_code
        == 429
    )
    api.clock[0] += timedelta(minutes=10, seconds=1)
    assert (
        client.post(
            f"/checkin/{token(data)}/sign-in",
            json={"first_name": "Wrong", "family_name": "Name"},
        ).status_code
        == 404
    )
    with api.factory() as db:
        assert db.execute(select(attendance_records)).all() == []
    client.close()
