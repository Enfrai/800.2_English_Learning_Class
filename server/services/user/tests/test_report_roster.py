"""Verify coordinator-only minimal report rosters and historical learner inclusion.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import importlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from auth import AuthenticatedUser, get_current_user, require_coordinator
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from models import learners, users
from report_roster import create_report_roster_router
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def api(tmp_path):
    """
    Provide injected API client and isolated application fixture.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'roster.sqlite'}")
    users.create(engine)
    learners.create(engine)
    factory = sessionmaker(engine)
    identifiers = [uuid4() for _ in range(4)]
    with factory.begin() as db:
        for i, identifier in enumerate(identifiers):
            db.execute(
                learners.insert().values(
                    id=identifier,
                    first_name="Māia" if i < 2 else "Past",
                    family_name="Test",
                    is_active=i < 2,
                    contact="private@example.test",
                    first_language="private",
                    created_by=uuid4(),
                )
            )
    app = FastAPI()
    app.include_router(create_report_roster_router(factory, require_coordinator))
    client = TestClient(app)

    def as_role(role):
        """
        Configure the test request identity with the supplied staff role.
        """
        if role is None:

            def no_login():
                """
                Simulate the missing-authentication path for the surrounding API
                scenario.
                """
                raise HTTPException(401, "Login required")

            app.dependency_overrides[get_current_user] = no_login
        else:
            app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
                uuid4(), "Test", role, datetime.now(UTC) + timedelta(minutes=30)
            )

    as_role("coordinator")
    yield client, factory, identifiers, as_role, engine
    client.close()
    engine.dispose()


def test_current_and_requested_historical_names_without_private_fields(api):
    """
    Verify that current and requested historical names without private fields.
    """
    client, _, ids, _, _ = api
    response = client.post(
        "/reports/attendance/learners", json={"learner_ids": [str(ids[2])]}
    )
    assert response.status_code == 200
    rows = response.json()
    assert {row["id"] for row in rows} == {str(i) for i in ids[:3]}
    assert len([row for row in rows if row["first_name"] == "Māia"]) == 2
    assert all(set(row) == {"id", "first_name", "family_name"} for row in rows)
    assert "private" not in response.text


def test_empty_ids_retains_active_roster_and_duplicate_ids_are_safe(api):
    """
    Verify that empty ids retains active roster and duplicate ids are safe.
    """
    client, _, ids, _, _ = api
    assert (
        len(
            client.post("/reports/attendance/learners", json={"learner_ids": []}).json()
        )
        == 2
    )
    assert (
        len(
            client.post(
                "/reports/attendance/learners", json={"learner_ids": [str(ids[2])] * 3}
            ).json()
        )
        == 3
    )


@pytest.mark.parametrize(
    "role,status", [(None, 401), ("teacher", 403), ("learner", 403), ("visitor", 403)]
)
def test_denied_before_roster_query(api, role, status):
    """
    Verify that denied before roster query.
    """
    client, _, _, as_role, engine = api
    as_role(role)
    statements = []

    def trace(*args):
        """
        Inspect or record trace events for the surrounding database or HTTP test.
        """
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", trace)
    try:
        response = client.post("/reports/attendance/learners", json={"learner_ids": []})
    finally:
        event.remove(engine, "before_cursor_execute", trace)
    assert response.status_code == status and statements == []
    assert "Māia" not in response.text


def test_missing_history_refuses_partial_roster(api):
    """
    Verify that missing history refuses partial roster.
    """
    client, *_ = api
    response = client.post(
        "/reports/attendance/learners", json={"learner_ids": [str(uuid4())]}
    )
    assert response.status_code == 409 and "Māia" not in response.text


@pytest.mark.parametrize(
    "payload",
    [{}, {"learner_ids": ["bad"]}, {"learner_ids": [], "role": "coordinator"}],
)
def test_invalid_roster_requests(api, payload):
    """
    Verify that invalid roster requests.
    """
    client, *_ = api
    assert client.post("/reports/attendance/learners", json=payload).status_code == 422


def test_application_roster_endpoint_has_cache_control(api, monkeypatch):
    """
    Verify that application roster endpoint has cache control.
    """
    client, factory, _, _, _ = api
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module("app")
    monkeypatch.setattr(module.app.state, "session_factory", factory)
    module.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        uuid4(), "Coordinator", "coordinator", datetime.now(UTC) + timedelta(minutes=30)
    )
    actual = TestClient(module.app)
    try:
        response = actual.post("/reports/attendance/learners", json={"learner_ids": []})
        assert (
            response.status_code == 200
            and response.headers["cache-control"] == "no-store"
        )
    finally:
        actual.close()
        module.app.dependency_overrides.clear()
