"""Exercise the real app/Cookie and Bearer dependency against disposable SQLite storage.

No application lifespan runs and no shared PostgreSQL connection is opened.
"""

import hashlib
import importlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import sessionmaker

from models import public_enquiries, user_sessions, users

API = tuple[TestClient, Engine]


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[API]:
    # Pin even the lazy import-time engine to temporary storage; bypass demo seeding.
    """
    Provide injected API client and isolated application fixture.
    """
    url = f"sqlite:///{tmp_path / 'listing.sqlite'}"
    monkeypatch.setenv("DATABASE_URL", url)
    application = importlib.import_module("app")
    engine = create_engine(url)
    for table in (users, user_sessions, public_enquiries):
        table.create(engine)
    monkeypatch.setattr(application.app.state, "session_factory", sessionmaker(engine))
    now = datetime.now(UTC)
    with engine.begin() as db:
        for i, (token, role, active, expired, revoked) in enumerate(
            [
                ("coordinator", "coordinator", True, False, False),
                ("teacher", "teacher", True, False, False),
                ("inactive", "coordinator", False, False, False),
                ("expired", "coordinator", True, True, False),
                ("revoked", "coordinator", True, False, True),
            ],
            1,
        ):
            user_id = UUID(f"abcdef00-0000-0000-0000-{i:012x}")
            db.execute(
                users.insert().values(
                    id=user_id,
                    username=token,
                    password_hash="unused-test-hash",
                    display_name=token,
                    role=role,
                    is_active=active,
                )
            )
            db.execute(
                user_sessions.insert().values(
                    user_id=user_id,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    created_at=now - timedelta(hours=2),
                    last_activity_at=now,
                    expires_at=now + timedelta(minutes=-1 if expired else 30),
                    revoked_at=now if revoked else None,
                )
            )
        # Same-time rows deliberately arrive out of UUID order.
        for i in (2, 1, 3):
            db.execute(
                public_enquiries.insert().values(
                    id=UUID(f"abcdef00-0000-0000-0000-{i:012x}"),
                    name=f"Visitor {i}",
                    contact="test@example.test",
                    message=None,
                    created_at=now - timedelta(days=1 if i == 3 else 0),
                )
            )
    try:
        # Not entering TestClient prevents lifespan/create_all/demo initialization.
        with_client = TestClient(application.app)
        try:
            yield with_client, engine
        finally:
            with_client.close()
    finally:
        engine.dispose()


def headers(token: str = "coordinator") -> dict[str, str]:
    """
    Prepare or exercise headers in the test enquiry listing test scenario.
    """
    return {"Authorization": f"Bearer {token}"}


def test_coordinator_fields_order_and_cache(api: API) -> None:
    """
    Verify that coordinator fields order and cache.
    """
    client, _ = api
    response = client.get("/enquiries", headers=headers())
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    rows = response.json()
    assert [row["id"] for row in rows] == [
        str(UUID(f"abcdef00-0000-0000-0000-{i:012x}")) for i in (2, 1, 3)
    ]
    assert all(
        set(row) == {"id", "name", "contact", "message", "created_at"} for row in rows
    )


@pytest.mark.parametrize(
    "token,status",
    [
        (None, 401),
        ("invalid", 401),
        ("inactive", 401),
        ("expired", 401),
        ("revoked", 401),
        ("teacher", 403),
    ],
)
def test_denied(api: API, token: str | None, status: int) -> None:
    """
    Verify that denied.
    """
    client, _ = api
    response = client.get("/enquiries", headers=headers(token) if token else {})
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "Visitor" not in response.text and "test@example.test" not in response.text
    if status == 403:
        assert response.json() == {"detail": "You do not have permission"}


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "limit=no", "offset=-1", "offset=10001"]
)
def test_invalid_pagination(api: API, query: str) -> None:
    """
    Verify that invalid pagination.
    """
    client, _ = api
    response = client.get(f"/enquiries?{query}", headers=headers())
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_pagination_and_empty(api: API) -> None:
    """
    Verify that pagination and empty.
    """
    client, engine = api
    assert client.get("/enquiries?limit=1&offset=1", headers=headers()).json()[0][
        "id"
    ] == str(UUID("abcdef00-0000-0000-0000-000000000001"))
    assert client.get("/enquiries?offset=3", headers=headers()).json() == []
    with engine.begin() as db:
        db.execute(public_enquiries.delete())
    assert client.get("/enquiries", headers=headers()).json() == []


def test_default_and_maximum_limit(api: API) -> None:
    """
    Verify that default and maximum limit.
    """
    client, engine = api
    with engine.begin() as db:
        db.execute(
            public_enquiries.insert(),
            [dict(name="Extra", contact="test@example.test") for _ in range(110)],
        )
    assert len(client.get("/enquiries", headers=headers()).json()) == 50
    assert len(client.get("/enquiries?limit=100", headers=headers()).json()) == 100


def test_database_role_not_client_claim(api: API) -> None:
    """
    Verify that database role not client claim.
    """
    client, engine = api
    response = client.get(
        "/enquiries?role=coordinator",
        headers=headers("teacher") | {"X-Role": "coordinator"},
    )
    assert response.status_code == 403
    with engine.begin() as db:
        db.execute(
            users.update()
            .where(users.c.username == "coordinator")
            .values(role="teacher")
        )
    assert client.get("/enquiries", headers=headers()).status_code == 403


def test_post_still_public_and_session_read_is_passive(api: API) -> None:
    """
    Verify that post still public and session read is passive.
    """
    client, engine = api
    with engine.connect() as db:
        before = db.execute(select(user_sessions)).all()
    response = client.post(
        "/enquiries",
        json=dict(
            name="New", contact_type="email", contact="new@example.test", consent=True
        ),
    )
    assert response.status_code == 201
    assert response.json() == {"message": "Thank you, the club will contact you"}
    assert client.get("/enquiries", headers=headers()).status_code == 200
    assert client.get("/me", headers=headers("teacher")).status_code == 200
    with engine.connect() as db:
        assert db.execute(select(user_sessions)).all() == before


@pytest.mark.parametrize(
    "token,status",
    [
        ("coordinator", 200),
        ("teacher", 403),
        ("expired", 401),
        ("revoked", 401),
        ("inactive", 401),
    ],
)
def test_cookie_authorization(api: API, token: str, status: int) -> None:
    """
    Verify that cookie authorization.
    """
    client, _ = api
    client.cookies.set("ako_session", token)
    response = client.get("/enquiries")
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    if status != 200:
        assert "Visitor" not in response.text


def test_conflicting_credentials_and_idle_session(api: API) -> None:
    """
    Verify that conflicting credentials and idle session.
    """
    client, engine = api
    client.cookies.set("ako_session", "teacher")
    assert client.get("/enquiries", headers=headers()).status_code == 401
    client.cookies.clear()
    with engine.begin() as db:
        db.execute(
            user_sessions.update().values(
                last_activity_at=datetime.now(UTC) - timedelta(minutes=31)
            )
        )
    assert client.get("/enquiries", headers=headers()).status_code == 401


def test_public_post_ignores_invalid_cookie_and_errors_are_not_cached(api: API) -> None:
    """
    Verify that public post ignores invalid cookie and errors are not cached.
    """
    client, engine = api
    client.cookies.set("ako_session", "invalid")
    payload = dict(
        name="Public", contact_type="email", contact="public@example.test", consent=True
    )
    assert client.post("/enquiries", json=payload).status_code == 201
    response = client.post("/enquiries", json=payload | {"consent": False})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    with engine.connect() as db:
        assert len(db.execute(select(public_enquiries)).all()) == 4
