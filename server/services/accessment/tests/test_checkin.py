"""Unit tests for QR check-in tokens and learner sign-in (US-012).

Cases UT-64 (the check-in code works for at most four hours and stops when
closed), the sign-in part of UT-65, UT-66 (privacy) and UT-67 (wrong-name
limit) from the Test Plan, section 4.9. Check-in windows are inserted
directly because opening check-in is US-011.

Author: Pei Wu
Date: 25 Oct 2026
"""

import secrets
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from attendance import AlreadySignedInError, present_count
from checkin import (
    CHECKIN_CLOSED,
    CheckinClosedError,
    CheckinExpiredError,
    CheckinSessionPastError,
    CheckinUnavailableError,
    UnknownCheckinTokenError,
    blocked_until,
    device_key,
    find_open_checkin,
    hash_token,
    record_wrong_name,
    sign_in,
)
from models import attendance_records, checkin_windows, signin_failures
from sqlalchemy import select
from sqlalchemy.orm import Session

OPENED = datetime(2026, 10, 25, 5, 0, tzinfo=UTC)  # 6 pm in Auckland

OpenWindow = Callable[..., tuple[str, UUID]]


@pytest.fixture
def open_window(
    db: Session, new_session: Callable[..., UUID], today: date
) -> OpenWindow:
    """Open check-in for a class and return its token and session id."""

    def create(
        session_date: date | None = None,
        closed_after: timedelta | None = None,
        hours: int = 4,
    ) -> tuple[str, UUID]:
        session_id = new_session(session_date or today)
        token = secrets.token_urlsafe(32)
        db.execute(
            checkin_windows.insert().values(
                id=uuid4(),
                session_id=session_id,
                token_hash=hash_token(token),
                opened_by=uuid4(),
                opened_at=OPENED,
                expires_at=OPENED + timedelta(hours=hours),
                closed_at=None if closed_after is None else OPENED + closed_after,
            )
        )
        return token, session_id

    return create


def find(db: Session, token: str | None, after: timedelta, today: date):
    return find_open_checkin(db, token, now=OPENED + after, today=today)


# Finding an open check-in (US-012 AC1, AC5; Test Plan UT-64)


def test_open_check_in_gives_the_class_and_its_date(
    db: Session, open_window: OpenWindow, today: date
) -> None:
    token, session_id = open_window()

    found = find(db, token, timedelta(minutes=1), today)

    assert found.session_id == session_id
    assert found.session_date == today
    assert found.expires_at == OPENED + timedelta(hours=4)


def test_check_in_works_at_3h59_and_is_refused_from_4_hours(
    db: Session, open_window: OpenWindow, today: date
) -> None:
    token, _ = open_window()

    find(db, token, timedelta(hours=3, minutes=59), today)
    with pytest.raises(CheckinExpiredError):
        find(db, token, timedelta(hours=4), today)
    with pytest.raises(CheckinExpiredError):
        find(db, token, timedelta(hours=4, minutes=1), today)


def test_check_in_is_refused_once_the_teacher_closes_it(
    db: Session, open_window: OpenWindow, today: date
) -> None:
    token, _ = open_window(closed_after=timedelta(minutes=30))

    find(db, token, timedelta(minutes=29), today)
    with pytest.raises(CheckinClosedError):
        find(db, token, timedelta(minutes=30), today)


@pytest.mark.parametrize("token", [None, "", "x" * 257, "made-up-token"])
def test_unknown_empty_or_overlong_token_is_refused(
    db: Session, open_window: OpenWindow, today: date, token: str | None
) -> None:
    open_window()

    with pytest.raises(UnknownCheckinTokenError):
        find(db, token, timedelta(minutes=1), today)


def test_check_in_for_a_class_before_today_is_refused(
    db: Session, open_window: OpenWindow, today: date
) -> None:
    token, _ = open_window(session_date=today - timedelta(days=1))

    with pytest.raises(CheckinSessionPastError):
        find(db, token, timedelta(minutes=1), today)


def test_every_refusal_shows_the_same_closed_message() -> None:
    errors = [
        UnknownCheckinTokenError(),
        CheckinClosedError(),
        CheckinExpiredError(),
        CheckinSessionPastError(),
    ]

    for error in errors:
        assert isinstance(error, CheckinUnavailableError)
        assert str(error) == CHECKIN_CLOSED
    assert len({error.reason for error in errors}) == len(errors)
    assert CHECKIN_CLOSED == "Check-in is closed. Please ask the teacher"


def test_only_the_token_hash_is_stored_and_each_token_finds_its_class(
    db: Session, open_window: OpenWindow, today: date
) -> None:
    first, first_session = open_window()
    second, second_session = open_window()

    stored = set(db.execute(select(checkin_windows.c.token_hash)).scalars())

    assert first not in stored and second not in stored
    assert hash_token(first) in stored and len(hash_token(first)) == 64
    assert find(db, first, timedelta(minutes=1), today).session_id == first_session
    assert find(db, second, timedelta(minutes=1), today).session_id == second_session


# Signing in (US-012 AC2, AC4; Test Plan UT-65, UT-66)


def test_sign_in_marks_present_under_the_teacher_who_opened_check_in(
    db: Session, open_window: OpenWindow, today: date
) -> None:
    token, session_id = open_window()
    checkin = find(db, token, timedelta(minutes=1), today)

    record = sign_in(db, checkin, uuid4(), today)

    assert record["status"] == "present"
    assert record["recorded_at"] is not None
    assert record["recorded_by"] == checkin.opened_by
    assert present_count(db, session_id) == 1


def test_second_sign_in_says_already_signed_in_and_adds_nothing(
    db: Session, open_window: OpenWindow, today: date
) -> None:
    token, session_id = open_window()
    checkin = find(db, token, timedelta(minutes=1), today)
    learner_id = uuid4()
    sign_in(db, checkin, learner_id, today)

    with pytest.raises(AlreadySignedInError) as error:
        sign_in(db, checkin, learner_id, today)

    assert str(error.value) == "Already signed in"
    assert present_count(db, session_id) == 1


def test_sign_in_stores_no_location_or_device_detail() -> None:
    columns = set(attendance_records.c.keys())

    assert columns == {
        "id",
        "session_id",
        "learner_id",
        "status",
        "recorded_by",
        "recorded_at",
        "corrected_by",
        "corrected_at",
    }
    assert set(signin_failures.c.keys()) == {"id", "key_hash", "failed_at"}


# Wrong-name limit (NFR-11; Test Plan UT-67)

START = datetime(2026, 10, 25, 6, 0, tzinfo=UTC)


def test_eleventh_try_after_ten_wrong_names_is_blocked_for_ten_minutes(
    db: Session,
) -> None:
    key = device_key("203.0.113.7", "secret")
    for n in range(10):
        assert blocked_until(db, key, START + timedelta(seconds=30 * n)) is None
        record_wrong_name(db, key, START + timedelta(seconds=30 * n))
    tenth = START + timedelta(seconds=270)

    assert blocked_until(db, key, tenth + timedelta(seconds=1)) == tenth + timedelta(
        minutes=10
    )
    assert blocked_until(db, key, tenth + timedelta(minutes=9, seconds=59))
    assert blocked_until(db, key, tenth + timedelta(minutes=10)) is None


def test_nine_wrong_names_do_not_block(db: Session) -> None:
    key = device_key("203.0.113.8", "secret")
    for n in range(9):
        record_wrong_name(db, key, START + timedelta(seconds=n))

    assert blocked_until(db, key, START + timedelta(minutes=1)) is None


def test_ten_wrong_names_spread_over_more_than_ten_minutes_do_not_block(
    db: Session,
) -> None:
    key = device_key("203.0.113.9", "secret")
    for n in range(10):
        record_wrong_name(db, key, START + timedelta(minutes=2 * n))

    assert blocked_until(db, key, START + timedelta(minutes=19)) is None


def test_block_applies_to_one_device_only(db: Session) -> None:
    blocked = device_key("203.0.113.10", "secret")
    for n in range(10):
        record_wrong_name(db, blocked, START + timedelta(seconds=n))

    other = device_key("203.0.113.11", "secret")
    assert blocked_until(db, other, START + timedelta(seconds=20)) is None


def test_device_address_is_never_stored(db: Session) -> None:
    key = device_key("203.0.113.12", "secret")

    record_wrong_name(db, key, START)

    stored = list(db.execute(select(signin_failures.c.key_hash)).scalars())
    assert stored == [key]
    assert len(key) == 64 and "203.0.113" not in key
    assert device_key("203.0.113.12", "another secret") != key


def test_wrong_names_older_than_an_hour_are_deleted(db: Session) -> None:
    key = device_key("203.0.113.13", "secret")
    record_wrong_name(db, key, START)

    record_wrong_name(db, key, START + timedelta(hours=1, minutes=1))

    times = list(db.execute(select(signin_failures.c.failed_at)).scalars())
    assert times == [START + timedelta(hours=1, minutes=1)]
