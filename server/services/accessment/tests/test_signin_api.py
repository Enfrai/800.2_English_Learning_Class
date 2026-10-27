"""API tests for the public QR sign-in endpoints (US-012).

The real app runs with its database session joined to the test's
transaction, and the User Service lookup is replaced by a stand-in. Covers
US-012 AC1 to AC5 and how the wrong-name limit (UT-67) counts tries.

Author: Pei Wu
Date: 25 Oct 2026
"""

import importlib
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
import user_client
from checkin import hash_token
from fastapi.testclient import TestClient
from models import attendance_records, checkin_windows, class_sessions, signin_failures
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

TODAY = date(2026, 10, 25)
NOT_FOUND = "We could not find that name. Please ask the teacher"
CLOSED = "Check-in is closed. Please ask the teacher"


@dataclass
class UserServiceStandIn:
    """Answers name lookups like the User Service, and counts them."""

    learners: dict[tuple[str, str], str] = field(default_factory=dict)
    shared_names: set[tuple[str, str]] = field(default_factory=set)
    down: bool = False
    calls: int = 0

    def find(self, first: str, family: str) -> dict[str, Any]:
        """
        Prepare or exercise find in the test signin api test scenario.
        """
        self.calls += 1
        if self.down:
            raise user_client.UserServiceError("User service unavailable")
        name = (first.lower(), family.lower())
        if name in self.shared_names:
            raise user_client.AmbiguousSignInNameError("Several learners")
        if name not in self.learners:
            raise user_client.SignInNameNotFoundError("Learner not found")
        return {"id": self.learners[name], "first_name": first, "family_name": family}


@dataclass
class SignInApi:
    client: TestClient
    session: Session
    users: UserServiceStandIn
    opened_by: UUID = field(default_factory=uuid4)

    def open_check_in(self, closed: bool = False) -> tuple[str, UUID]:
        """
        Prepare or exercise open check in in the test signin api test scenario.
        """
        session_id = self.session.execute(
            class_sessions.insert()
            .values(id=uuid4(), session_date=TODAY, created_by=self.opened_by)
            .returning(class_sessions.c.id)
        ).scalar_one()
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        self.session.execute(
            checkin_windows.insert().values(
                id=uuid4(),
                session_id=session_id,
                token_hash=hash_token(token),
                opened_by=self.opened_by,
                opened_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(hours=3),
                closed_at=now - timedelta(seconds=1) if closed else None,
            )
        )
        return token, session_id

    def sign_in(
        self,
        token: str,
        first: str,
        family: str,
        device: str,
        phone_id: str | None = None,
    ) -> Any:
        """
        Prepare or exercise sign in in the test signin api test scenario.
        """
        headers = {"X-Real-IP": device}
        if phone_id:
            headers["X-Device-Id"] = phone_id
        return self.client.post(
            f"/checkin/{token}/sign-in",
            json={"first_name": first, "family_name": family},
            headers=headers,
        )

    def count(self, table: Any) -> int:
        """
        Prepare or exercise count in the test signin api test scenario.
        """
        return self.session.execute(
            select(func.count()).select_from(table)
        ).scalar_one()


@pytest.fixture
def app_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    # Importing app creates an engine but does not connect.
    """
    Prepare or exercise app module in the test signin api test scenario.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused@localhost/unused")
    return importlib.import_module("app")


@pytest.fixture
def api(
    engine: Engine, app_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SignInApi]:
    """
    Provide injected API client and isolated application fixture.
    """
    users = UserServiceStandIn()
    monkeypatch.setattr(user_client, "find_learner_for_sign_in", users.find)
    monkeypatch.setattr(app_module, "club_today", lambda: TODAY)
    with engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint"
        )
        monkeypatch.setattr(app_module, "SessionLocal", factory)
        session = factory()
        try:
            yield SignInApi(TestClient(app_module.app), session, users)
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def aroha(api: SignInApi) -> str:
    """
    Prepare or exercise aroha in the test signin api test scenario.
    """
    learner_id = str(uuid4())
    api.users.learners[("aroha", "ngata")] = learner_id
    return learner_id


# AC1 and AC5: opening the sign-in page


def test_open_check_in_tells_the_page_its_class_date(api: SignInApi) -> None:
    """
    Verify that open check in tells the page its class date.
    """
    token, _ = api.open_check_in()

    response = api.client.get(f"/checkin/{token}")

    assert response.status_code == 200
    assert response.json() == {"session_date": "2026-10-25"}


@pytest.mark.parametrize("closed", [True, False])
def test_closed_or_unknown_check_in_shows_the_closed_message(
    api: SignInApi, closed: bool
) -> None:
    """
    Verify that closed or unknown check in shows the closed message.
    """
    token, _ = api.open_check_in(closed=True)
    path = f"/checkin/{token if closed else 'made-up-token'}"

    response = api.client.get(path)
    sign_in = api.client.post(f"{path}/sign-in", json={"first_name": "A"})

    assert response.status_code == 404
    assert response.json() == {"detail": CLOSED}
    assert sign_in.json() == {"detail": CLOSED}
    assert api.users.calls == 0


# AC2 to AC4: signing in


def test_matching_name_signs_in_under_the_teacher_who_opened_check_in(
    api: SignInApi, aroha: str
) -> None:
    """
    Verify that matching name signs in under the teacher who opened check in.
    """
    token, session_id = api.open_check_in()

    response = api.sign_in(token, "Aroha", "Ngata", "198.51.100.1")

    assert response.status_code == 201
    assert response.json() == {
        "message": "You are signed in",
        "session_date": "2026-10-25",
    }
    record = api.session.execute(select(attendance_records)).mappings().one()
    assert str(record["learner_id"]) == aroha
    assert record["session_id"] == session_id
    assert record["recorded_by"] == api.opened_by


def test_second_sign_in_says_already_signed_in(api: SignInApi, aroha: str) -> None:
    """
    Verify that second sign in says already signed in.
    """
    token, _ = api.open_check_in()
    api.sign_in(token, "Aroha", "Ngata", "198.51.100.1")

    response = api.sign_in(token, "Aroha", "Ngata", "198.51.100.1")

    assert response.status_code == 409
    assert response.json() == {"detail": "Already signed in"}
    assert api.count(attendance_records) == 1


def test_unknown_name_is_refused_counted_and_records_nothing(
    api: SignInApi,
) -> None:
    """
    Verify that unknown name is refused counted and records nothing.
    """
    token, _ = api.open_check_in()

    response = api.sign_in(token, "Nobody", "Here", "198.51.100.1")

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND}
    assert api.count(attendance_records) == 0
    assert api.count(signin_failures) == 1


def test_shared_name_asks_for_the_teacher_and_is_not_counted(
    api: SignInApi,
) -> None:
    """
    Verify that shared name asks for the teacher and is not counted.
    """
    api.users.shared_names.add(("mere", "walker"))
    token, _ = api.open_check_in()

    response = api.sign_in(token, "Mere", "Walker", "198.51.100.1")

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND}
    assert api.count(attendance_records) == 0
    assert api.count(signin_failures) == 0


def test_user_service_down_is_reported_and_not_counted(api: SignInApi) -> None:
    """
    Verify that user service down is reported and not counted.
    """
    api.users.down = True
    token, _ = api.open_check_in()

    response = api.sign_in(token, "Aroha", "Ngata", "198.51.100.1")

    assert response.status_code == 503
    assert response.json() == {"detail": "User service unavailable"}
    assert api.count(signin_failures) == 0


# Wrong-name limit (UT-67)


def test_eleventh_try_is_blocked_even_with_a_real_name(
    api: SignInApi, aroha: str
) -> None:
    """
    Verify that eleventh try is blocked even with a real name.
    """
    token, _ = api.open_check_in()
    for n in range(10):
        assert api.sign_in(token, f"Guess{n}", "X", "198.51.100.7").status_code == 404

    blocked = api.sign_in(token, "Aroha", "Ngata", "198.51.100.7")
    other_device = api.sign_in(token, "Aroha", "Ngata", "198.51.100.8")

    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many tries. Please ask the teacher"}
    assert other_device.status_code == 201
    assert api.users.calls == 11


def test_one_phone_is_blocked_but_classmates_on_the_same_wifi_are_not(
    api: SignInApi, aroha: str
) -> None:
    """
    Verify that one phone is blocked but classmates on the same wifi are not.
    """
    token, _ = api.open_check_in()
    wifi, phone, classmate = "198.51.100.20", str(uuid4()), str(uuid4())
    for n in range(10):
        api.sign_in(token, f"Guess{n}", "X", wifi, phone)

    blocked = api.sign_in(token, "Aroha", "Ngata", wifi, phone)
    allowed = api.sign_in(token, "Aroha", "Ngata", wifi, classmate)

    assert blocked.status_code == 429
    assert allowed.status_code == 201


def test_changing_the_phone_id_every_time_still_hits_the_address_limit(
    api: SignInApi, aroha: str
) -> None:
    """
    Verify that changing the phone id every time still hits the address limit.
    """
    token, _ = api.open_check_in()
    wifi = "198.51.100.21"
    for n in range(50):
        assert (
            api.sign_in(token, f"Guess{n}", "X", wifi, str(uuid4())).status_code == 404
        )

    response = api.sign_in(token, "Aroha", "Ngata", wifi, str(uuid4()))

    assert response.status_code == 429
