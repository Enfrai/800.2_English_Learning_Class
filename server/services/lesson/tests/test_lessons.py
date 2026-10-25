"""Verify US-006 lesson, permission, attachment and migration contracts.

Author: Sandhya Tiwari
Date: 25 Oct 2026
"""

import io
import zipfile
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import user_client
from fastapi import FastAPI
from fastapi.testclient import TestClient
from lesson_api import MAX_FILE_SIZE, create_lesson_router
from maori_review_api import create_maori_review_router
from models import Base, lesson_materials, lessons
from schema import prepare_schema
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

AUTHOR = user_client.Staff(uuid4(), "Teacher", "teacher")
OTHER = user_client.Staff(uuid4(), "Another teacher", "teacher")
COORDINATOR = user_client.Staff(uuid4(), "Coordinator", "coordinator")
PDF = b"%PDF-1.7\nTest lesson\n%%EOF"


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'lessons.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    storage = tmp_path / "materials"

    def current(token):
        if token == "Bearer unavailable":
            raise user_client.UserServiceError()
        people = {
            "Bearer author": AUTHOR,
            "Bearer other": OTHER,
            "Bearer coordinator": COORDINATOR,
        }
        if token not in people:
            raise user_client.LoginRequiredError()
        return people[token]

    monkeypatch.setattr(user_client, "current_staff", current)
    app = FastAPI()
    app.include_router(create_lesson_router(factory, storage))
    app.include_router(create_maori_review_router(factory))
    with TestClient(app) as client:
        yield client, factory, storage
    engine.dispose()


def headers(who="author"):
    return {"Authorization": f"Bearer {who}"}


def payload(**changes):
    return {
        "title": "Te reo Māori transport",
        "lesson_date": "2026-10-25",
        "tags": ["transport", "health"],
        "description": "Paper handout",
        **changes,
    }


def create(api, who="author", **changes):
    response = api[0].post("/lessons", json=payload(**changes), headers=headers(who))
    assert response.status_code == 201, response.text
    return response.json()


def upload(
    api, lesson_id, name="Te reo Māori.pdf", content=PDF, who="author", share=None
):
    return api[0].post(
        f"/lessons/{lesson_id}/materials",
        headers=headers(who),
        files={"file": (name, content, "application/octet-stream")},
        data={} if share is None else {"share_with_learners": str(share).lower()},
    )


def test_create_list_detail_tags_and_macrons(api):
    row = create(api)
    assert row["created_by"] == str(AUTHOR.id)
    assert row["tags"] == ["health", "transport"]
    assert row["materials"] == [] and row["can_edit"]
    listed = api[0].get("/lessons", headers=headers("other")).json()
    assert listed[0]["title"] == "Te reo Māori transport"
    assert listed[0]["can_edit"] is False
    assert api[0].get(f"/lessons/{row['id']}", headers=headers()).json() == row
    assert [tag["name"] for tag in api[0].get("/tags", headers=headers()).json()] == [
        "health",
        "transport",
    ]


@pytest.mark.parametrize(
    "changes,field,message",
    [
        ({"title": ""}, "title", "Title is required"),
        ({"title": "   "}, "title", "Title is required"),
        ({"title": "x" * 256}, "title", "Title must be 255 characters or fewer"),
        ({"lesson_date": None}, "lesson_date", "Lesson date is required"),
        ({"tags": []}, "tags", "At least one topic tag is required"),
        ({"tags": [" "]}, "tags", "At least one topic tag is required"),
        (
            {"tags": ["x" * 101]},
            "tags",
            "Each topic tag must be 100 characters or fewer",
        ),
    ],
)
def test_required_fields_do_not_create_partial_lesson(api, changes, field, message):
    response = api[0].post("/lessons", json=payload(**changes), headers=headers())
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][field] == message
    assert api[0].get("/lessons", headers=headers()).json() == []


def test_trim_deduplicate_tags_and_title_boundary(api):
    row = create(
        api, title=" " + "x" * 255 + " ", tags=[" health ", "health", "Tāmaki"]
    )
    assert len(row["title"]) == 255
    assert row["tags"] == ["Tāmaki", "health"]
    create(api, tags=["health"])
    assert len(api[0].get("/tags", headers=headers()).json()) == 2


@pytest.mark.parametrize("who,code", [("expired", 401), ("unavailable", 503)])
def test_auth_failures_are_not_treated_as_staff(api, who, code):
    assert api[0].get("/lessons", headers=headers(who)).status_code == code
    assert (
        api[0].post("/lessons", json=payload(), headers=headers(who)).status_code
        == code
    )


def test_missing_auth_and_forged_author_are_rejected(api):
    assert api[0].get("/lessons").status_code == 401
    response = api[0].post(
        "/lessons", json=payload(created_by=str(OTHER.id)), headers=headers()
    )
    assert response.status_code == 422


def test_title_edit_preserves_date_and_materials(api):
    row = create(api)
    material = upload(api, row["id"]).json()
    response = api[0].put(
        f"/lessons/{row['id']}", json=payload(title="New title"), headers=headers()
    )
    assert response.status_code == 200
    saved = response.json()
    assert saved["title"] == "New title" and saved["lesson_date"] == row["lesson_date"]
    assert saved["materials"][0]["id"] == material["id"]
    assert api[0].get("/lessons", headers=headers()).json()[0]["title"] == "New title"


def test_invalid_update_preserves_previous_data(api):
    row = create(api)
    assert (
        api[0]
        .put(f"/lessons/{row['id']}", json=payload(title=""), headers=headers())
        .status_code
        == 422
    )
    assert (
        api[0].get(f"/lessons/{row['id']}", headers=headers()).json()["title"]
        == row["title"]
    )


@pytest.mark.parametrize("operation", ["edit", "delete", "upload", "remove", "share"])
def test_other_teacher_cannot_modify_lesson_or_files(api, operation):
    row = create(api)
    material = upload(api, row["id"]).json()
    client = api[0]
    if operation == "edit":
        response = client.put(
            f"/lessons/{row['id']}",
            json=payload(title="Forged"),
            headers=headers("other"),
        )
    elif operation == "delete":
        response = client.delete(f"/lessons/{row['id']}", headers=headers("other"))
    elif operation == "upload":
        response = upload(api, row["id"], who="other")
    elif operation == "remove":
        response = client.delete(
            f"/materials/{material['id']}", headers=headers("other")
        )
    else:
        response = client.patch(
            f"/materials/{material['id']}",
            json={"share_with_learners": True},
            headers=headers("other"),
        )
    assert response.status_code == 403
    assert (
        client.get(
            f"/materials/{material['id']}/download", headers=headers("other")
        ).content
        == PDF
    )


def test_coordinator_can_manage_another_teachers_lesson(api):
    row = create(api)
    assert (
        api[0]
        .put(
            f"/lessons/{row['id']}",
            json=payload(title="Coordinator edit"),
            headers=headers("coordinator"),
        )
        .status_code
        == 200
    )
    material = upload(api, row["id"], who="coordinator").json()
    assert (
        api[0]
        .delete(f"/materials/{material['id']}", headers=headers("coordinator"))
        .status_code
        == 204
    )
    assert (
        api[0]
        .delete(f"/lessons/{row['id']}", headers=headers("coordinator"))
        .status_code
        == 204
    )


def test_original_filename_download_and_default_sharing(api):
    row = create(api)
    response = upload(api, row["id"])
    assert response.status_code == 201
    material = response.json()
    assert not material["share_with_learners"] and "storage_key" not in material
    downloaded = api[0].get(f"/materials/{material['id']}/download", headers=headers())
    assert downloaded.content == PDF
    assert "Te%20reo%20M%C4%81ori.pdf" in downloaded.headers["content-disposition"]
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["cache-control"] == "no-store"
    assert api[0].get(f"/materials/{material['id']}/download").status_code == 401


def test_sharing_can_be_selected_at_upload_and_changed(api):
    row = create(api)
    material = upload(api, row["id"], share=True).json()
    assert material["share_with_learners"]
    changed = api[0].patch(
        f"/materials/{material['id']}",
        json={"share_with_learners": False},
        headers=headers(),
    )
    assert changed.status_code == 200 and not changed.json()["share_with_learners"]


def docx():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return output.getvalue()


@pytest.mark.parametrize(
    "name,content",
    [
        ("notes.PDF", PDF),
        ("notes.docx", docx()),
        ("image.JPG", b"\xff\xd8\xffdata"),
        ("image.jpeg", b"\xff\xd8\xffdata"),
        ("image.png", b"\x89PNG\r\n\x1a\ndata"),
    ],
)
def test_allowed_types_and_uppercase_extensions(api, name, content):
    row = create(api)
    assert upload(api, row["id"], name, content).status_code == 201


@pytest.mark.parametrize(
    "name,content",
    [
        ("bad.exe", PDF),
        ("bad.svg", b"<svg/>"),
        ("bad.pdf", b"<html/>"),
        ("bad.docx", b"not a zip"),
        ("bad.png", PDF),
        ("bad.jpg", PDF),
        ("empty.pdf", b""),
        ("x" * 256 + ".pdf", PDF),
        ("missing", PDF),
        ("bad.docx", b"PK"),
    ],
)
def test_invalid_files_leave_lesson_unchanged(api, name, content):
    row = create(api)
    assert upload(api, row["id"], name, content).status_code == 422
    saved = api[0].get(f"/lessons/{row['id']}", headers=headers()).json()
    assert saved["title"] == row["title"] and saved["materials"] == []
    assert not api[2].exists() or not list(api[2].iterdir())


def test_size_limit_is_inclusive_and_oversize_does_not_store_file(api):
    row = create(api)
    data = PDF + b" " * (MAX_FILE_SIZE - len(PDF))
    assert upload(api, row["id"], content=data).status_code == 201
    assert upload(api, row["id"], content=data + b" ").status_code == 413
    assert len(list(api[2].iterdir())) == 1


def test_same_names_use_distinct_storage_and_path_traversal_is_not_exposed(api):
    row = create(api)
    a = upload(api, row["id"], "../same.pdf").json()
    b = upload(api, row["id"], "same.pdf", PDF + b"other").json()
    assert a["file_name"] == b["file_name"] == "same.pdf"
    assert a["id"] != b["id"] and len(list(api[2].iterdir())) == 2
    assert (
        api[0].get(f"/materials/{a['id']}/download", headers=headers()).content == PDF
    )
    with api[1].begin() as db:
        db.execute(
            lesson_materials.update()
            .where(lesson_materials.c.id == UUID(a["id"]))
            .values(storage_key="../outside")
        )
    assert (
        api[0].get(f"/materials/{a['id']}/download", headers=headers()).status_code
        == 404
    )


def test_delete_blocks_old_download_links_and_excludes_lesson(api):
    row = create(api)
    material = upload(api, row["id"]).json()
    assert api[0].delete(f"/lessons/{row['id']}", headers=headers()).status_code == 204
    assert api[0].get("/lessons", headers=headers()).json() == []
    assert not list(api[2].iterdir())
    for path in [f"/lessons/{row['id']}", f"/materials/{material['id']}/download"]:
        assert api[0].get(path, headers=headers()).status_code == 404
    assert upload(api, row["id"]).status_code == 404
    assert (
        api[0]
        .patch(
            f"/materials/{material['id']}",
            json={"share_with_learners": True},
            headers=headers(),
        )
        .status_code
        == 404
    )


def test_remove_only_one_material(api):
    row = create(api)
    a, b = upload(api, row["id"]).json(), upload(api, row["id"], "second.pdf").json()
    assert api[0].delete(f"/materials/{a['id']}", headers=headers()).status_code == 204
    assert (
        api[0].get(f"/materials/{a['id']}/download", headers=headers()).status_code
        == 404
    )
    assert (
        api[0].get(f"/materials/{b['id']}/download", headers=headers()).status_code
        == 200
    )


@pytest.mark.parametrize("operation", ["upload", "remove"])
def test_material_changes_reset_maori_review_and_keep_audit_log(api, operation):
    row = create(api)
    material = upload(api, row["id"]).json()
    api[0].put(
        f"/lessons/{row['id']}/maori-content",
        json={"has_maori_content": True},
        headers=headers(),
    )
    reviewed = api[0].post(
        f"/lessons/{row['id']}/review",
        json={"reviewer_name": "Aroha", "review_date": str(date.today())},
        headers=headers("coordinator"),
    )
    assert reviewed.status_code == 200
    if operation == "upload":
        assert upload(api, row["id"]).status_code == 201
    else:
        assert (
            api[0].delete(f"/materials/{material['id']}", headers=headers()).status_code
            == 204
        )
    status = api[0].get(f"/lessons/{row['id']}/review", headers=headers()).json()
    assert status["review_status"] == "pending" and status["reviewer_name"] is None


def test_metadata_edit_and_sharing_do_not_reset_review(api):
    row = create(api)
    material = upload(api, row["id"]).json()
    api[0].put(
        f"/lessons/{row['id']}/maori-content",
        json={"has_maori_content": True},
        headers=headers(),
    )
    api[0].post(
        f"/lessons/{row['id']}/review",
        json={"reviewer_name": "Aroha", "review_date": str(date.today())},
        headers=headers("coordinator"),
    )
    api[0].put(
        f"/lessons/{row['id']}", json=payload(title="Updated"), headers=headers()
    )
    api[0].patch(
        f"/materials/{material['id']}",
        json={"share_with_learners": True},
        headers=headers(),
    )
    assert (
        api[0]
        .get(f"/lessons/{row['id']}/review", headers=headers())
        .json()["review_status"]
        == "reviewed"
    )


def test_failed_database_write_removes_orphan_file(api, monkeypatch):
    row = create(api)
    import lesson_api

    def fail(*args):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(lesson_api, "reset_review_after_material_change", fail)
    with pytest.raises(RuntimeError):
        upload(api, row["id"])
    assert not list(api[2].iterdir())
    assert (
        api[0].get(f"/lessons/{row['id']}", headers=headers()).json()["materials"] == []
    )


def test_missing_storage_file_returns_not_found(api):
    row = create(api)
    material = upload(api, row["id"]).json()
    next(api[2].iterdir()).unlink()
    assert (
        api[0]
        .get(f"/materials/{material['id']}/download", headers=headers())
        .status_code
        == 404
    )


def test_schema_upgrade_preserves_existing_records_and_is_repeatable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.sqlite'}")
    Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(text("ALTER TABLE lesson_materials DROP COLUMN share_with_learners"))
        lesson_id = db.execute(
            lessons.insert()
            .values(title="Existing", lesson_date=date.today(), created_by=AUTHOR.id)
            .returning(lessons.c.id)
        ).scalar_one()
        db.execute(
            text(
                "INSERT INTO lesson_materials "
                "(id,lesson_id,file_name,storage_key,mime_type,file_size,uploaded_by) "
                "VALUES (:id,:lesson,:name,:key,:mime,1,:by)"
            ),
            {
                "id": uuid4().hex,
                "lesson": lesson_id.hex,
                "name": "old.pdf",
                "key": "old",
                "mime": "application/pdf",
                "by": AUTHOR.id.hex,
            },
        )
    prepare_schema(engine)
    prepare_schema(engine)
    assert "share_with_learners" in {
        column["name"] for column in inspect(engine).get_columns("lesson_materials")
    }
    with engine.connect() as db:
        assert db.scalar(select(lessons.c.title)) == "Existing"
        assert db.scalar(select(lesson_materials.c.share_with_learners)) is False
    engine.dispose()


def test_control_characters_in_original_filename_are_rejected():
    from fastapi import HTTPException, UploadFile
    from lesson_api import read_file

    with pytest.raises(HTTPException) as error:
        read_file(UploadFile(filename="invalid\r\n.pdf", file=io.BytesIO(PDF)))
    assert error.value.status_code == 422


def test_purge_failure_does_not_restore_a_deleted_download(api, monkeypatch):
    row = create(api)
    material = upload(api, row["id"]).json()
    original_unlink = Path.unlink

    def fail(path, *args, **kwargs):
        if path.parent == api[2]:
            raise PermissionError("Storage temporarily unavailable")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail)
    assert (
        api[0].delete(f"/materials/{material['id']}", headers=headers()).status_code
        == 204
    )
    assert (
        api[0]
        .get(f"/materials/{material['id']}/download", headers=headers())
        .status_code
        == 404
    )


def test_legacy_review_columns_are_added_without_database_reset(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-review.sqlite'}")
    Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(text("ALTER TABLE lessons DROP COLUMN reviewer_name"))
        db.execute(text("ALTER TABLE lessons DROP COLUMN review_date"))
    prepare_schema(engine)
    assert {"reviewer_name", "review_date"} <= {
        column["name"] for column in inspect(engine).get_columns("lessons")
    }
    engine.dispose()


def test_sorting_is_newest_lesson_date_first(api):
    create(api, lesson_date="2026-10-01", title="Older")
    create(api, lesson_date="2026-10-25", title="Newer")
    assert [
        row["title"] for row in api[0].get("/lessons", headers=headers()).json()
    ] == ["Newer", "Older"]


def test_unknown_resources_and_invalid_dates_are_rejected(api):
    unknown = str(uuid4())
    assert api[0].get(f"/lessons/{unknown}", headers=headers()).status_code == 404
    assert api[0].delete(f"/materials/{unknown}", headers=headers()).status_code == 404
    assert (
        api[0]
        .post("/lessons", json=payload(lesson_date="not-a-date"), headers=headers())
        .status_code
        == 422
    )
