"""Unit tests for attendance in class (US-004).

Cases UT-26, UT-27, UT-28, UT-30 and UT-31 from the Test Plan, section 4.4.
UT-29 ("Add and mark present") is in test_user_client.py.

Author: Pei Wu
Date: 23 Oct 2026
Updated: Shuohui Liu, 26 Oct 2026
"""

from collections.abc import Callable
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from attendance import (
    AlreadySignedInError,
    NotMarkedPresentError,
    PastSessionError,
    SessionNotFoundError,
    check_session_is_running,
    mark_present,
    present_count,
    present_records,
    unmark,
)
from models import attendance_records
from sqlalchemy import func, select
from sqlalchemy.orm import Session

NewSession = Callable[..., UUID]


def tick(db: Session, session_id: UUID, learner_id: UUID, today: date) -> dict:
    return mark_present(
        db,
        session_id=session_id,
        learner_id=learner_id,
        recorded_by=uuid4(),
        today=today,
    )


def record_count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(attendance_records)).scalar_one()


# UT-26 (US-004 AC1)


def test_ticked_learner_is_present_with_the_time_and_count_rises_by_1(
    db: Session, new_session: NewSession, teacher_id: UUID, today: date
) -> None:
    session_id = new_session()
    learner_id = uuid4()

    record = mark_present(
        db,
        session_id=session_id,
        learner_id=learner_id,
        recorded_by=teacher_id,
        today=today,
    )

    assert record["status"] == "present"
    assert record["learner_id"] == learner_id
    assert record["recorded_by"] == teacher_id
    assert record["recorded_at"] is not None
    assert present_count(db, session_id) == 1


def test_present_records_list_who_is_here_earliest_first(
    db: Session, new_session: NewSession, today: date
) -> None:
    session_id = new_session()
    learners = [uuid4(), uuid4(), uuid4()]
    for learner_id in learners:
        tick(db, session_id, learner_id, today)

    records = present_records(db, session_id)

    assert [record["learner_id"] for record in records] == learners


# UT-27 (US-004 AC3)


def test_ticking_the_same_learner_again_says_already_signed_in(
    db: Session, new_session: NewSession, today: date
) -> None:
    session_id = new_session()
    learner_id = uuid4()
    first = tick(db, session_id, learner_id, today)

    with pytest.raises(AlreadySignedInError) as error:
        tick(db, session_id, learner_id, today)

    assert str(error.value) == "Already signed in"
    assert error.value.record["id"] == first["id"]
    assert record_count(db) == 1
    assert present_count(db, session_id) == 1


def test_same_learner_can_be_present_at_two_different_sessions(
    db: Session, new_session: NewSession, today: date
) -> None:
    learner_id = uuid4()
    first_session, second_session = new_session(), new_session(today - timedelta(days=1))

    tick(db, first_session, learner_id, today)
    tick(db, second_session, learner_id, today - timedelta(days=1))

    assert present_count(db, first_session) == 1
    assert present_count(db, second_session) == 1


# UT-28 (US-004 AC4)


def test_unticking_removes_the_record_and_count_falls_by_1(
    db: Session, new_session: NewSession, today: date
) -> None:
    session_id = new_session()
    mistake, other = uuid4(), uuid4()
    tick(db, session_id, mistake, today)
    tick(db, session_id, other, today)

    unmark(db, session_id=session_id, learner_id=mistake, today=today)

    assert present_count(db, session_id) == 1
    assert [r["learner_id"] for r in present_records(db, session_id)] == [other]


def test_learner_can_be_ticked_again_after_unticking(
    db: Session, new_session: NewSession, today: date
) -> None:
    session_id = new_session()
    learner_id = uuid4()
    tick(db, session_id, learner_id, today)
    unmark(db, session_id=session_id, learner_id=learner_id, today=today)

    tick(db, session_id, learner_id, today)

    assert present_count(db, session_id) == 1


def test_unticking_a_learner_who_is_not_present_is_reported(
    db: Session, new_session: NewSession, today: date
) -> None:
    session_id = new_session()

    with pytest.raises(NotMarkedPresentError):
        unmark(db, session_id=session_id, learner_id=uuid4(), today=today)


# UT-30 (US-004)


@pytest.mark.parametrize("present", [0, 1, 50])
def test_present_count_is_correct(
    db: Session, new_session: NewSession, today: date, present: int
) -> None:
    session_id, other_session = new_session(), new_session(today - timedelta(days=1))
    for _ in range(present):
        tick(db, session_id, uuid4(), today)
    tick(db, other_session, uuid4(), today - timedelta(days=1))

    assert present_count(db, session_id) == present


# UT-31 (US-015 AC3)


def test_attendance_of_a_past_session_cannot_be_changed(
    db: Session, new_session: NewSession, today: date
) -> None:
    session_id = new_session(today - timedelta(days=1))
    learner_id = uuid4()

    with pytest.raises(PastSessionError) as tick_error:
        tick(db, session_id, learner_id, today)
    with pytest.raises(PastSessionError) as untick_error:
        unmark(db, session_id=session_id, learner_id=learner_id, today=today)

    message = "Only a coordinator can correct past attendance"
    assert str(tick_error.value) == message
    assert str(untick_error.value) == message
    assert present_count(db, session_id) == 0


def test_todays_session_is_running(
    db: Session, new_session: NewSession, today: date
) -> None:
    check_session_is_running(db, new_session(today), today)


# Other failures


def test_unknown_session_is_reported(db: Session, today: date) -> None:
    with pytest.raises(SessionNotFoundError):
        tick(db, uuid4(), uuid4(), today)
    with pytest.raises(SessionNotFoundError):
        unmark(db, session_id=uuid4(), learner_id=uuid4(), today=today)


def test_absent_record_becomes_present_when_ticked(
    db: Session, new_session: NewSession, teacher_id: UUID, today: date
) -> None:
    session_id = new_session()
    learner_id = uuid4()
    db.execute(
        attendance_records.insert().values(
            id=uuid4(),
            session_id=session_id,
            learner_id=learner_id,
            status="absent",
            recorded_by=teacher_id,
        )
    )

    record = tick(db, session_id, learner_id, today)

    assert record["status"] == "present"
    assert record_count(db) == 1
    assert present_count(db, session_id) == 1


def test_absent_record_is_not_counted_or_listed_as_present(
    db: Session, new_session: NewSession, teacher_id: UUID, today: date
) -> None:
    session_id = new_session()
    absent_learner = uuid4()
    db.execute(
        attendance_records.insert().values(
            id=uuid4(),
            session_id=session_id,
            learner_id=absent_learner,
            status="absent",
            recorded_by=teacher_id,
        )
    )
    tick(db, session_id, uuid4(), today)

    assert present_count(db, session_id) == 1
    assert absent_learner not in [
        r["learner_id"] for r in present_records(db, session_id)
    ]
    with pytest.raises(NotMarkedPresentError):
        unmark(db, session_id=session_id, learner_id=absent_learner, today=today)
