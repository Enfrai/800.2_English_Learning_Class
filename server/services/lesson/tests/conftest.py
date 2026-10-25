"""Shared pytest fixtures for the Lesson service.

Tests need a PostgreSQL server. ``TEST_DATABASE_URL`` points at it, for
example ``postgresql+psycopg://postgres:test@localhost:55432/postgres``.
A new database with a random name is created for the test run and dropped
afterwards, so the database named in the URL is never changed (Test Plan
section 3: tests never touch the real database).

Each test runs inside a transaction that is rolled back, so tests are
independent and can run in any order.

Author: Pei Wu
Date: 25 Oct 2026
"""

import os
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from models import Base, lesson_review_logs, lessons

TODAY = date(2026, 10, 25)


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
def coordinator_id() -> UUID:
    """Id of a made-up coordinator. Users live in the User Service database."""
    return uuid4()


@pytest.fixture
def new_lesson(db: Session) -> Callable[..., UUID]:
    """Create a lesson (US-006 owns the real workflow) and return its id."""

    def create(**values: Any) -> UUID:
        return db.execute(
            lessons.insert()
            .values(
                id=uuid4(),
                title="Te reo Māori greetings",
                lesson_date=TODAY,
                created_by=uuid4(),
                **values,
            )
            .returning(lessons.c.id)
        ).scalar_one()

    return create


@pytest.fixture
def lesson_row(db: Session) -> Callable[[UUID], dict[str, Any]]:
    """Read a lesson as stored."""

    def read(lesson_id: UUID) -> dict[str, Any]:
        query = select(lessons).where(lessons.c.id == lesson_id)
        return dict(db.execute(query).mappings().one())

    return read


@pytest.fixture
def review_log(db: Session) -> Callable[[UUID], list[dict[str, Any]]]:
    """Read a lesson's review history (order not guaranteed in one transaction)."""

    def read(lesson_id: UUID) -> list[dict[str, Any]]:
        query = (
            select(lesson_review_logs)
            .where(lesson_review_logs.c.lesson_id == lesson_id)
            .order_by(lesson_review_logs.c.created_at)
        )
        return [dict(row) for row in db.execute(query).mappings()]

    return read
