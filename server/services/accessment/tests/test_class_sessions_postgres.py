"""Verify cross-replica classroom creation and attendance/delete locking in PostgreSQL.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

from attendance import mark_present
from class_sessions import create_session_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import attendance_records, class_sessions
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import sessionmaker

DAY = date(2026, 10, 24)


def test_two_replicas_start_one_class(engine: Engine) -> None:
    """
    Verify that two replicas start one class.
    """
    factory = sessionmaker(engine)
    owner = uuid4()

    def staff():
        """
        Prepare or exercise staff in the test class sessions postgres test scenario.
        """
        return SimpleNamespace(
            staff=SimpleNamespace(id=owner, role="teacher"), authorization="test-only"
        )

    clients = []
    for _ in range(2):
        app = FastAPI()
        app.include_router(create_session_router(factory, staff, lambda: DAY))
        clients.append(TestClient(app))
    try:
        with ThreadPoolExecutor(max_workers=8) as workers:
            replies = list(
                workers.map(
                    lambda index: clients[index % 2].post("/sessions/today").json(),
                    range(8),
                )
            )
        assert len({reply["id"] for reply in replies}) == 1
        assert sum(reply["created"] for reply in replies) == 1
        with factory() as db:
            assert (
                len(
                    db.execute(
                        select(class_sessions).where(
                            class_sessions.c.created_by == owner
                        )
                    ).all()
                )
                == 1
            )
    finally:
        for client in clients:
            client.close()
        with factory.begin() as db:
            db.execute(
                class_sessions.delete().where(class_sessions.c.created_by == owner)
            )


def test_attendance_commit_prevents_a_waiting_deletion(engine: Engine) -> None:
    """
    Verify that attendance commit prevents a waiting deletion.
    """
    factory = sessionmaker(engine)
    owner, learner = uuid4(), uuid4()
    with factory.begin() as db:
        sid = db.execute(
            class_sessions.insert()
            .values(session_date=DAY, created_by=owner)
            .returning(class_sessions.c.id)
        ).scalar_one()
    written, deleting, release = Event(), Event(), Event()

    def staff():
        """
        Prepare or exercise staff in the test class sessions postgres test scenario.
        """
        return SimpleNamespace(
            staff=SimpleNamespace(id=owner, role="teacher"), authorization="test-only"
        )

    app = FastAPI()
    app.include_router(create_session_router(factory, staff, lambda: DAY))
    client = TestClient(app)

    def before_statement(connection, cursor, statement, parameters, context, many):
        """
        Observe database execution before the statement to coordinate the concurrency
        scenario.
        """
        if "SELECT class_sessions.id," in statement and "FOR UPDATE" in statement:
            deleting.set()

    event.listen(engine, "before_cursor_execute", before_statement)

    def record():
        """
        Inspect or record record events for the surrounding database or HTTP test.
        """
        with factory.begin() as db:
            mark_present(
                db, session_id=sid, learner_id=learner, recorded_by=owner, today=DAY
            )
            written.set()
            assert release.wait(10), "Delete request never reached the classroom lock"

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            recording = workers.submit(record)
            assert written.wait(10)
            deletion = workers.submit(lambda: client.delete(f"/sessions/{sid}"))
            assert deleting.wait(10)
            release.set()
            recording.result(timeout=10)
            response = deletion.result(timeout=10)
        assert response.status_code == 409
        assert (
            response.json()["detail"]
            == "This session has attendance and cannot be deleted"
        )
        with factory() as db:
            assert (
                db.execute(
                    select(class_sessions.c.id).where(class_sessions.c.id == sid)
                ).scalar_one()
                == sid
            )
            assert (
                db.execute(
                    select(attendance_records.c.learner_id).where(
                        attendance_records.c.session_id == sid
                    )
                ).scalar_one()
                == learner
            )
    finally:
        release.set()
        event.remove(engine, "before_cursor_execute", before_statement)
        client.close()
        with factory.begin() as db:
            db.execute(
                attendance_records.delete().where(
                    attendance_records.c.session_id == sid
                )
            )
            db.execute(class_sessions.delete().where(class_sessions.c.id == sid))
