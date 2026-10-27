"""ST-02 uses only temporary SQLite storage, not PostgreSQL or app lifespan."""

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import sessionmaker

from enquiries import (
    CONSENT_ERROR,
    EMAIL_ERROR,
    MESSAGE_ERROR,
    SUCCESS_MESSAGE,
    create_enquiries_router,
)
from models import public_enquiries

VALID = dict(
    name="Test Visitor",
    contact_type="email",
    contact="visitor@example.test",
    consent=True,
)
API = tuple[TestClient, Engine]


@pytest.fixture
def isolated_api(tmp_path: Path) -> Iterator[API]:
    """
    Provide aPI fixture with isolated persistence and dependency overrides.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'enquiries.sqlite'}")
    public_enquiries.create(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine)
    app.include_router(create_enquiries_router())
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, engine
    finally:
        engine.dispose()


def count_rows(engine: Engine) -> int:
    """
    Count persisted rows in the isolated enquiry database.
    """
    with engine.connect() as db:
        return db.execute(
            select(func.count()).select_from(public_enquiries)
        ).scalar_one()


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"message": None},
        {"message": ""},
        {"message": "a" * 500},
        {"message": "😀" * 500},
        {"contact_type": "phone", "contact": "+64 21 555 0101"},
        {"contact_type": "phone", "contact": "021-555-0101"},
        {"name": "  Test Visitor  ", "contact": " visitor@example.test "},
    ],
)
def test_valid(isolated_api: API, changes: dict) -> None:
    """
    Verify that valid.
    """
    client, engine = isolated_api
    payload = VALID | changes
    response = client.post("/enquiries", json=payload)
    assert response.status_code == 201
    assert response.json() == {"message": SUCCESS_MESSAGE}
    assert response.headers["cache-control"] == "no-store"
    with engine.connect() as db:
        row = db.execute(select(public_enquiries)).mappings().one()
    assert isinstance(row["id"], UUID)
    assert row["name"] == payload["name"].strip()
    assert row["contact"] == payload["contact"].strip()
    assert row["message"] == payload.get("message")
    assert row["status"] == "new"
    assert row["created_at"] is not None


@pytest.mark.parametrize(
    "changes,detail",
    [
        ({"contact": "sam@"}, EMAIL_ERROR),
        ({"contact": "a..b@example.test"}, EMAIL_ERROR),
        ({"contact": "a@-example.test"}, EMAIL_ERROR),
        ({"contact": "a b@example.test"}, EMAIL_ERROR),
        ({"contact": ""}, EMAIL_ERROR),
        ({"contact": "a" * 256}, EMAIL_ERROR),
        ({"consent": False}, CONSENT_ERROR),
        ({"message": "a" * 501}, MESSAGE_ERROR),
        ({"message": "😀" * 501}, MESSAGE_ERROR),
        ({"name": " "}, None),
        ({"name": "a" * 151}, None),
        ({"contact_type": "phone", "contact": "abc12345"}, None),
        ({"contact_type": "phone", "contact": "123456"}, None),
        ({"contact_type": "phone", "contact": "1" * 16}, None),
        ({"contact_type": "fax"}, None),
        ({"consent": "true"}, None),
        ({"consent": 1}, None),
        ({"consent": None}, None),
        ({"message": 123}, None),
        ({"name": None}, None),
        ({"status": "reviewed"}, None),
        ({"role": "coordinator"}, None),
        ({"id": "client-id"}, None),
        ({"created_at": "2026-01-01"}, None),
    ],
)
def test_invalid(isolated_api: API, changes: dict, detail: str | None) -> None:
    """
    Verify that invalid.
    """
    client, engine = isolated_api
    response = client.post("/enquiries", json=VALID | changes)
    assert response.status_code == 422
    if detail:
        assert response.json()["detail"] == detail
    assert count_rows(engine) == 0


@pytest.mark.parametrize("field", ["name", "contact_type", "contact", "consent"])
def test_required(isolated_api: API, field: str) -> None:
    """
    Verify that required.
    """
    client, engine = isolated_api
    payload = VALID.copy()
    del payload[field]
    assert client.post("/enquiries", json=payload).status_code == 422
    assert count_rows(engine) == 0


def test_rollback(isolated_api: API) -> None:
    """
    Verify that rollback.
    """
    client, engine = isolated_api

    def fail_commit(connection: Connection) -> None:
        """
        Simulate a failed database commit to check transaction error handling.
        """
        raise RuntimeError("Simulated commit failure")

    # Fail after INSERT to check rollback, not just rejection before a write.
    event.listen(engine, "commit", fail_commit)
    try:
        response = client.post("/enquiries", json=VALID)
        assert response.status_code == 500
        assert "Simulated" not in response.text
    finally:
        event.remove(engine, "commit", fail_commit)
    assert count_rows(engine) == 0
