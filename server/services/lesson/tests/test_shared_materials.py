"""Verify US-013 file sharing, Māori review protection and safe downloads.

Author: Sandhya Tiwari
Date: 26 Oct 2026
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import Base, lesson_materials, lessons
from shared_materials import create_shared_router
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def shared_api(tmp_path, monkeypatch):
    """
    Provide lesson API fixture configured for shared-material endpoints.
    """
    monkeypatch.setenv("INTERNAL_API_KEY", "test-key")
    engine = create_engine(f"sqlite:///{tmp_path / 'lesson.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    folder = tmp_path / "files"
    folder.mkdir()
    lid, mid, private = uuid4(), uuid4(), uuid4()
    with factory.begin() as db:
        db.execute(
            lessons.insert().values(
                id=lid,
                title="Te reo Māori",
                lesson_date=date(2020, 1, 1),
                created_by=uuid4(),
            )
        )
        for item, shared, name in [
            (mid, True, "Te reo Māori.pdf"),
            (private, False, "private.pdf"),
        ]:
            (folder / item.hex).write_bytes(b"%PDF-content")
            db.execute(
                lesson_materials.insert().values(
                    id=item,
                    lesson_id=lid,
                    file_name=name,
                    storage_key=item.hex,
                    mime_type="application/pdf",
                    file_size=12,
                    uploaded_by=uuid4(),
                    share_with_learners=shared,
                )
            )
    app = FastAPI()
    app.include_router(create_shared_router(factory, folder))
    with TestClient(app, headers={"X-Internal-Key": "test-key"}) as client:
        yield client, factory, folder, lid, mid, private
    engine.dispose()


def test_only_shared_files_listed_with_no_storage_keys(shared_api):
    """
    Verify that only shared files listed with no storage keys.
    """
    client, _, _, lid, mid, _ = shared_api
    reply = client.get(f"/internal/lessons/{lid}/shared-materials")
    assert reply.status_code == 200
    assert reply.json() == {
        "materials": [
            {"id": str(mid), "file_name": "Te reo Māori.pdf", "file_size": 12}
        ],
        "message": "",
    }


@pytest.mark.parametrize("key", ["", "wrong"])
def test_internal_api_is_not_public(shared_api, key):
    """
    Verify that internal api is not public.
    """
    client, _, _, lid, mid, _ = shared_api
    for path in [
        f"/internal/lessons/{lid}/shared-materials",
        f"/internal/lessons/{lid}/shared-materials/{mid}",
    ]:
        assert client.get(path, headers={"X-Internal-Key": key}).status_code == 403


def test_missing_server_key_fails_closed(shared_api, monkeypatch):
    """
    Verify that missing server key fails closed.
    """
    client, _, _, lid, _, _ = shared_api
    monkeypatch.delenv("INTERNAL_API_KEY")
    assert client.get(f"/internal/lessons/{lid}/shared-materials").status_code == 403


@pytest.mark.parametrize(
    "review,visible", [("pending", False), ("rejected", False), ("reviewed", True)]
)
def test_maori_review_applies_to_listing_and_direct_download(
    shared_api, review, visible
):
    """
    Verify that maori review applies to listing and direct download.
    """
    client, factory, _, lid, mid, _ = shared_api
    with factory.begin() as db:
        db.execute(
            lessons.update()
            .where(lessons.c.id == lid)
            .values(has_maori_content=True, review_status=review)
        )
    listing = client.get(f"/internal/lessons/{lid}/shared-materials").json()
    assert bool(listing["materials"]) is visible
    assert listing["message"] == ("" if visible else "Materials will be added soon")
    assert client.get(
        f"/internal/lessons/{lid}/shared-materials/{mid}"
    ).status_code == (200 if visible else 404)


def test_original_name_content_and_headers(shared_api):
    """
    Verify that original name content and headers.
    """
    client, _, _, lid, mid, _ = shared_api
    reply = client.get(f"/internal/lessons/{lid}/shared-materials/{mid}")
    assert reply.content == b"%PDF-content"
    assert "Te%20reo%20M%C4%81ori.pdf" in reply.headers["content-disposition"]
    assert reply.headers["cache-control"] == "no-store"
    assert reply.headers["x-content-type-options"] == "nosniff"


def test_private_unknown_and_wrong_lesson_downloads_denied(shared_api):
    """
    Verify that private unknown and wrong lesson downloads denied.
    """
    client, _, _, lid, mid, private = shared_api
    for lesson, file in [(lid, private), (lid, uuid4()), (uuid4(), mid)]:
        assert (
            client.get(
                f"/internal/lessons/{lesson}/shared-materials/{file}"
            ).status_code
            == 404
        )


@pytest.mark.parametrize("target", ["file", "lesson"])
def test_deleted_materials_and_lessons_block_old_links(shared_api, target):
    """
    Verify that deleted materials and lessons block old links.
    """
    client, factory, _, lid, mid, _ = shared_api
    with factory.begin() as db:
        table = lesson_materials if target == "file" else lessons
        db.execute(
            table.update()
            .where(table.c.id == (mid if target == "file" else lid))
            .values(deleted_at=datetime.now(UTC))
        )
    assert (
        client.get(f"/internal/lessons/{lid}/shared-materials/{mid}").status_code == 404
    )
    reply = client.get(f"/internal/lessons/{lid}/shared-materials")
    assert (
        reply.status_code == 404
        if target == "lesson"
        else reply.json()["materials"] == []
    )


def test_unshare_revokes_existing_link(shared_api):
    """
    Verify that unshare revokes existing link.
    """
    client, factory, _, lid, mid, _ = shared_api
    with factory.begin() as db:
        db.execute(
            lesson_materials.update()
            .where(lesson_materials.c.id == mid)
            .values(share_with_learners=False)
        )
    assert (
        client.get(f"/internal/lessons/{lid}/shared-materials").json()["message"]
        == "No materials for today"
    )
    assert (
        client.get(f"/internal/lessons/{lid}/shared-materials/{mid}").status_code == 404
    )


@pytest.mark.parametrize("storage", ["../outside", "missing"])
def test_storage_path_and_missing_file_safe(shared_api, storage):
    """
    Verify that storage path and missing file safe.
    """
    client, factory, folder, lid, mid, _ = shared_api
    (folder.parent / "outside").write_bytes(b"secret")
    with factory.begin() as db:
        db.execute(
            lesson_materials.update()
            .where(lesson_materials.c.id == mid)
            .values(storage_key=storage)
        )
    assert (
        client.get(f"/internal/lessons/{lid}/shared-materials/{mid}").status_code == 404
    )


def test_two_shared_files_each_download_with_their_original_name(shared_api):
    """
    Verify that two shared files each download with their original name.
    """
    client, factory, folder, lid, mid, _ = shared_api
    second = uuid4()
    (folder / second.hex).write_bytes(b"image-content")
    with factory.begin() as db:
        db.execute(
            lesson_materials.insert().values(
                id=second,
                lesson_id=lid,
                file_name="Picture.png",
                storage_key=second.hex,
                mime_type="image/png",
                file_size=13,
                uploaded_by=uuid4(),
                share_with_learners=True,
            )
        )
    listing = client.get(f"/internal/lessons/{lid}/shared-materials").json()
    assert len(listing["materials"]) == 2
    for identifier, name in [
        (mid, "Te%20reo%20M%C4%81ori.pdf"),
        (second, "Picture.png"),
    ]:
        response = client.get(f"/internal/lessons/{lid}/shared-materials/{identifier}")
        assert response.status_code == 200
        assert name in response.headers["content-disposition"]
