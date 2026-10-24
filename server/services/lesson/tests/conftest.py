"""Shared pytest fixtures for the Lesson service.

Tests need a PostgreSQL server. ``TEST_DATABASE_URL`` points at it, for
example ``postgresql+psycopg://postgres:test@localhost:55432/postgres``.
A new database with a random name is created for the test run and dropped
afterwards, so the database named in the URL is never changed (Test Plan
section 3: tests never touch the real database).

Each test runs inside a transaction that is rolled back, so tests are
independent and can run in any order. Files go to a temporary folder.

Author: Sandhya Tiwari
Date: 23 Oct 2026
"""

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from files import FileStore
from lessons import seed_tags
from models import Base
from user_client import Staff

# app.py builds its engine when imported. It only connects when used, and the
# tests replace its sessions, so this address is never contacted.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused@localhost/unused")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL is not set. See the testing section in "
            "server/README.md.",
            pytrace=False,
        )
    server_url = make_url(url)
    # The name is generated here, never taken from input, so it is safe to
    # put in the SQL text (identifiers cannot be bound as parameters).
    database_name = f"ako_test_{uuid4().hex[:12]}"
    admin = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    test_engine = create_engine(server_url.set(database=database_name))
    try:
        Base.metadata.create_all(test_engine)
        with Session(test_engine) as db, db.begin():
            seed_tags(db)
        yield test_engine
    finally:
        test_engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
        admin.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator:
    """A connection whose changes are rolled back after the test."""
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def db(connection) -> Iterator[Session]:
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()


def make_staff(role: str, name: str) -> Staff:
    """A made-up staff member. Users live in the User Service database."""
    return Staff(uuid4(), name, role)


@pytest.fixture
def teacher() -> Staff:
    return make_staff("teacher", "Test Teacher")


@pytest.fixture
def other_teacher() -> Staff:
    return make_staff("teacher", "Second Teacher")


@pytest.fixture
def coordinator() -> Staff:
    return make_staff("coordinator", "Demo Coordinator")


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "lesson-files")


class LoggedIn:
    """Who the test client is logged in as. ``None`` means no login."""

    def __init__(self, staff: Staff | None) -> None:
        self.staff = staff


@pytest.fixture
def logged_in(teacher: Staff) -> LoggedIn:
    return LoggedIn(teacher)


@pytest.fixture
def client(
    connection, store: FileStore, logged_in: LoggedIn, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """The real Lesson Service API on the test database and file folder.

    Only the User Service call is replaced: change ``logged_in.staff`` to
    act as another user, or set it to ``None`` to send no login.
    """
    import app as lesson_app
    import user_client

    monkeypatch.setattr(
        lesson_app,
        "SessionLocal",
        sessionmaker(bind=connection, join_transaction_mode="create_savepoint"),
    )
    monkeypatch.setattr(lesson_app, "file_store", store)

    def current_staff(authorization: str) -> Staff:
        if logged_in.staff is None:
            raise user_client.LoginRequiredError("Login required")
        return logged_in.staff

    monkeypatch.setattr(user_client, "current_staff", current_staff)
    # Not used as a context manager, so the start-up step (create_all) is skipped.
    yield TestClient(lesson_app.app, headers={"Authorization": "Bearer test"})
