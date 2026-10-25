"""System tests for the Māori content review flow (US-008).

Test Plan ST-09 and the review part of NT-10, run end to end through the web
app's lesson proxy: cookie login, Origin check, Lesson Service, User Service
and database. A real teacher account (US-002) and the demo coordinator take
part.

These API checks exercise the authenticated US-006 endpoints and verify
that uploaded materials reset the Māori review through the real gateway.

Author: Sandhya Tiwari
Date: 25 Oct 2026
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from api import BASE_URL
from playwright.sync_api import APIRequestContext, APIResponse, Browser

COORDINATOR_LOGIN = ("demo", "DemoPass123!")
NOT_YET_REVIEWED = "Māori content – not yet reviewed"


@dataclass
class Person:
    """Someone logged in, calling the API from their own browser session."""

    request: APIRequestContext
    user_id: str

    def call(self, method: str, path: str, body: Any = None) -> APIResponse:
        # A browser sends Origin on every change; the proxy refuses it otherwise.
        return self.request.fetch(
            path, method=method, data=body, headers={"Origin": BASE_URL}
        )

    def review(self, lesson_id: str) -> APIResponse:
        return self.call("GET", f"/api/staff/lesson/lessons/{lesson_id}/review")

    def tick(self, lesson_id: str, value: bool = True) -> APIResponse:
        return self.call(
            "PUT",
            f"/api/staff/lesson/lessons/{lesson_id}/maori-content",
            {"has_maori_content": value},
        )

    def record_review(self, lesson_id: str, name: str, day: str) -> APIResponse:
        return self.call(
            "POST",
            f"/api/staff/lesson/lessons/{lesson_id}/review",
            {"reviewer_name": name, "review_date": day},
        )


@pytest.fixture
def log_in(browser: Browser) -> Iterator[Callable[[str, str], Person]]:
    contexts = []

    def login(username: str, password: str) -> Person:
        context = browser.new_context(base_url=BASE_URL)
        contexts.append(context)
        response = context.request.post(
            "/api/user/login",
            data={"username": username, "password": password},
            headers={"Origin": BASE_URL},
        )
        assert response.ok, f"Login failed with status {response.status}"
        session = context.request.get("/api/user/session").json()
        return Person(context.request, session["user_id"])

    yield login
    for context in contexts:
        context.close()


@pytest.fixture
def coordinator(log_in: Callable[[str, str], Person]) -> Person:
    return log_in(*COORDINATOR_LOGIN)


@pytest.fixture
def new_teacher(
    coordinator: Person, log_in: Callable[[str, str], Person]
) -> Callable[[], Person]:
    """Create a teacher account through US-002 and log them in."""

    def create() -> Person:
        username = f"teacher_{uuid4().hex[:10]}"
        password = f"Temp-{uuid4().hex[:8]}"
        response = coordinator.call(
            "POST",
            "/api/user/staff",
            {
                "display_name": "Review Test Teacher",
                "username": username,
                "temporary_password": password,
            },
        )
        assert response.status == 201, response.status
        return log_in(username, password)

    return create


@pytest.fixture
def teacher(new_teacher: Callable[[], Person]) -> Person:
    return new_teacher()


@pytest.fixture
def new_lesson(coordinator: Person) -> Callable[[Person], str]:
    """Create a lesson written by the given person and return its id.

    Creates through the authenticated US-006 API as the lesson author.
    """

    def create(author: Person) -> str:
        response = author.call(
            "POST",
            "/api/staff/lesson/lessons",
            {
                "title": "Te reo Māori greetings",
                "lesson_date": "2026-10-25",
                "tags": ["greetings"],
            },
        )
        assert response.status == 201, response.status
        return response.json()["id"]

    return create


# ST-09 Lesson with Māori content


def test_st09_teacher_flags_and_coordinator_reviews(
    teacher: Person, coordinator: Person, new_lesson: Callable[[Person], str]
) -> None:
    lesson_id = new_lesson(teacher)
    assert teacher.review(lesson_id).json()["label"] is None

    ticked = teacher.tick(lesson_id)
    assert ticked.status == 200
    assert ticked.json()["label"] == NOT_YET_REVIEWED
    assert ticked.json()["visible_to_learners"] is False
    assert coordinator.review(lesson_id).json()["label"] == NOT_YET_REVIEWED

    reviewed = coordinator.record_review(lesson_id, "Aroha", "2026-10-08")
    assert reviewed.status == 200
    assert reviewed.json()["label"] == "Reviewed by Aroha, 8 Oct 2026"
    assert reviewed.json()["visible_to_learners"] is True
    # The teacher sees the same label.
    assert teacher.review(lesson_id).json()["label"] == "Reviewed by Aroha, 8 Oct 2026"


def test_st09_adding_a_file_returns_the_label_to_not_yet_reviewed(
    teacher: Person, coordinator: Person, new_lesson: Callable[[Person], str]
) -> None:
    lesson_id = new_lesson(teacher)
    assert teacher.tick(lesson_id).status == 200
    assert coordinator.record_review(lesson_id, "Aroha", "2026-10-08").status == 200
    response = teacher.request.post(
        f"/api/staff/lesson/lessons/{lesson_id}/materials",
        headers={"Origin": BASE_URL},
        multipart={
            "file": {
                "name": "handout.pdf",
                "mimeType": "application/pdf",
                "buffer": b"%PDF-1.7 test",
            }
        },
    )
    assert response.status == 201
    assert teacher.review(lesson_id).json()["label"] == NOT_YET_REVIEWED


# US-008 AC3 and Test Plan UT-46, through the whole system


def test_bad_review_is_refused_with_every_message_and_label_unchanged(
    teacher: Person, coordinator: Person, new_lesson: Callable[[Person], str]
) -> None:
    lesson_id = new_lesson(teacher)
    teacher.tick(lesson_id)

    response = coordinator.record_review(lesson_id, "", "2099-01-01")

    assert response.status == 422
    assert response.json()["detail"]["errors"] == {
        "reviewer_name": "Reviewer name is required",
        "review_date": "Review date cannot be in the future",
    }
    assert teacher.review(lesson_id).json()["label"] == NOT_YET_REVIEWED


def test_teacher_cannot_record_a_review(
    teacher: Person, new_lesson: Callable[[Person], str]
) -> None:
    lesson_id = new_lesson(teacher)
    teacher.tick(lesson_id)

    response = teacher.record_review(lesson_id, "Aroha", "2026-10-08")

    assert response.status == 403
    assert response.json() == {"detail": "You do not have permission"}
    assert teacher.review(lesson_id).json()["label"] == NOT_YET_REVIEWED


def test_teacher_cannot_flag_another_teachers_lesson(
    teacher: Person,
    new_teacher: Callable[[], Person],
    new_lesson: Callable[[Person], str],
) -> None:
    lesson_id = new_lesson(teacher)
    other = new_teacher()

    response = other.tick(lesson_id)

    assert response.status == 403
    assert teacher.review(lesson_id).json()["has_maori_content"] is False


def test_unticking_removes_the_label_and_the_review(
    teacher: Person, coordinator: Person, new_lesson: Callable[[Person], str]
) -> None:
    lesson_id = new_lesson(teacher)
    teacher.tick(lesson_id)
    coordinator.record_review(lesson_id, "Aroha", "2026-10-08")

    response = teacher.tick(lesson_id, False)

    assert response.json()["label"] is None
    assert response.json()["reviewer_name"] is None


# Security of the new paths


def test_change_without_origin_is_refused(
    teacher: Person, new_lesson: Callable[[Person], str]
) -> None:
    lesson_id = new_lesson(teacher)

    response = teacher.request.put(
        f"/api/staff/lesson/lessons/{lesson_id}/maori-content",
        data={"has_maori_content": True},
    )

    assert response.status == 403
    assert teacher.review(lesson_id).json()["has_maori_content"] is False


def test_logged_out_person_cannot_read_or_change_reviews(
    browser: Browser, teacher: Person, new_lesson: Callable[[Person], str]
) -> None:
    lesson_id = new_lesson(teacher)
    context = browser.new_context(base_url=BASE_URL)
    try:
        path = f"/api/staff/lesson/lessons/{lesson_id}"
        read = context.request.get(f"{path}/review")
        change = context.request.put(
            f"{path}/maori-content",
            data={"has_maori_content": True},
            headers={"Origin": BASE_URL},
        )
    finally:
        context.close()

    assert read.status == 401
    assert change.status == 401


# NT-10 Correct te reo


def test_nt10_reviewer_name_with_macrons_is_kept_exactly(
    teacher: Person, coordinator: Person, new_lesson: Callable[[Person], str]
) -> None:
    lesson_id = new_lesson(teacher)
    teacher.tick(lesson_id)

    coordinator.record_review(lesson_id, "Kiri Tāmaki-Ōtene", "2026-10-08")

    shown = teacher.review(lesson_id).json()
    assert shown["reviewer_name"] == "Kiri Tāmaki-Ōtene"
    assert shown["label"] == "Reviewed by Kiri Tāmaki-Ōtene, 8 Oct 2026"
