"""HTTP contract tests with mocked persistence, not PostgreSQL integration tests."""

import hashlib
import importlib.util
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

LoginContext = tuple[ModuleType, TestClient, MagicMock, dict[str, Any], datetime]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[LoginContext]:
    """
    Provide injected API client and isolated application fixture.
    """
    service = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(service))
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused"
    )
    spec = importlib.util.spec_from_file_location("us001_app", service / "app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    now = datetime(2026, 10, 23, 12, tzinfo=UTC)

    class Clock:
        @staticmethod
        def now(tz: tzinfo | None) -> datetime:
            """
            Return the current timezone-aware UTC instant.
            """
            return now

    monkeypatch.setattr(module, "datetime", Clock)
    row = {
        "id": uuid4(),
        "username": "teacher",
        "is_active": True,
        "password_hash": module.password_hash("CorrectPass!", b"0123456789abcdef"),
        "role": "teacher",
        "display_name": "Test Teacher",
        "failed_login_attempts": 0,
        "locked_until": None,
    }
    db = MagicMock()
    db.__enter__.return_value = db
    db.execute.return_value.mappings.return_value.first.return_value = row
    monkeypatch.setattr(module.app.state, "session_factory", lambda: db)
    # Deliberately do not enter TestClient's context: lifespan seeds real databases.
    client = TestClient(module.app)
    yield module, client, db, row, now
    client.close()
    module.engine.dispose()
    sys.modules.pop(spec.name, None)


def login(client: TestClient, password: str = "WrongPass!") -> httpx.Response:
    """
    Validate staff credentials, replace previous sessions and issue the session cookie.
    """
    return client.post("/login", json={"username": "teacher", "password": password})


@pytest.mark.parametrize("prior", range(4))
def test_wrong_password_exact_message_and_committed_counter(
    api: LoginContext, prior: int
) -> None:
    """
    Verify that wrong password exact message and committed counter.
    """
    _, client, db, row, _ = api
    row["failed_login_attempts"] = prior
    response = login(client)
    assert response.status_code == 401
    assert response.json() == {"detail": "Username or password is incorrect"}
    update = db.execute.call_args_list[1].args[0].compile().params
    assert update["failed_login_attempts"] == prior + 1
    assert update["locked_until"] is None
    assert db.execute.call_count == 2  # No session insert.
    db.commit.assert_called_once()


def test_fifth_failure_locks_and_informs_immediately(api: LoginContext) -> None:
    """
    Verify that fifth failure locks and informs immediately.
    """
    _, client, db, row, now = api
    row["failed_login_attempts"] = 4
    response = login(client)
    assert response.status_code == 423
    detail = response.json()["detail"]
    assert detail["locked_until"] == (now + timedelta(minutes=10)).isoformat()
    assert detail["retry_after_seconds"] == 600
    assert detail["locked_until"] in detail["message"]
    assert response.headers["retry-after"] == "600"
    update = db.execute.call_args_list[1].args[0].compile().params
    assert update["locked_until"] == now + timedelta(minutes=10)
    assert update["failed_login_attempts"] == 0
    db.commit.assert_called_once()
    assert db.execute.call_count == 2


@pytest.mark.parametrize("password", ["WrongPass!", "CorrectPass!"])
def test_locked_account_rejects_without_extending_lock(
    api: LoginContext, password: str
) -> None:
    """
    Verify that locked account rejects without extending lock.
    """
    _, client, db, row, now = api
    row["locked_until"] = now + timedelta(seconds=60, microseconds=1)
    response = login(client, password)
    assert response.status_code == 423
    assert response.headers["retry-after"] == "61"
    assert response.json()["detail"]["locked_until"] == row["locked_until"].isoformat()
    assert db.execute.call_count == 1
    db.commit.assert_not_called()


@pytest.mark.parametrize("kind", ["unknown", "inactive"])
def test_unknown_and_inactive_users_get_generic_error(
    api: LoginContext, kind: str
) -> None:
    """
    Verify that unknown and inactive users get generic error.
    """
    _, client, db, row, _ = api
    if kind == "unknown":
        db.execute.return_value.mappings.return_value.first.return_value = None
    else:
        row["is_active"] = False
    response = login(client, "CorrectPass!")
    assert response.status_code == 401
    assert response.json() == {"detail": "Username or password is incorrect"}
    assert db.execute.call_count == 1


@pytest.mark.parametrize("role", ["teacher", "coordinator"])
@pytest.mark.parametrize("lock_expired", [False, True])
def test_success_contract_and_session_hash(
    api: LoginContext, role: str, lock_expired: bool
) -> None:
    """
    Verify that success contract and session hash.
    """
    _, client, db, row, now = api
    row["role"] = role
    row["failed_login_attempts"] = 3
    row["locked_until"] = now if lock_expired else None
    response = login(client, "CorrectPass!")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "sessionid",
        "expires_at",
        "user_id",
        "instance",
        "role",
        "display_name",
    }
    assert body["user_id"] == str(row["id"])
    assert body["role"] == role
    assert body["display_name"] == row["display_name"]
    assert datetime.fromisoformat(body["expires_at"]) == now + timedelta(minutes=30)
    update = db.execute.call_args_list[1].args[0].compile().params
    assert update["failed_login_attempts"] == 0
    assert update["locked_until"] is None
    session = db.execute.call_args_list[3].args[0].compile().params
    assert session["user_id"] == row["id"]
    assert (
        session["token_hash"] == hashlib.sha256(body["sessionid"].encode()).hexdigest()
    )
    assert session["token_hash"] != body["sessionid"]


def test_password_hash_compatibility(api: LoginContext) -> None:
    """
    Verify that password hash compatibility.
    """
    module, _, _, row, _ = api
    assert module.verify_password("CorrectPass!", row["password_hash"])
    assert not module.verify_password("WrongPass!", row["password_hash"])
    assert not module.verify_password("CorrectPass!", "malformed")
