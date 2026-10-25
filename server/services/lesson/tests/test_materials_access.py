"""API tests for teacher access to lesson materials (the story after US-006).

AC1: a signed-in teacher sees the shared lessons and their files.
AC2: a teacher can open or download every file type.
AC3: a visitor who is not signed in is refused, and no titles or file names
are given away, whatever address they try.

Author: Sandhya Tiwari
Date: 24 Oct 2026
"""

from uuid import uuid4

import pytest
from conftest import LoggedIn
from fastapi.testclient import TestClient
from sample_files import docx_bytes, jpg_bytes, pdf_bytes, png_bytes

import user_client
from files import DOCX_MIME, KB
from user_client import Staff

TITLE = "Secret bus lesson"
FILE_NAME = "Confidential timetable.pdf"


def create_with_file(client: TestClient) -> tuple[dict, dict]:
    lesson = client.post(
        "/lessons",
        json={"title": TITLE, "lesson_date": "2026-10-21", "tags": ["Transport"]},
    ).json()
    material = client.post(
        f"/lessons/{lesson['id']}/materials",
        files={"file": (FILE_NAME, pdf_bytes(4 * KB), "application/pdf")},
    ).json()
    return lesson, material


def protected_requests(lesson_id: str, material_id: str) -> list[tuple[str, str]]:
    return [
        ("GET", "/tags"),
        ("GET", "/lessons"),
        ("GET", f"/lessons/{lesson_id}"),
        ("PUT", f"/lessons/{lesson_id}"),
        ("DELETE", f"/lessons/{lesson_id}"),
        ("POST", f"/lessons/{lesson_id}/materials"),
        ("PATCH", f"/materials/{material_id}"),
        ("DELETE", f"/materials/{material_id}"),
        ("GET", f"/materials/{material_id}/download"),
    ]


# AC1


def test_ac1_teacher_sees_shared_lessons_with_their_file_count(
    client: TestClient, logged_in: LoggedIn, other_teacher: Staff
) -> None:
    lesson, _ = create_with_file(client)

    logged_in.staff = other_teacher
    listed = {item["id"]: item for item in client.get("/lessons").json()}

    assert listed[lesson["id"]]["title"] == TITLE
    assert listed[lesson["id"]]["material_count"] == 1
    assert listed[lesson["id"]]["can_change"] is False


def test_hidden_files_are_not_counted_or_listed(client: TestClient) -> None:
    lesson, material = create_with_file(client)
    client.delete(f"/materials/{material['id']}")

    listed = {item["id"]: item for item in client.get("/lessons").json()}
    detail = client.get(f"/lessons/{lesson['id']}").json()

    assert listed[lesson["id"]]["material_count"] == 0
    assert detail["materials"] == []


def test_lesson_shows_its_maori_content_review_status(client: TestClient) -> None:
    lesson, _ = create_with_file(client)

    detail = client.get(f"/lessons/{lesson['id']}").json()

    # US-008 adds the tick; until then a lesson has no Māori content flag.
    assert detail["has_maori_content"] is False
    assert detail["review_status"] == "not_required"


# AC2


@pytest.mark.parametrize(
    ("name", "content", "mime_type"),
    [
        ("worksheet.pdf", pdf_bytes(4 * KB), "application/pdf"),
        ("worksheet.docx", docx_bytes(), DOCX_MIME),
        ("bus stop.jpg", jpg_bytes(), "image/jpeg"),
        ("map.png", png_bytes(), "image/png"),
    ],
)
def test_ac2_another_teacher_can_open_or_download_each_file_type(
    client: TestClient,
    logged_in: LoggedIn,
    other_teacher: Staff,
    name: str,
    content: bytes,
    mime_type: str,
) -> None:
    lesson, _ = create_with_file(client)
    material = client.post(
        f"/lessons/{lesson['id']}/materials",
        files={"file": (name, content, "application/octet-stream")},
    ).json()

    logged_in.staff = other_teacher
    response = client.get(f"/materials/{material['id']}/download")

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"].startswith(mime_type)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in response.headers["cache-control"]


def test_missing_file_answers_file_not_found(client: TestClient) -> None:
    response = client.get(f"/materials/{uuid4()}/download")

    assert response.status_code == 404
    assert response.json() == {"detail": "File not found"}


# AC3


def test_ac3_visitor_without_a_session_is_refused_everywhere_and_sees_no_names(
    client: TestClient, logged_in: LoggedIn
) -> None:
    lesson, material = create_with_file(client)

    logged_in.staff = None
    for method, path in protected_requests(lesson["id"], material["id"]):
        response = client.request(method, path, headers={"Authorization": ""})

        assert response.status_code == 401, (method, path)
        assert response.json() == {"detail": "Login required"}
        assert TITLE not in response.text
        assert FILE_NAME not in response.text


def test_ac3_ended_or_unknown_session_is_refused_the_same_way(
    client: TestClient, logged_in: LoggedIn
) -> None:
    lesson, material = create_with_file(client)

    # The User Service answers 401 for an expired or logged-out session.
    logged_in.staff = None
    for method, path in protected_requests(lesson["id"], material["id"]):
        response = client.request(method, path)

        assert response.status_code == 401, (method, path)
        assert FILE_NAME not in response.text


def test_ac3_visitor_cannot_tell_whether_a_lesson_or_file_exists(
    client: TestClient, logged_in: LoggedIn
) -> None:
    lesson, material = create_with_file(client)

    logged_in.staff = None
    real = client.get(f"/materials/{material['id']}/download")
    made_up = client.get(f"/materials/{uuid4()}/download")
    real_lesson = client.get(f"/lessons/{lesson['id']}")
    made_up_lesson = client.get(f"/lessons/{uuid4()}")

    assert real.status_code == made_up.status_code == 401
    assert real.json() == made_up.json()
    assert real_lesson.status_code == made_up_lesson.status_code == 401


def test_user_service_down_refuses_without_names(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    lesson, material = create_with_file(client)

    def unavailable(authorization: str) -> Staff:
        raise user_client.UserServiceError("User service unavailable")

    monkeypatch.setattr(user_client, "current_staff", unavailable)
    response = client.get(f"/materials/{material['id']}/download")

    assert response.status_code == 503
    assert FILE_NAME not in response.text
    assert TITLE not in response.text
