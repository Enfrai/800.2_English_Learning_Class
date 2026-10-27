"""Shared pytest fixtures for the User service.

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
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from models import Base, users
from test_auth import context as context
from test_login import api as api
from test_postgres import pg as pg
from test_postgres import postgres_url as postgres_url


@pytest.fixture(scope="module")
def engine(request: pytest.FixtureRequest) -> Iterator[Engine]:
    """
    Provide the engine context and release its resources after use.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url and os.environ.get("US001_TEST_PG_URL"):
        # Reuse the identity-verified isolated US-001 runner, never the application URL.
        url = request.getfixturevalue("postgres_url")
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
def staff_id(db: Session) -> UUID:
    """Id of a made-up coordinator who adds and edits learners."""
    return db.execute(
        users.insert()
        .values(
            username="test_coordinator",
            password_hash="not-a-real-hash",
            display_name="Test Coordinator",
            role="coordinator",
        )
        .returning(users.c.id)
    ).scalar_one()
