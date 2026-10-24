"""Authentication tests against isolated SQLite; never use development databases."""

import hashlib
import importlib.util
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

# Fixture includes dynamically loaded modules and SQLAlchemy test objects.
AuthContext = dict[str, Any]


@pytest.fixture
def context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[AuthContext]:
    service = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(service))
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused"
    )
    spec = importlib.util.spec_from_file_location("us001_auth_app", service / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    auth = importlib.import_module("auth")
    models = importlib.import_module("models")
    user_sessions, users = models.user_sessions, models.users

    engine = create_engine(f"sqlite:///{tmp_path / 'auth.sqlite'}")
    users.create(engine)
    user_sessions.create(engine)
    factory = sessionmaker(engine)
    module.app.state.session_factory = factory
    now = datetime(2030, 1, 1, 12, tzinfo=UTC)
    clock = {"now": now}

    class Clock:
        @staticmethod
        def now(tz: tzinfo | None) -> datetime:
            return clock["now"]

    monkeypatch.setattr(auth, "datetime", Clock)
    user_id, session_id = uuid4(), uuid4()
    token = "a-valid-opaque-session-token"
    with factory.begin() as db:
        db.execute(
            users.insert().values(
                id=user_id,
                username="teacher",
                display_name="Test Teacher",
                password_hash="not-exposed",
                role="teacher",
                is_active=True,
            )
        )
        db.execute(
            user_sessions.insert().values(
                id=session_id,
                user_id=user_id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                created_at=now - timedelta(hours=1),
                last_activity_at=now,
                expires_at=now + timedelta(minutes=30),
            )
        )

    calls = []

    @module.app.get("/test/coordinator")
    def coordinator(user: Any = Depends(auth.require_coordinator)) -> dict[str, str]:
        calls.append("coordinator")
        return {"user_id": str(user.user_id)}

    @module.app.get("/test/teacher")
    def teacher(user: Any = Depends(auth.require_teacher)) -> dict[str, str]:
        calls.append("teacher")
        return {"user_id": str(user.user_id)}

    # No lifespan: avoids schema initialization and demo seeding.
    with _client(module.app) as client:
        yield {
            "client": client,
            "module": module,
            "auth": auth,
            "factory": factory,
            "engine": engine,
            "users": users,
            "sessions": user_sessions,
            "user_id": user_id,
            "session_id": session_id,
            "token": token,
            "now": now,
            "clock": clock,
            "calls": calls,
        }
    engine.dispose()
    module.engine.dispose()


@contextmanager
def _client(app: FastAPI) -> Iterator[TestClient]:
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()


def headers(ctx: AuthContext) -> dict[str, str]:
    return {"Authorization": f"Bearer {ctx['token']}"}


def change_session(ctx: AuthContext, **values: Any) -> None:
    with ctx["factory"].begin() as db:
        db.execute(ctx["sessions"].update().values(**values))


def change_user(ctx: AuthContext, **values: Any) -> None:
    with ctx["factory"].begin() as db:
        db.execute(ctx["users"].update().values(**values))


def test_valid_session_minimal_identity(context: AuthContext) -> None:
    c = context
    response = c["client"].get("/session", headers=headers(c))
    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(c["user_id"]),
        "display_name": "Test Teacher",
        "role": "teacher",
    }
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "authorization",
    [None, "Basic abc", "Bearer", "Bearer wrong", "Bearer " + "x" * 513],
)
def test_missing_malformed_and_unknown_tokens(
    context: AuthContext, authorization: str | None
) -> None:
    c = context
    response = c["client"].get(
        "/session",
        headers={} if authorization is None else {"Authorization": authorization},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "state",
    ["expired", "boundary", "revoked", "inactive", "deleted_session", "deleted_user"],
)
def test_invalid_database_states(context: AuthContext, state: str) -> None:
    c = context
    if state == "expired":
        change_session(c, expires_at=c["now"] - timedelta(seconds=1))
    elif state == "boundary":
        change_session(c, expires_at=c["now"])
    elif state == "revoked":
        change_session(c, revoked_at=c["now"])
    elif state == "inactive":
        change_user(c, is_active=False)
    else:
        with c["factory"].begin() as db:
            db.execute(c["sessions"].delete())
            if state == "deleted_user":
                db.execute(c["users"].delete())
    response = c["client"].get("/session", headers=headers(c))
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.parametrize(
    "role,path,status",
    [
        ("teacher", "/test/teacher", 200),
        ("teacher", "/test/coordinator", 403),
        ("coordinator", "/test/coordinator", 200),
        ("coordinator", "/test/teacher", 403),
    ],
)
def test_exact_role_authorization_before_handler(
    context: AuthContext, role: str, path: str, status: int
) -> None:
    c = context
    change_user(c, role=role)
    response = c["client"].get(path, headers=headers(c))
    assert response.status_code == status
    if status == 403:
        assert response.json() == {"detail": "You do not have permission"}
        assert c["calls"] == []
    else:
        assert c["calls"] == [role]


def test_unauthenticated_role_route_never_runs(context: AuthContext) -> None:
    c = context
    response = c["client"].get("/test/coordinator")
    assert response.status_code == 401
    assert c["calls"] == []


def test_client_role_and_query_token_are_not_trusted(context: AuthContext) -> None:
    c = context
    response = c["client"].get(
        "/test/coordinator?role=coordinator",
        headers={**headers(c), "X-Role": "coordinator", "X-User-ID": str(uuid4())},
    )
    assert response.status_code == 403
    assert c["calls"] == []
    assert c["client"].get(f"/session?sessionid={c['token']}").status_code == 401


def test_database_role_change_applies_on_next_request(context: AuthContext) -> None:
    c = context
    assert c["client"].get("/test/teacher", headers=headers(c)).status_code == 200
    change_user(c, role="coordinator")
    assert c["client"].get("/test/teacher", headers=headers(c)).status_code == 403
    assert c["client"].get("/test/coordinator", headers=headers(c)).status_code == 200


def test_validation_is_read_only(context: AuthContext) -> None:
    c = context
    statements = []
    with c["factory"]() as db:
        before = dict(db.execute(select(c["sessions"])).mappings().one())

    def capture(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(c["engine"], "before_cursor_execute", capture)
    try:
        assert c["client"].get("/session", headers=headers(c)).status_code == 200
    finally:
        event.remove(c["engine"], "before_cursor_execute", capture)
    assert statements and all(
        s.lstrip().upper().startswith("SELECT") for s in statements
    )
    with c["factory"]() as db:
        assert dict(db.execute(select(c["sessions"])).mappings().one()) == before


@pytest.mark.parametrize("transition", ["revoke", "expire"])
def test_overlapping_validation_cannot_reactivate_session(
    context: AuthContext, monkeypatch: pytest.MonkeyPatch, transition: str
) -> None:
    c = context
    validated, resume = Event(), Event()
    original = c["auth"].authenticate_session

    def paused_validation(token: str, db: Session) -> Any:
        user = original(token, db)
        validated.set()
        assert resume.wait(5), "test did not release validation"
        return user

    monkeypatch.setattr(c["auth"], "authenticate_session", paused_validation)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(c["client"].get, "/session", headers=headers(c))
        try:
            assert validated.wait(5), "validation never completed"
            if transition == "revoke":
                change_session(c, revoked_at=c["now"])
            else:
                c["clock"]["now"] += timedelta(minutes=30)
        finally:
            resume.set()
        # Already authenticated in-flight requests may finish.
        assert request.result(timeout=5).status_code == 200
    monkeypatch.setattr(c["auth"], "authenticate_session", original)
    assert c["client"].get("/session", headers=headers(c)).status_code == 401
    with c["factory"]() as db:
        row = db.execute(select(c["sessions"])).mappings().one()
        assert row["expires_at"].replace(tzinfo=UTC) == c["now"] + timedelta(minutes=30)
        if transition == "revoke":
            assert row["revoked_at"].replace(tzinfo=UTC) == c["now"]


def test_login_and_validation_share_injected_factory(
    context: AuthContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = context
    module = c["module"]
    monkeypatch.setattr(module, "datetime", c["auth"].datetime)
    change_user(
        c, password_hash=module.password_hash("CorrectPass!", b"0123456789abcdef")
    )
    response = c["client"].post(
        "/login", json={"username": "teacher", "password": "CorrectPass!"}
    )
    assert response.status_code == 200
    token = response.json()["sessionid"]
    session = c["client"].get("/session", headers={"Authorization": f"Bearer {token}"})
    assert session.status_code == 200
    assert session.json()["user_id"] == str(c["user_id"])
    # The same isolated database also records replacement of the old session.
    assert c["client"].get("/session", headers=headers(c)).status_code == 401
