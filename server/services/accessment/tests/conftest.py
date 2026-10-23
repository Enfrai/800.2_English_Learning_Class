"""Shared pytest fixtures for the Accessment service.

Tests need a PostgreSQL server. ``TEST_DATABASE_URL`` points at it, for
example ``postgresql+psycopg://postgres:test@localhost:55432/postgres``.
A new database with a random name is created for the test run and dropped
afterwards, so the database named in the URL is never changed (Test Plan
section 3: tests never touch the real database).

Each test runs inside a transaction that is rolled back, so tests are
independent and can run in any order.

Author: Pei Wu
Date: 23 Oct 2026
"""

import os
from collections.abc import Callable, Iterator
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from models import Base, class_sessions

TODAY = date(2026, 10, 23)


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
        yield test_engine
    finally:
        test_engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            )
        admin.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A session whose changes are rolled back after the test."""
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def today() -> date:
    """A fixed club date, so results never depend on when tests run."""
    return TODAY


@pytest.fixture
def teacher_id() -> UUID:
    """Id of a made-up teacher. Users live in the User Service database."""
    return uuid4()


@pytest.fixture
def new_session(db: Session, teacher_id: UUID) -> Callable[..., UUID]:
    """Create a class session (US-014 owns the real workflow)."""

    def create(session_date: date = TODAY) -> UUID:
        return db.execute(
            class_sessions.insert()
            .values(id=uuid4(), session_date=session_date, created_by=teacher_id)
            .returning(class_sessions.c.id)
        ).scalar_one()

    return create
