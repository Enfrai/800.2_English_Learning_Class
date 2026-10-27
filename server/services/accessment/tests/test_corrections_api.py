"""API tests for correcting past attendance and its history (US-015).

The real app runs with its database session joined to the test's
transaction, and the User Service is replaced by a stand-in that also counts
calls. Covers US-015 AC1, AC2 and AC4 through the endpoints and ST-05's
"You do not have permission" for teachers.

Author: Pei Wu
Date: 25 Oct 2026
"""

import importlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
import user_client
from fastapi.testclient import TestClient
from models import attendance_records, class_sessions
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

TODAY = date(2026, 10, 25)
COORDINATOR = user_client.Staff(uuid4(), "Cy Coordinator", "coordinator")
TEACHER = user_client.Staff(uuid4(), "Tia Teacher", "teacher")


@dataclass
class UserServiceStandIn:
    learners: dict[UUID, str] = field(default_factory=dict)
    down: bool = False
    lookups: int = 0

    def current_staff(self, authorization: str) -> user_client.Staff:
        """
        Prepare or exercise current staff in the test corrections api test scenario.
        """
        who = authorization.removeprefix("Bearer ")
        if who not in ("coordinator", "teacher"):
            raise user_client.LoginRequiredError("Login required")
        return COORDINATOR if who == "coordinator" else TEACHER

    def learner_exists(self, authorization: str, learner_id: UUID) -> bool:
        """
        Prepare or exercise learner exists in the test corrections api test scenario.
        """
        self.lookups += 1
        if self.down:
            raise user_client.UserServiceError("down")
        return learner_id in self.learners

    def staff_names(self, authorization: str) -> dict[UUID, str]:
        """
        Prepare or exercise staff names in the test corrections api test scenario.
        """
        self.lookups += 1
        if self.down:
            raise user_client.UserServiceError("down")
        return {COORDINATOR.id: COORDINATOR.display_name}

    def learner_names(self, authorization: str, ids: set[UUID]) -> dict[UUID, str]:
        """
        Prepare or exercise learner names in the test corrections api test scenario.
        """
        self.lookups += 1
        return {i: self.learners[i] for i in ids if i in self.learners}


@dataclass
class Api:
    client: TestClient
    session: Session
    users: UserServiceStandIn

    def new_class(self, days_ago: int = 7) -> UUID:
        """
        Prepare or exercise new class in the test corrections api test scenario.
        """
        return self.session.execute(
            class_sessions.insert()
            .values(
                id=uuid4(),
                session_date=TODAY - timedelta(days=days_ago),
                created_by=TEACHER.id,
            )
            .returning(class_sessions.c.id)
        ).scalar_one()

    def new_learner(self, name: str, ticked_in: UUID | None = None) -> UUID:
        """
        Prepare or exercise new learner in the test corrections api test scenario.
        """
        learner_id = uuid4()
        self.users.learners[learner_id] = name
        if ticked_in:
            self.session.execute(
                attendance_records.insert().values(
                    id=uuid4(),
                    session_id=ticked_in,
                    learner_id=learner_id,
                    status="present",
                    recorded_by=TEACHER.id,
                )
            )
        return learner_id

    def correct(
        self,
        session_id: UUID,
        learner_id: UUID,
        present: bool,
        who: str,
        reason: str | None = None,
    ) -> Any:
        """
        Prepare or exercise correct in the test corrections api test scenario.
        """
        return self.client.post(
            f"/sessions/{session_id}/corrections",
            json={"learner_id": str(learner_id), "present": present, "reason": reason},
            headers={"Authorization": f"Bearer {who}"},
        )

    def get(self, path: str, who: str) -> Any:
        """
        Send a GET request through the test client with the supplied scenario data.
        """
        return self.client.get(path, headers={"Authorization": f"Bearer {who}"})


@pytest.fixture
def api(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Api]:
    # Importing app creates an engine but does not connect.
    """
    Provide injected API client and isolated application fixture.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused@localhost/unused")
    app_module: ModuleType = importlib.import_module("app")
    users = UserServiceStandIn()
    for name in ("current_staff", "learner_exists", "staff_names", "learner_names"):
        monkeypatch.setattr(user_client, name, getattr(users, name))
    monkeypatch.setattr(app_module, "club_today", lambda: TODAY)
    with engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint"
        )
        monkeypatch.setattr(app_module, "SessionLocal", factory)
        session = factory()
        try:
            yield Api(TestClient(app_module.app), session, users)
        finally:
            session.close()
            transaction.rollback()


# ST-05: teachers cannot correct or read the history


def test_teacher_is_refused_before_any_lookup(api: Api) -> None:
    """
    Verify that teacher is refused before any lookup.
    """
    class_id = api.new_class()
    learner = api.new_learner("Sione Taufa")

    correction = api.correct(class_id, learner, True, "teacher")
    history = api.get(f"/sessions/{class_id}/corrections", "teacher")

    assert correction.status_code == 403
    assert correction.json() == {"detail": "You do not have permission"}
    assert history.status_code == 403
    assert api.users.lookups == 0


# AC1, AC2: correcting


def test_coordinator_marks_a_missing_learner_present(api: Api) -> None:
    """
    Verify that coordinator marks a missing learner present.
    """
    class_id = api.new_class()
    api.new_learner("Aroha Ngata", ticked_in=class_id)
    missing = api.new_learner("Sione Taufa")

    response = api.correct(class_id, missing, True, "coordinator")

    assert response.status_code == 200
    assert response.json()["present_count"] == 2
    assert response.json()["attendance"]["status"] == "present"


def test_coordinator_unticks_a_mistake_and_the_count_falls(api: Api) -> None:
    """
    Verify that coordinator unticks a mistake and the count falls.
    """
    class_id = api.new_class()
    mistake = api.new_learner("Mere Walker", ticked_in=class_id)
    api.new_learner("Aroha Ngata", ticked_in=class_id)

    response = api.correct(class_id, mistake, False, "coordinator")

    assert response.status_code == 200
    assert response.json()["present_count"] == 1
    assert response.json()["attendance"]["status"] == "absent"


def test_todays_class_is_changed_on_its_list_not_corrected(api: Api) -> None:
    """
    Verify that todays class is changed on its list not corrected.
    """
    class_id = api.new_class(days_ago=0)
    learner = api.new_learner("Aroha Ngata")

    response = api.correct(class_id, learner, True, "coordinator")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "This class is today. Change it on the class list"
    }


@pytest.mark.parametrize("missing", ["learner", "class"])
def test_unknown_learner_or_class_is_not_found(api: Api, missing: str) -> None:
    """
    Verify that unknown learner or class is not found.
    """
    class_id = api.new_class() if missing == "learner" else uuid4()
    learner = uuid4() if missing == "learner" else api.new_learner("Ana Silva")

    response = api.correct(class_id, learner, True, "coordinator")

    assert response.status_code == 404


def test_user_service_down_is_reported(api: Api) -> None:
    """
    Verify that user service down is reported.
    """
    api.users.down = True

    response = api.correct(api.new_class(), uuid4(), True, "coordinator")

    assert response.status_code == 503


# AC4: history with names, and the corrected list


def test_history_shows_who_what_and_when_with_names(api: Api) -> None:
    """
    Verify that history shows who what and when with names.
    """
    class_id = api.new_class()
    mistake = api.new_learner("Mere Walker", ticked_in=class_id)
    missing = api.new_learner("Sione Taufa")
    api.correct(class_id, missing, True, "coordinator")
    api.correct(class_id, mistake, False, "coordinator", reason="left early")

    response = api.get(f"/sessions/{class_id}/corrections", "coordinator")

    assert response.status_code == 200
    history = response.json()
    assert [
        (e["learner_name"], e["old_status"], e["new_status"], e["corrected_by_name"])
        for e in history
    ] == [
        ("Sione Taufa", "absent", "present", "Cy Coordinator"),
        ("Mere Walker", "present", "absent", "Cy Coordinator"),
    ]
    assert history[1]["reason"] == "left early"
    assert history[0]["created_at"] < history[1]["created_at"]


def test_class_without_corrections_has_an_empty_history(api: Api) -> None:
    """
    Verify that class without corrections has an empty history.
    """
    class_id = api.new_class()

    response = api.get(f"/sessions/{class_id}/corrections", "coordinator")

    assert response.json() == []
    assert api.users.lookups == 0


def test_attendance_list_names_every_corrected_learner(api: Api) -> None:
    """
    Verify that attendance list names every corrected learner.
    """
    class_id = api.new_class()
    mistake = api.new_learner("Mere Walker", ticked_in=class_id)
    untouched = api.new_learner("Aroha Ngata", ticked_in=class_id)
    missing = api.new_learner("Sione Taufa")
    api.correct(class_id, missing, True, "coordinator")
    api.correct(class_id, mistake, False, "coordinator")

    shown = api.get(f"/sessions/{class_id}/attendance", "teacher").json()

    assert set(shown["corrected_learner_ids"]) == {str(missing), str(mistake)}
    assert str(untouched) not in shown["corrected_learner_ids"]
    assert shown["present_count"] == 2
    assert shown["editable"] is False
