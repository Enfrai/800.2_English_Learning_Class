"""Verify QR open idempotency and close/sign-in locking across PostgreSQL replicas.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from checkin import CheckinClosedError, find_open_checkin, sign_in
from checkin_management import create_checkin_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import attendance_records, checkin_windows, class_sessions
from sqlalchemy import event, select
from sqlalchemy.orm import sessionmaker

DAY = date(2026, 10, 26)
NOW = datetime(2026, 10, 26, 0, tzinfo=UTC)


@pytest.fixture
def qr(engine, monkeypatch):
    """
    Provide the qr context and release its resources after use.
    """
    monkeypatch.setenv("CHECKIN_TOKEN_SECRET", "shared-test-key")
    monkeypatch.setenv("CHECKIN_PUBLIC_ORIGIN", "http://localhost:8080")
    factory = sessionmaker(engine)
    sid = uuid4()
    owner = uuid4()
    with factory.begin() as db:
        db.execute(
            class_sessions.insert().values(id=sid, session_date=DAY, created_by=owner)
        )

    def staff():
        """
        Prepare or exercise staff in the test checkin management postgres test scenario.
        """
        return SimpleNamespace(staff=SimpleNamespace(id=owner, role="teacher"))

    clients = []
    for _ in range(2):
        app = FastAPI()
        app.include_router(
            create_checkin_router(factory, staff, lambda: DAY, lambda: NOW)
        )
        clients.append(TestClient(app))
    yield factory, sid, clients
    for client in clients:
        client.close()
    with factory.begin() as db:
        db.execute(
            attendance_records.delete().where(attendance_records.c.session_id == sid)
        )
        db.execute(checkin_windows.delete().where(checkin_windows.c.session_id == sid))
        db.execute(class_sessions.delete().where(class_sessions.c.id == sid))


def test_two_replicas_open_exactly_one_window(qr):
    """
    Verify that two replicas open exactly one window.
    """
    factory, sid, clients = qr
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(
            pool.map(
                lambda i: clients[i % 2].post(f"/sessions/{sid}/check-in").json(),
                range(8),
            )
        )
    assert len({row["sign_in_url"] for row in replies}) == 1
    assert all(row["state"] == "open" for row in replies)
    with factory() as db:
        assert (
            len(
                db.execute(
                    select(checkin_windows).where(checkin_windows.c.session_id == sid)
                ).all()
            )
            == 1
        )


def test_close_commit_blocks_an_already_resolved_signin(qr, engine):
    """
    Verify that close commit blocks an already resolved signin.
    """
    factory, sid, clients = qr
    data = clients[0].post(f"/sessions/{sid}/check-in").json()
    token = data["sign_in_url"].rsplit("/", 1)[1]
    with factory() as db:
        opened = find_open_checkin(db, token, now=NOW, today=DAY)
    waiting = Event()

    def trace(connection, cursor, statement, parameters, context, many):
        """
        Inspect or record trace events for the surrounding database or HTTP test.
        """
        if (
            "SELECT class_sessions.session_date" in statement
            and "FOR UPDATE" in statement
        ):
            waiting.set()

    event.listen(engine, "before_cursor_execute", trace)

    def submit():
        """
        Prepare or exercise submit in the test checkin management postgres test
        scenario.
        """
        with factory.begin() as db:
            with pytest.raises(CheckinClosedError):
                sign_in(db, opened, uuid4(), DAY, now=NOW)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with factory.begin() as db:
                db.execute(
                    select(class_sessions.c.id)
                    .where(class_sessions.c.id == sid)
                    .with_for_update()
                )
                db.execute(
                    checkin_windows.update()
                    .where(checkin_windows.c.session_id == sid)
                    .values(closed_at=NOW)
                )
                result = pool.submit(submit)
                assert waiting.wait(5)
                assert not result.done()
            result.result(timeout=5)
    finally:
        event.remove(engine, "before_cursor_execute", trace)
    with factory() as db:
        assert (
            db.execute(
                select(attendance_records).where(attendance_records.c.session_id == sid)
            ).all()
            == []
        )
