"""Real PostgreSQL tests for the isolated Compose or identity-checked host runner."""

import hashlib
import importlib.util
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table, create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from run_postgres import verify_container


@pytest.fixture(scope="module")
def postgres_url() -> str:
    compose_url = os.getenv("AKO_COMPOSE_TEST_DATABASE_URL")
    if compose_url:
        url = make_url(compose_url)
        if not (
            os.getenv("AKO_TEST_COMPOSE") == "1"
            and url.drivername == "postgresql+psycopg"
            and url.host == "test-db"
            and url.username == "ako_test"
            and url.database is not None
            and url.database.startswith("ako_test_")
        ):
            raise RuntimeError(
                "Refusing a database outside the isolated Compose runner"
            )
        engine = create_engine(compose_url)
        try:
            with engine.connect() as db:
                assert db.scalar(text("SELECT current_database()")) == url.database
                assert (
                    170000 <= int(db.scalar(text("SHOW server_version_num"))) < 180000
                )
        finally:
            engine.dispose()
        return compose_url
    value = os.getenv("US001_TEST_PG_URL")
    if not value:
        pytest.skip("Use tests/run_postgres.py for isolated PostgreSQL tests")
    run_id = os.environ["US001_TEST_RUN_ID"]
    assert len(run_id) == 32 and all(c in "0123456789abcdef" for c in run_id)
    info = verify_container(os.environ["US001_TEST_CONTAINER_ID"], run_id)
    url = make_url(value)
    assert url.drivername == "postgresql+psycopg"
    assert url.host == "127.0.0.1" and url.username == "us001_test"
    assert url.database == f"us001_test_{run_id}"
    bindings = info["NetworkSettings"]["Ports"]["5432/tcp"]
    assert len(bindings) == 1
    assert bindings[0]["HostIp"] == "127.0.0.1"
    assert int(bindings[0]["HostPort"]) == url.port
    engine = create_engine(value)
    try:
        with engine.connect() as db:
            assert db.scalar(text("SELECT current_database()")) == url.database
            assert 170000 <= int(db.scalar(text("SHOW server_version_num"))) < 180000
    finally:
        engine.dispose()
    return value


@dataclass
class PgContext:
    a: ModuleType
    b: ModuleType
    clients: tuple[TestClient, TestClient]
    users: Table
    sessions: Table
    user_id: UUID
    username: str

    @property
    def engine(self) -> Engine:
        return self.a.engine

    def login(self, replica: int = 0, password: str = "CorrectPass!") -> httpx.Response:
        return self.clients[replica].post(
            "/login",
            json={"username": self.username, "password": password},
            headers={"Cookie": ""},
        )

    def validate(self, token: str, replica: int = 1) -> httpx.Response:
        return self.clients[replica].get(
            "/session", headers={"Authorization": f"Bearer {token}", "Cookie": ""}
        )

    def user(self) -> dict[str, Any]:
        with self.engine.connect() as db:
            return dict(
                db.execute(select(self.users).where(self.users.c.id == self.user_id))
                .mappings()
                .one()
            )

    def session_rows(self) -> list[dict[str, Any]]:
        with self.engine.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    select(self.sessions).where(self.sessions.c.user_id == self.user_id)
                ).mappings()
            ]

    def update_session(self, **values: Any) -> None:
        with self.b.engine.begin() as db:
            db.execute(
                self.sessions.update()
                .where(self.sessions.c.user_id == self.user_id)
                .values(**values)
            )


@pytest.fixture
def pg(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[PgContext]:
    service = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(service))
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    modules = []
    for label in ("A", "B"):
        monkeypatch.setenv("INSTANCE_NAME", label)
        spec = importlib.util.spec_from_file_location(
            f"pg_app_{label}_{uuid4().hex}", service / "app.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    a, b = modules
    models = importlib.import_module("models")
    models.Base.metadata.create_all(a.engine)
    user_id = uuid4()
    username = f"teacher_{user_id.hex}"
    with a.engine.begin() as db:
        db.execute(
            models.users.insert().values(
                id=user_id,
                username=username,
                display_name="Integration Teacher",
                role="teacher",
                password_hash=a.password_hash("CorrectPass!", os.urandom(16)),
            )
        )
    clients = (
        TestClient(a.app, raise_server_exceptions=False),
        TestClient(b.app, raise_server_exceptions=False),
    )
    try:
        assert a.engine is not b.engine
        assert a.app.state.session_factory is not b.app.state.session_factory
        yield PgContext(
            a, b, clients, models.users, models.user_sessions, user_id, username
        )
    finally:
        for client in clients:
            client.close()
        a.engine.dispose()
        b.engine.dispose()


def test_persisted_five_failure_lockout_and_expiry(pg: PgContext) -> None:
    for attempt in range(1, 5):
        assert pg.login(attempt % 2, "wrong").status_code == 401
        assert pg.user()["failed_login_attempts"] == attempt
    before = datetime.now(UTC)
    response = pg.login(0, "wrong")
    after = datetime.now(UTC)
    assert response.status_code == 423
    locked_until = pg.user()["locked_until"]
    assert (
        before + timedelta(minutes=10) <= locked_until <= after + timedelta(minutes=10)
    )
    assert response.headers["Retry-After"] == "600"
    assert (
        datetime.fromisoformat(response.json()["detail"]["locked_until"])
        == locked_until
    )
    assert pg.login(1).status_code == 423
    assert pg.user()["locked_until"] == locked_until
    assert pg.session_rows() == []
    # Advance persisted lock state instead of waiting ten minutes.
    with pg.b.engine.begin() as db:
        db.execute(
            pg.users.update()
            .where(pg.users.c.id == pg.user_id)
            .values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert pg.login(1).status_code == 200
    assert pg.user()["failed_login_attempts"] == 0
    assert pg.user()["locked_until"] is None


def test_success_resets_committed_failures(pg: PgContext) -> None:
    for _ in range(3):
        assert pg.login(0, "wrong").status_code == 401
    assert pg.user()["failed_login_attempts"] == 3
    assert pg.login(1).status_code == 200
    assert pg.user()["failed_login_attempts"] == 0
    assert pg.login(0, "wrong").status_code == 401
    assert pg.user()["failed_login_attempts"] == 1


def test_hash_persistence_and_cross_replica_validation(pg: PgContext) -> None:
    login = pg.login(0)
    assert login.status_code == 200 and login.json()["instance"] == "A"
    token = login.json()["sessionid"]
    row = pg.session_rows()[0]
    assert row["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in repr(row)
    response = pg.validate(token, 1)
    assert response.status_code == 200
    assert response.json()["user_id"] == str(pg.user_id)
    assert response.json()["role"] == "teacher"


def test_replacement_and_revocation_visible_across_replicas(pg: PgContext) -> None:
    first = pg.login(0).json()["sessionid"]
    assert pg.validate(first, 1).status_code == 200
    second_response = pg.login(1)
    assert second_response.json()["instance"] == "B"
    second = second_response.json()["sessionid"]
    assert pg.validate(first, 0).status_code == 401
    assert pg.validate(second, 0).status_code == 200
    assert len(pg.session_rows()) == 1
    # No logout endpoint exists yet; commit revocation through instance B's engine.
    pg.update_session(revoked_at=datetime.now(UTC))
    assert pg.validate(second, 0).status_code == 401
    assert pg.validate(second, 1).status_code == 401


@pytest.mark.parametrize("state", ["expired", "revoked", "inactive"])
def test_reject_persisted_invalid_sessions(pg: PgContext, state: str) -> None:
    token = pg.login().json()["sessionid"]
    now = datetime.now(UTC)
    if state == "expired":
        pg.update_session(
            created_at=now - timedelta(hours=1), expires_at=now - timedelta(seconds=1)
        )
    elif state == "revoked":
        pg.update_session(revoked_at=now)
    else:
        with pg.b.engine.begin() as db:
            db.execute(
                pg.users.update()
                .where(pg.users.c.id == pg.user_id)
                .values(is_active=False)
            )
    for replica in (0, 1):
        assert pg.validate(token, replica).status_code == 401


@pytest.mark.parametrize("count", [4, 5, 8])
def test_concurrent_failures_are_not_lost(pg: PgContext, count: int) -> None:
    barrier = Barrier(count)

    def fail(index: int) -> int:
        barrier.wait(timeout=10)
        return pg.login(index % 2, "wrong").status_code

    with ThreadPoolExecutor(max_workers=count) as pool:
        statuses = list(pool.map(fail, range(count)))
    assert statuses.count(401) == min(count, 4)
    assert statuses.count(423) == max(0, count - 4)
    row = pg.user()
    assert row["failed_login_attempts"] == (count if count < 5 else 0)
    assert (row["locked_until"] is not None) == (count >= 5)
    assert pg.session_rows() == []


def test_concurrent_successes_preserve_one_session(pg: PgContext) -> None:
    barrier = Barrier(4)

    def succeed(index: int) -> httpx.Response:
        barrier.wait(timeout=10)
        return pg.login(index % 2)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(succeed, range(4)))
    assert all(response.status_code == 200 for response in responses)
    tokens = [r.json()["sessionid"] for r in responses]
    assert len(set(tokens)) == 4
    assert len(pg.session_rows()) == 1
    for replica in (0, 1):
        statuses = [pg.validate(token, replica).status_code for token in tokens]
        assert statuses.count(200) == 1 and statuses.count(401) == 3


def test_postgres_uuid_timestamps_and_partial_unique_index(pg: PgContext) -> None:
    pg.login()
    row = pg.session_rows()[0]
    assert isinstance(row["id"], UUID) and isinstance(row["user_id"], UUID)
    for field in ("created_at", "last_activity_at", "expires_at"):
        assert row[field].utcoffset() is not None
    assert row["expires_at"] - row["last_activity_at"] == timedelta(minutes=30)
    indexes = {i["name"]: i for i in inspect(pg.engine).get_indexes("user_sessions")}
    assert indexes["uq_active_user_session"]["unique"]
    assert "revoked_at IS NULL" in str(
        indexes["uq_active_user_session"]["dialect_options"]["postgresql_where"]
    )
    values = dict(
        user_id=pg.user_id,
        token_hash=uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    with pytest.raises(IntegrityError):
        with pg.engine.begin() as db:
            db.execute(pg.sessions.insert().values(**values))
    # PostgreSQL's partial index permits historical revoked sessions.
    with pg.engine.begin() as db:
        db.execute(pg.sessions.insert().values(**values, revoked_at=datetime.now(UTC)))
    assert len(pg.session_rows()) == 2


def test_failed_login_transaction_restores_prior_state(
    pg: PgContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = pg.login().json()["sessionid"]
    assert pg.login(1, "wrong").status_code == 401
    before_user, before_sessions = pg.user(), pg.session_rows()
    # Cause a real PostgreSQL CHECK violation at insertion, after reset + delete.
    # An old expiry is earlier than the database-generated creation timestamp.
    monkeypatch.setattr(pg.a, "SESSION_DURATION", timedelta(days=-1))
    assert pg.login(0).status_code == 500
    assert pg.user() == before_user
    assert pg.session_rows() == before_sessions
    assert pg.validate(first, 1).status_code == 200
    assert pg.login(1).status_code == 200


def test_cookie_created_by_a_is_valid_on_b_without_refresh(pg: PgContext) -> None:
    response = pg.login(0)
    assert response.status_code == 200
    token = response.cookies["ako_session"]
    before = pg.session_rows()
    check = pg.clients[1].get("/session", headers={"Cookie": f"ako_session={token}"})
    assert check.status_code == 200
    assert check.json()["user_id"] == str(pg.user_id)
    assert pg.session_rows() == before
    assert "set-cookie" not in check.headers


@pytest.mark.parametrize("state", ["expired", "revoked", "inactive"])
def test_cookie_cannot_restore_invalid_postgres_session(
    pg: PgContext, state: str
) -> None:
    token = pg.login(0).cookies["ako_session"]
    now = datetime.now(UTC)
    if state == "expired":
        pg.update_session(
            created_at=now - timedelta(hours=1), expires_at=now - timedelta(seconds=1)
        )
    elif state == "revoked":
        pg.update_session(revoked_at=now)
    else:
        with pg.b.engine.begin() as db:
            db.execute(
                pg.users.update()
                .where(pg.users.c.id == pg.user_id)
                .values(is_active=False)
            )
    before = pg.session_rows()
    response = pg.clients[1].get("/session", headers={"Cookie": f"ako_session={token}"})
    assert response.status_code == 401
    assert pg.session_rows() == before
    assert "set-cookie" not in response.headers


def test_conflicting_valid_identities_rejected(pg: PgContext) -> None:
    teacher_token = pg.login(0).json()["sessionid"]
    other_username = f"other_{uuid4().hex}"
    with pg.b.engine.begin() as db:
        db.execute(
            pg.users.insert().values(
                username=other_username,
                display_name="Other",
                role="coordinator",
                password_hash=pg.b.password_hash("OtherPass!", os.urandom(16)),
            )
        )
    response = pg.clients[1].post(
        "/login",
        headers={"Cookie": ""},
        json={"username": other_username, "password": "OtherPass!"},
    )
    assert response.status_code == 200
    other_token = response.json()["sessionid"]
    conflict = pg.clients[0].get(
        "/session",
        headers={
            "Cookie": f"ako_session={teacher_token}",
            "Authorization": f"Bearer {other_token}",
        },
    )
    assert conflict.status_code == 401
    assert pg.validate(teacher_token, 0).status_code == 200
    assert pg.validate(other_token, 1).status_code == 200
