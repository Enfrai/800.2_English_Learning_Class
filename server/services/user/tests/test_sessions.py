"""API tests for sign-in sessions (US-001 rules used by the lesson library).

A session ends after 30 minutes without explicit activity. Passive identity
reads do not extend it; explicit activity and logout use the US-001 contract. These call the real
endpoints with a test client on the test database.

Author: Sandhya Tiwari
Date: 24 Oct 2026
"""

import os
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import sessionmaker

# app.py builds its engine when imported. It only connects when used, and the
# tests replace its sessions, so this address is never contacted.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused@localhost/unused")

PASSWORD = "TeacherPass123!"


@pytest.fixture
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    import app as user_app

    with engine.connect() as connection:
        transaction = connection.begin()
        monkeypatch.setattr(
            user_app,
            "SessionLocal",
            sessionmaker(bind=connection, join_transaction_mode="create_savepoint"),
        )
        monkeypatch.setattr(
            user_app.app.state, "session_factory", user_app.SessionLocal
        )
        try:
            yield TestClient(user_app.app)
        finally:
            transaction.rollback()


@pytest.fixture
def teacher(client: TestClient) -> str:
    """Add a teacher account and return its username."""
    import app as user_app

    username = f"teacher-{secrets.token_hex(4)}"
    with user_app.SessionLocal.begin() as db:
        user_app.seed_user(db, username, PASSWORD, "Test Teacher", "teacher")
    return username


def log_in(client: TestClient, username: str) -> dict:
    response = client.post("/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def bearer(session_id: str) -> dict:
    return {"Authorization": f"Bearer {session_id}", "Cookie": ""}


def set_session_times(last_activity: datetime, expires: datetime) -> None:
    """Move the session into the past, as if time had passed."""
    import app as user_app
    from models import user_sessions

    with user_app.SessionLocal.begin() as db:
        db.execute(
            update(user_sessions).values(
                created_at=last_activity - timedelta(minutes=5),
                last_activity_at=last_activity,
                expires_at=expires,
            )
        )


def session_expiry() -> datetime:
    import app as user_app
    from models import user_sessions

    with user_app.SessionLocal() as db:
        return db.execute(select(user_sessions.c.expires_at)).scalar_one()


def test_signed_in_teacher_is_recognised(client: TestClient, teacher: str) -> None:
    session = log_in(client, teacher)

    response = client.get("/me", headers=bearer(session["sessionid"]))

    assert response.status_code == 200
    assert response.json()["role"] == "teacher"


def test_no_or_wrong_session_is_refused(client: TestClient) -> None:
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers=bearer("not-a-session")).status_code == 401
    assert client.get("/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_activity_moves_the_end_of_the_session_forward(
    client: TestClient, teacher: str
) -> None:
    session = log_in(client, teacher)
    now = datetime.now(UTC)
    # Signed in 25 minutes ago and active until 20 minutes ago.
    set_session_times(now - timedelta(minutes=20), now + timedelta(minutes=10))

    before = session_expiry()
    assert client.get("/me", headers=bearer(session["sessionid"])).status_code == 200
    assert session_expiry() == before
    response = client.post("/activity", headers=bearer(session["sessionid"]))
    assert response.status_code == 200
    assert session_expiry() > now + timedelta(minutes=29)


def test_session_ends_after_30_minutes_without_activity(
    client: TestClient, teacher: str
) -> None:
    session = log_in(client, teacher)
    now = datetime.now(UTC)
    set_session_times(now - timedelta(minutes=31), now - timedelta(minutes=1))

    response = client.get("/me", headers=bearer(session["sessionid"]))

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_log_out_ends_the_session_on_the_server(
    client: TestClient, teacher: str
) -> None:
    session = log_in(client, teacher)

    response = client.post("/logout", headers=bearer(session["sessionid"]))

    assert response.status_code == 200
    assert client.get("/me", headers=bearer(session["sessionid"])).status_code == 401


def test_log_out_without_a_session_is_refused(client: TestClient) -> None:
    assert client.post("/logout").status_code == 401
