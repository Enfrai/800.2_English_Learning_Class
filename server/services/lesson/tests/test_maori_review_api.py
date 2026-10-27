"""API tests for flagging Māori content and recording its review (US-008).

The router runs on a test app whose database session joins the test's
transaction, and the User Service is replaced by a stand-in, so each test
chooses who is logged in.

Author: Pei Wu
Date: 25 Oct 2026
"""

from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import maori_review_api
import user_client
from models import lessons

TODAY = date(2026, 10, 25)
AUTHOR = user_client.Staff(uuid4(), "Ana Teacher", "teacher")
OTHER_TEACHER = user_client.Staff(uuid4(), "Ben Teacher", "teacher")
COORDINATOR = user_client.Staff(uuid4(), "Cy Coordinator", "coordinator")
STAFF = {"author": AUTHOR, "other": OTHER_TEACHER, "coordinator": COORDINATOR}


class Api:
    def __init__(self, client: TestClient, session: Session) -> None:
        """
        Initialize Api and retain the supplied constructor state.
        """
        self.client = client
        self.session = session

    def call(self, method: str, path: str, who: str | None, **kwargs: Any) -> Any:
        """
        Prepare or exercise call in the test maori review api test scenario.
        """
        headers = {"Authorization": f"Bearer {who}"} if who else {}
        return self.client.request(method, path, headers=headers, **kwargs)

    def new_lesson(self, **values: Any) -> UUID:
        """
        Provide fixture factory creating a lesson and its scenario data.
        """
        return self.session.execute(
            lessons.insert()
            .values(
                id=uuid4(),
                title="Te reo Māori greetings",
                lesson_date=TODAY,
                created_by=AUTHOR.id,
                **values,
            )
            .returning(lessons.c.id)
        ).scalar_one()

    def lesson(self, lesson_id: UUID) -> dict[str, Any]:
        """
        Prepare or exercise lesson in the test maori review api test scenario.
        """
        query = select(lessons).where(lessons.c.id == lesson_id)
        return dict(self.session.execute(query).mappings().one())


@pytest.fixture
def api(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Api]:
    """
    Provide injected API client and isolated application fixture.
    """
    def current_staff(authorization: str) -> user_client.Staff:
        """
        Prepare or exercise current staff in the test maori review api test scenario.
        """
        who = authorization.removeprefix("Bearer ")
        if who == "down":
            raise user_client.UserServiceError("User service unavailable")
        if who not in STAFF:
            raise user_client.LoginRequiredError("Login required")
        return STAFF[who]

    monkeypatch.setattr(user_client, "current_staff", current_staff)
    monkeypatch.setattr(maori_review_api, "club_today", lambda: TODAY)
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")

        def session_factory() -> Session:
            """
            Prepare or exercise session factory in the test maori review api test
            scenario.
            """
            return Session(bind=connection, join_transaction_mode="create_savepoint")

        app = FastAPI()
        app.include_router(maori_review_api.create_maori_review_router(session_factory))
        try:
            yield Api(TestClient(app), session)
        finally:
            session.close()
            transaction.rollback()


def flag(api: Api, lesson_id: UUID, who: str, value: bool = True) -> Any:
    """
    Prepare or exercise flag in the test maori review api test scenario.
    """
    return api.call(
        "PUT",
        f"/lessons/{lesson_id}/maori-content",
        who,
        json={"has_maori_content": value},
    )


def review(api: Api, lesson_id: UUID, who: str, **body: Any) -> Any:
    """
    Provide fixture helper recording a lesson review.
    """
    body = {"reviewer_name": "Aroha", "review_date": "2026-10-08", **body}
    return api.call("POST", f"/lessons/{lesson_id}/review", who, json=body)


# Login


@pytest.mark.parametrize(("who", "status"), [(None, 401), ("nobody", 401)])
def test_login_is_required(api: Api, who: str | None, status: int) -> None:
    """
    Verify that login is required.
    """
    lesson_id = api.new_lesson()

    assert api.call("GET", f"/lessons/{lesson_id}/review", who).status_code == status
    assert flag(api, lesson_id, who).status_code == status


def test_user_service_down_is_reported_not_hidden(api: Api) -> None:
    """
    Verify that user service down is reported not hidden.
    """
    response = api.call("GET", f"/lessons/{api.new_lesson()}/review", "down")

    assert response.status_code == 503
    assert response.json() == {"detail": "User service unavailable"}


# Flag (AC1)


def test_author_ticks_maori_content_and_sees_not_yet_reviewed(api: Api) -> None:
    """
    Verify that author ticks maori content and sees not yet reviewed.
    """
    lesson_id = api.new_lesson()

    response = flag(api, lesson_id, "author")

    assert response.status_code == 200
    assert response.json() == {
        "lesson_id": str(lesson_id),
        "has_maori_content": True,
        "review_status": "pending",
        "reviewer_name": None,
        "review_date": None,
        "label": "Māori content – not yet reviewed",
        "visible_to_learners": False,
    }


def test_another_teacher_cannot_tick_someone_elses_lesson(api: Api) -> None:
    """
    Verify that another teacher cannot tick someone elses lesson.
    """
    lesson_id = api.new_lesson()

    response = flag(api, lesson_id, "other")

    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission"}
    assert api.lesson(lesson_id)["has_maori_content"] is False


def test_coordinator_may_tick_any_lesson(api: Api) -> None:
    """
    Verify that coordinator may tick any lesson.
    """
    assert flag(api, api.new_lesson(), "coordinator").status_code == 200


def test_unknown_lesson_is_not_found(api: Api) -> None:
    """
    Verify that unknown lesson is not found.
    """
    assert flag(api, uuid4(), "coordinator").status_code == 404
    assert api.call("GET", f"/lessons/{uuid4()}/review", "author").status_code == 404


# Review (AC2, AC3)


def test_coordinator_records_review_and_label_changes(api: Api) -> None:
    """
    Verify that coordinator records review and label changes.
    """
    lesson_id = api.new_lesson()
    flag(api, lesson_id, "author")

    response = review(api, lesson_id, "coordinator")

    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "Reviewed by Aroha, 8 Oct 2026"
    assert body["review_date"] == "2026-10-08"
    assert body["visible_to_learners"] is True
    assert api.lesson(lesson_id)["reviewed_by"] == COORDINATOR.id
    shown = api.call("GET", f"/lessons/{lesson_id}/review", "author").json()
    assert shown["label"] == "Reviewed by Aroha, 8 Oct 2026"


def test_teacher_cannot_record_a_review(api: Api) -> None:
    """
    Verify that teacher cannot record a review.
    """
    lesson_id = api.new_lesson()
    flag(api, lesson_id, "author")

    response = review(api, lesson_id, "author")

    assert response.status_code == 403
    assert api.lesson(lesson_id)["review_status"] == "pending"


def test_bad_review_returns_every_message_and_changes_nothing(api: Api) -> None:
    """
    Verify that bad review returns every message and changes nothing.
    """
    lesson_id = api.new_lesson()
    flag(api, lesson_id, "author")

    response = review(
        api, lesson_id, "coordinator", reviewer_name=" ", review_date="2026-10-26"
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "errors": {
                "reviewer_name": "Reviewer name is required",
                "review_date": "Review date cannot be in the future",
            }
        }
    }
    assert api.lesson(lesson_id)["review_status"] == "pending"


def test_lesson_without_maori_content_cannot_be_reviewed(api: Api) -> None:
    """
    Verify that lesson without maori content cannot be reviewed.
    """
    response = review(api, api.new_lesson(), "coordinator")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "This lesson is not marked as containing Māori content"
    }
