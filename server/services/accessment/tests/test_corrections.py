"""Unit tests for correcting past attendance (US-015).

Cases UT-32 to UT-35 from the Test Plan, section 4.5, and the coordinator-
only rule of UT-31 for corrections (the in-class lock itself is tested in
test_attendance.py). Team decisions (25 Oct 2026): unticking here sets the
record to absent instead of deleting it; a learner with no record gets a new
present record.

Author: Pei Wu
Date: 25 Oct 2026
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from attendance import SessionNotFoundError, mark_present, present_count
from corrections import (
    NotCoordinatorError,
    SessionNotPastError,
    change_history,
    correct_attendance,
    corrected_learners,
)
from models import attendance_audits, attendance_records
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

NewSession = Callable[..., UUID]
COORDINATOR = uuid4()


@pytest.fixture
def last_week(new_session: NewSession, today: date) -> UUID:
    return new_session(today - timedelta(days=7))


def tick_in_class(db: Session, session_id: UUID, learner_id: UUID, day: date) -> None:
    mark_present(
        db, session_id=session_id, learner_id=learner_id, recorded_by=uuid4(), today=day
    )


def correct(
    db: Session,
    session_id: UUID,
    learner_id: UUID,
    present: bool,
    today: date,
    role: str = "coordinator",
    reason: str | None = None,
) -> dict[str, Any] | None:
    return correct_attendance(
        db,
        session_id=session_id,
        learner_id=learner_id,
        present=present,
        corrected_by=COORDINATOR,
        corrector_role=role,
        today=today,
        reason=reason,
    )


def log(db: Session) -> list[dict[str, Any]]:
    query = select(attendance_audits).order_by(attendance_audits.c.created_at)
    return [dict(row) for row in db.execute(query).mappings()]


def record_count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(attendance_records)).scalar_one()


# UT-32 (US-015 AC1)


def test_marking_a_missing_learner_present_creates_a_record_and_logs_it(
    db: Session, last_week: UUID, today: date
) -> None:
    learner_id = uuid4()

    record = correct(db, last_week, learner_id, True, today)

    assert record is not None
    assert record["status"] == "present"
    assert record["corrected_by"] == COORDINATOR
    assert record["corrected_at"] is not None
    assert present_count(db, last_week) == 1
    [entry] = log(db)
    assert entry["attendance_id"] == record["id"]
    assert (entry["old_status"], entry["new_status"]) == ("absent", "present")
    assert entry["corrected_by"] == COORDINATOR
    assert entry["created_at"] is not None


def test_correcting_an_absent_record_to_present_logs_it(
    db: Session, last_week: UUID, today: date
) -> None:
    learner_id = uuid4()
    tick_in_class(db, last_week, learner_id, today - timedelta(days=7))
    correct(db, last_week, learner_id, False, today)

    record = correct(db, last_week, learner_id, True, today)

    assert record is not None and record["status"] == "present"
    assert [(e["old_status"], e["new_status"]) for e in log(db)] == [
        ("present", "absent"),
        ("absent", "present"),
    ]


# UT-33 (US-015 AC2)


def test_unticking_a_mistake_sets_absent_and_the_count_falls(
    db: Session, last_week: UUID, today: date
) -> None:
    mistake, other = uuid4(), uuid4()
    for learner_id in (mistake, other):
        tick_in_class(db, last_week, learner_id, today - timedelta(days=7))

    record = correct(db, last_week, mistake, False, today)

    assert record is not None and record["status"] == "absent"
    assert present_count(db, last_week) == 1
    # Kept, not deleted, so the log entry still points at it.
    assert record_count(db) == 2
    [entry] = log(db)
    assert (entry["old_status"], entry["new_status"]) == ("present", "absent")
    assert entry["attendance_id"] == record["id"]


def test_reason_is_kept_trimmed_and_optional(
    db: Session, last_week: UUID, today: date
) -> None:
    correct(db, last_week, uuid4(), True, today, reason="  came late  ")
    correct(db, last_week, uuid4(), True, today, reason="   ")

    assert sorted(str(e["reason"]) for e in log(db)) == ["None", "came late"]


def test_no_change_writes_no_log(db: Session, last_week: UUID, today: date) -> None:
    learner_id = uuid4()
    tick_in_class(db, last_week, learner_id, today - timedelta(days=7))

    still_present = correct(db, last_week, learner_id, True, today)
    still_absent = correct(db, last_week, uuid4(), False, today)

    assert still_present is not None and still_present["status"] == "present"
    assert still_absent is None
    assert log(db) == []


# UT-31 for corrections: coordinators only, past classes only


def test_teacher_cannot_correct_and_nothing_changes(
    db: Session, last_week: UUID, today: date
) -> None:
    with pytest.raises(NotCoordinatorError) as error:
        correct(db, last_week, uuid4(), True, today, role="teacher")

    assert str(error.value) == "You do not have permission"
    assert record_count(db) == 0
    assert log(db) == []


@pytest.mark.parametrize("days_ahead", [0, 1])
def test_todays_or_a_future_class_is_not_corrected(
    db: Session, new_session: NewSession, today: date, days_ahead: int
) -> None:
    session_id = new_session(today + timedelta(days=days_ahead))

    with pytest.raises(SessionNotPastError):
        correct(db, session_id, uuid4(), True, today)


def test_unknown_class_is_reported(db: Session, today: date) -> None:
    with pytest.raises(SessionNotFoundError):
        correct(db, uuid4(), uuid4(), True, today)
    with pytest.raises(SessionNotFoundError):
        change_history(db, uuid4())


# UT-34 (US-015 AC4)


def test_history_lists_every_change_in_time_order(
    db: Session, last_week: UUID, today: date
) -> None:
    first, second = uuid4(), uuid4()
    tick_in_class(db, last_week, second, today - timedelta(days=7))
    correct(db, last_week, first, True, today)
    correct(db, last_week, second, False, today)

    history = change_history(db, last_week)

    assert [(e["learner_id"], e["old_status"], e["new_status"]) for e in history] == [
        (first, "absent", "present"),
        (second, "present", "absent"),
    ]
    assert history[0]["created_at"] < history[1]["created_at"]
    assert {e["corrected_by"] for e in history} == {COORDINATOR}


def test_class_with_no_corrections_has_an_empty_history(
    db: Session, last_week: UUID, today: date
) -> None:
    tick_in_class(db, last_week, uuid4(), today - timedelta(days=7))

    assert change_history(db, last_week) == []
    assert corrected_learners(db, last_week) == []


def test_history_and_corrected_list_belong_to_one_class(
    db: Session, new_session: NewSession, today: date
) -> None:
    class_a = new_session(today - timedelta(days=7))
    class_b = new_session(today - timedelta(days=14))
    learner_a, learner_b = uuid4(), uuid4()
    correct(db, class_a, learner_a, True, today)
    correct(db, class_b, learner_b, True, today)

    assert [e["learner_id"] for e in change_history(db, class_a)] == [learner_a]
    assert corrected_learners(db, class_a) == [learner_a]


def test_corrected_list_includes_learners_corrected_to_not_present(
    db: Session, last_week: UUID, today: date
) -> None:
    present, unticked = uuid4(), uuid4()
    tick_in_class(db, last_week, unticked, today - timedelta(days=7))
    correct(db, last_week, present, True, today)
    correct(db, last_week, unticked, False, today)

    assert set(corrected_learners(db, last_week)) == {present, unticked}


# UT-35: the change log is append-only


@pytest.mark.parametrize("change", ["update", "delete", "truncate"])
def test_log_entries_cannot_be_edited_deleted_or_emptied(
    db: Session, last_week: UUID, today: date, change: str
) -> None:
    correct(db, last_week, uuid4(), True, today)
    statement = {
        "update": attendance_audits.update().values(
            old_status="present", new_status="absent"
        ),
        "delete": attendance_audits.delete(),
        "truncate": text("TRUNCATE attendance_audits"),
    }[change]

    with pytest.raises(DBAPIError) as error, db.begin_nested():
        db.execute(statement)

    assert "attendance_audits is append-only" in str(error.value)
    assert len(log(db)) == 1


def test_corrected_record_cannot_be_deleted_while_it_is_logged(
    db: Session, last_week: UUID, today: date
) -> None:
    record = correct(db, last_week, uuid4(), True, today)
    assert record is not None

    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            attendance_records.delete().where(attendance_records.c.id == record["id"])
        )
