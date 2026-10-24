"""API tests for the Lesson Service (US-006 AC1 to AC6).

These call the real endpoints with a test client, so they also check the
login rule, the HTTP answers the website relies on, and the download name
(UT-41). Only the User Service session check is replaced (see conftest.py).

Author: Sandhya Tiwari
Date: 23 Oct 2026
"""

import re
from urllib.parse import unquote

from conftest import LoggedIn
from fastapi.testclient import TestClient
from sample_files import exe_bytes, pdf_bytes

from files import FILE_RULE, KB, MB
from user_client import Staff

LESSON = {
    "title": "Catching the bus",
    "lesson_date": "2026-10-21",
    "tags": ["Transport"],
}


def create(client: TestClient, **changes) -> dict:
    response = client.post("/lessons", json={**LESSON, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def upload(
    client: TestClient,
    lesson_id: str,
    name: str,
    content: bytes,
    share: bool | None = None,
):
    data = {} if share is None else {"share_with_learners": str(share).lower()}
    return client.post(
        f"/lessons/{lesson_id}/materials",
        files={"file": (name, content, "application/octet-stream")},
        data=data,
    )


def download_name(content_disposition: str) -> str:
    """The file name a browser saves, from a Content-Disposition header."""
    encoded = re.search(r"filename\*=utf-8''([^;]+)", content_disposition)
    if encoded:
        return unquote(encoded.group(1))
    return re.search(r'filename="([^"]+)"', content_disposition).group(1)


def listed_ids(client: TestClient) -> list[str]:
    response = client.get("/lessons")
    assert response.status_code == 200
    return [lesson["id"] for lesson in response.json()]


# Login


def test_every_lesson_endpoint_needs_a_login(
    client: TestClient, logged_in: LoggedIn
) -> None:
    logged_in.staff = None

    assert client.get("/lessons").status_code == 401
    assert client.post("/lessons", json=LESSON).status_code == 401
    assert client.get("/tags").status_code == 401


def test_request_without_an_authorization_header_is_refused(client: TestClient) -> None:
    response = client.get("/lessons", headers={"Authorization": ""})

    assert response.status_code == 401


def test_author_comes_from_the_login_not_the_request(
    client: TestClient, teacher: Staff, other_teacher: Staff
) -> None:
    lesson = create(client, created_by=str(other_teacher.id))

    assert lesson["created_by"] == str(teacher.id)


# AC1


def test_ac1_saved_lesson_appears_in_the_list_with_date_and_tags(
    client: TestClient,
) -> None:
    saved = create(client, tags=["Health", "Shopping"])

    listed = [
        lesson
        for lesson in client.get("/lessons").json()
        if lesson["id"] == saved["id"]
    ]

    assert len(listed) == 1
    assert listed[0]["title"] == "Catching the bus"
    assert listed[0]["lesson_date"] == "2026-10-21"
    assert listed[0]["tags"] == ["Health", "Shopping"]
    assert listed[0]["can_change"] is True


def test_tags_endpoint_returns_the_agreed_list(client: TestClient) -> None:
    assert client.get("/tags").json() == [
        "Transport",
        "Health",
        "Shopping",
        "Culture",
        "History",
        "Accommodation",
        "Lifestyle",
    ]


def test_macron_title_comes_back_exactly_as_typed(client: TestClient) -> None:
    saved = create(client, title="Te reo Māori")

    assert client.get(f"/lessons/{saved['id']}").json()["title"] == "Te reo Māori"


# AC2


def test_ac2_empty_title_answers_title_is_required_and_saves_nothing(
    client: TestClient,
) -> None:
    before = listed_ids(client)

    response = client.post("/lessons", json={**LESSON, "title": "  "})

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "field": "title",
        "message": "Title is required",
    }
    assert listed_ids(client) == before


def test_missing_date_and_tag_have_their_own_messages(client: TestClient) -> None:
    no_date = client.post("/lessons", json={**LESSON, "lesson_date": None})
    no_tag = client.post("/lessons", json={**LESSON, "tags": []})

    assert no_date.json()["detail"] == {
        "field": "lesson_date",
        "message": "Lesson date is required",
    }
    assert no_tag.json()["detail"]["field"] == "tags"


# AC3 / UT-41


def test_ac3_pdf_up_to_10_mb_downloads_with_the_same_name_and_content(
    client: TestClient,
) -> None:
    saved = create(client)
    content = pdf_bytes(10 * MB)

    uploaded = upload(client, saved["id"], "Bus timetable.pdf", content)
    assert uploaded.status_code == 201, uploaded.text
    download = client.get(f"/materials/{uploaded.json()['id']}/download")

    assert download.status_code == 200
    assert download.content == content
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("attachment")
    assert download_name(download.headers["content-disposition"]) == "Bus timetable.pdf"


def test_file_name_with_a_macron_downloads_unchanged(client: TestClient) -> None:
    saved = create(client)

    uploaded = upload(client, saved["id"], "Māori kai.pdf", pdf_bytes(2 * KB))
    download = client.get(f"/materials/{uploaded.json()['id']}/download")

    assert uploaded.json()["file_name"] == "Māori kai.pdf"
    assert download_name(download.headers["content-disposition"]) == "Māori kai.pdf"


def test_uploaded_file_is_listed_on_the_lesson(client: TestClient) -> None:
    saved = create(client)
    upload(client, saved["id"], "worksheet.pdf", pdf_bytes(2 * KB))

    materials = client.get(f"/lessons/{saved['id']}").json()["materials"]

    assert [m["file_name"] for m in materials] == ["worksheet.pdf"]


def test_download_needs_a_login(client: TestClient, logged_in: LoggedIn) -> None:
    saved = create(client)
    material_id = upload(
        client, saved["id"], "worksheet.pdf", pdf_bytes(2 * KB)
    ).json()["id"]

    logged_in.staff = None

    assert client.get(f"/materials/{material_id}/download").status_code == 401


# Share with learners (stored for US-013)


def test_share_with_learners_is_off_unless_ticked(client: TestClient) -> None:
    saved = create(client)

    default = upload(client, saved["id"], "a.pdf", pdf_bytes(2 * KB)).json()
    ticked = upload(client, saved["id"], "b.pdf", pdf_bytes(2 * KB), share=True).json()

    assert default["share_with_learners"] is False
    assert ticked["share_with_learners"] is True


def test_share_with_learners_can_be_changed_later(client: TestClient) -> None:
    saved = create(client)
    material_id = upload(client, saved["id"], "a.pdf", pdf_bytes(2 * KB)).json()["id"]

    response = client.patch(
        f"/materials/{material_id}", json={"share_with_learners": True}
    )

    assert response.json()["share_with_learners"] is True


# AC4 / UT-40


def test_ac4_file_over_10_mb_is_refused_with_the_rule_and_lesson_is_kept(
    client: TestClient,
) -> None:
    saved = create(client)

    response = upload(client, saved["id"], "big.pdf", pdf_bytes(int(10.1 * MB)))

    assert response.status_code == 422
    assert response.json()["detail"] == {"field": "file", "message": FILE_RULE}
    lesson = client.get(f"/lessons/{saved['id']}").json()
    assert (lesson["title"], lesson["lesson_date"], lesson["tags"]) == (
        "Catching the bus",
        "2026-10-21",
        ["Transport"],
    )
    assert lesson["materials"] == []


def test_ac4_wrong_type_and_renamed_program_are_refused(client: TestClient) -> None:
    saved = create(client)

    exe = upload(client, saved["id"], "setup.exe", exe_bytes())
    renamed = upload(client, saved["id"], "setup.pdf", exe_bytes())
    small = upload(client, saved["id"], "tiny.pdf", pdf_bytes(900))

    for response in (exe, renamed, small):
        assert response.status_code == 422
        assert response.json()["detail"]["message"] == FILE_RULE
    assert client.get(f"/lessons/{saved['id']}").json()["materials"] == []


# AC5


def test_ac5_new_title_is_listed_and_date_and_files_are_unchanged(
    client: TestClient,
) -> None:
    saved = create(client)
    material = upload(client, saved["id"], "worksheet.pdf", pdf_bytes(2 * KB)).json()

    response = client.put(
        f"/lessons/{saved['id']}", json={**LESSON, "title": "Catching the train"}
    )

    assert response.status_code == 200
    listed = {lesson["id"]: lesson for lesson in client.get("/lessons").json()}
    assert listed[saved["id"]]["title"] == "Catching the train"
    lesson = client.get(f"/lessons/{saved['id']}").json()
    assert lesson["lesson_date"] == "2026-10-21"
    assert [m["id"] for m in lesson["materials"]] == [material["id"]]


# AC6 / UT-43


def test_ac6_deleted_lesson_leaves_the_list_and_files_cannot_be_downloaded(
    client: TestClient,
) -> None:
    saved = create(client)
    material_id = upload(
        client, saved["id"], "worksheet.pdf", pdf_bytes(2 * KB)
    ).json()["id"]

    response = client.delete(f"/lessons/{saved['id']}")

    assert response.status_code == 204
    assert saved["id"] not in listed_ids(client)
    assert client.get(f"/lessons/{saved['id']}").status_code == 404
    assert client.get(f"/materials/{material_id}/download").status_code == 404


# UT-42: author or coordinator only, also when the address is typed directly


def test_another_teacher_gets_you_do_not_have_permission(
    client: TestClient, logged_in: LoggedIn, other_teacher: Staff
) -> None:
    saved = create(client)
    material_id = upload(
        client, saved["id"], "worksheet.pdf", pdf_bytes(2 * KB)
    ).json()["id"]

    logged_in.staff = other_teacher

    lesson = client.get(f"/lessons/{saved['id']}").json()
    assert lesson["can_change"] is False
    for response in (
        client.put(f"/lessons/{saved['id']}", json={**LESSON, "title": "Not mine"}),
        client.delete(f"/lessons/{saved['id']}"),
        upload(client, saved["id"], "extra.pdf", pdf_bytes(2 * KB)),
        client.patch(f"/materials/{material_id}", json={"share_with_learners": True}),
        client.delete(f"/materials/{material_id}"),
    ):
        assert response.status_code == 403
        assert response.json()["detail"] == "You do not have permission"
    # Viewing and downloading are still allowed, because lessons are shared.
    assert client.get(f"/materials/{material_id}/download").status_code == 200
    assert client.get(f"/lessons/{saved['id']}").json()["title"] == "Catching the bus"


def test_coordinator_can_edit_and_delete_another_teachers_lesson(
    client: TestClient, logged_in: LoggedIn, coordinator: Staff
) -> None:
    saved = create(client)

    logged_in.staff = coordinator

    assert client.get(f"/lessons/{saved['id']}").json()["can_change"] is True
    edited = client.put(f"/lessons/{saved['id']}", json={**LESSON, "title": "Checked"})
    assert edited.status_code == 200
    assert client.delete(f"/lessons/{saved['id']}").status_code == 204
