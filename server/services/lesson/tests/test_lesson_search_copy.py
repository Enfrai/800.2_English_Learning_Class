"""Verify US-007 searches, unsaved drafts and independent lesson copies.

Author: Sandhya Tiwari
Date: 26 Oct 2026
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

import lesson_copy
import pytest
import user_client
from fastapi import FastAPI
from fastapi.testclient import TestClient
from lesson_api import MAX_FILE_SIZE, create_lesson_router
from lesson_copy import create_copy_router
from maori_review_api import create_maori_review_router
from models import Base, lesson_materials, lessons
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

AUTHOR = user_client.Staff(uuid4(), "Author", "teacher")
OTHER = user_client.Staff(uuid4(), "Another teacher", "teacher")
COORDINATOR = user_client.Staff(uuid4(), "Coordinator", "coordinator")
PDF = b"%PDF-1.7\nTest material\n%%EOF"


def auth(who: str = "author") -> dict[str, str]:
    """
    Prepare or exercise auth in the test lesson search copy test scenario.
    """
    return {"Authorization": f"Bearer {who}"}


def fields(**changes: Any) -> dict[str, Any]:
    """
    Prepare or exercise fields in the test lesson search copy test scenario.
    """
    return {
        "title": "Copy of Transport",
        "lesson_date": "2026-10-26",
        "tags": ["transport"],
        "description": "Notes",
        **changes,
    }


@dataclass
class Library:
    client: TestClient
    factory: sessionmaker
    storage: Path

    def create(self, who: str = "author", **changes: Any) -> dict[str, Any]:
        """
        Prepare or exercise create in the test lesson search copy test scenario.
        """
        reply = self.client.post("/lessons", headers=auth(who), json=fields(**changes))
        assert reply.status_code == 201, reply.text
        return reply.json()

    def upload(self, lesson: dict[str, Any], **changes: Any) -> dict[str, Any]:
        """
        Prepare or exercise upload in the test lesson search copy test scenario.
        """
        reply = self.client.post(
            f"/lessons/{lesson['id']}/materials",
            headers=auth(),
            files={
                "file": (
                    changes.get("name", "Te reo Māori.pdf"),
                    changes.get("content", PDF),
                    "application/pdf",
                )
            },
            data={"share_with_learners": "true"},
        )
        assert reply.status_code == 201, reply.text
        return reply.json()

    def count(self) -> int:
        """
        Prepare or exercise count in the test lesson search copy test scenario.
        """
        with self.factory() as db:
            return db.scalar(select(func.count()).select_from(lessons))

    def copy(self, source: dict[str, Any], who: str = "other", **changes: Any):
        """
        Prepare or exercise copy in the test lesson search copy test scenario.
        """
        return self.client.post(
            f"/lessons/{source['id']}/copy", headers=auth(who), json=fields(**changes)
        )

    def search(self, **params: str) -> list[dict[str, Any]]:
        """
        Prepare or exercise search in the test lesson search copy test scenario.
        """
        reply = self.client.get("/lessons", headers=auth("other"), params=params)
        assert reply.status_code == 200, reply.text
        return reply.json()


@pytest.fixture
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Library]:
    """
    Provide isolated lesson-library fixture including database and file storage.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'library.sqlite'}")

    # PostgreSQL lower() handles Unicode; supply the equivalent for isolated SQLite tests.
    @event.listens_for(engine, "connect")
    def unicode_lower(connection, _):
        """
        Prepare or exercise unicode lower in the test lesson search copy test scenario.
        """
        connection.create_function(
            "lower", 1, lambda value: value.casefold() if value is not None else None
        )

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    storage = tmp_path / "materials"

    def staff(token: str) -> user_client.Staff:
        """
        Prepare or exercise staff in the test lesson search copy test scenario.
        """
        people = {
            "Bearer author": AUTHOR,
            "Bearer other": OTHER,
            "Bearer coordinator": COORDINATOR,
        }
        if token not in people:
            raise user_client.LoginRequiredError()
        return people[token]

    monkeypatch.setattr(user_client, "current_staff", staff)
    app = FastAPI()
    app.include_router(create_lesson_router(factory, storage))
    app.include_router(create_copy_router(factory, storage))
    app.include_router(create_maori_review_router(factory))
    with TestClient(app) as client:
        yield Library(client, factory, storage)
    engine.dispose()


def test_exact_tag_filter_returns_only_two_of_ten(library: Library) -> None:
    """
    Verify that exact tag filter returns only two of ten.
    """
    for index in range(10):
        library.create(
            title=f"Lesson {index}",
            tags=["transport" if index < 2 else "transportation"],
        )
    assert len(library.search(tag="transport")) == 2
    assert library.search(tag="trans") == []


@pytest.mark.parametrize(
    "keyword", ["transport", "TRANSPORT", "TrAnSpOrT", "  transport  "]
)
def test_title_search_ignores_case_and_whitespace(
    library: Library, keyword: str
) -> None:
    """
    Verify that title search ignores case and whitespace.
    """
    expected = library.create(title="Local Transport", tags=["health"])
    library.create(title="Shopping", tags=["shopping"])
    assert [item["id"] for item in library.search(q=keyword)] == [expected["id"]]


def test_keyword_can_match_tags_and_combines_with_exact_tag(library: Library) -> None:
    """
    Verify that keyword can match tags and combines with exact tag.
    """
    expected = library.create(title="Bus", tags=["transport", "health"])
    library.create(title="Bus", tags=["shopping"])
    assert [item["id"] for item in library.search(q="HEALTH", tag="transport")] == [
        expected["id"]
    ]
    assert library.search(q="Bus", tag="missing") == []


def test_description_filename_and_file_text_are_not_searched(library: Library) -> None:
    """
    Verify that description filename and file text are not searched.
    """
    source = library.create(title="Lesson", tags=["general"], description="uniquenotes")
    library.upload(
        source, name="uniquefilename.pdf", content=b"%PDF-1.7 uniquefiletext"
    )
    for keyword in ["uniquenotes", "uniquefilename", "uniquefiletext"]:
        assert library.search(q=keyword) == []


@pytest.mark.parametrize("keyword", ["%", "_", "\\", "' OR 1=1 --"])
def test_keyword_wildcards_are_literal_and_sql_is_parameterized(
    library: Library, keyword: str
) -> None:
    """
    Verify that keyword wildcards are literal and sql is parameterized.
    """
    match = library.create(title="Literal " + keyword, tags=["general"])
    library.create(title="Different lesson", tags=["general"])
    assert [item["id"] for item in library.search(q=keyword)] == [match["id"]]


def test_unicode_macrons_and_case_are_preserved(library: Library) -> None:
    """
    Verify that unicode macrons and case are preserved.
    """
    source = library.create(title="Te reo Māori", tags=["language"])
    assert library.search(q="MĀORI")[0]["title"] == "Te reo Māori"
    assert (
        library.client.get(f"/lessons/{source['id']}/copy", headers=auth()).json()[
            "title"
        ]
        == "Copy of Te reo Māori"
    )


def test_deleted_lessons_never_appear_in_search_or_copy(library: Library) -> None:
    """
    Verify that deleted lessons never appear in search or copy.
    """
    source = library.create()
    library.client.delete(f"/lessons/{source['id']}", headers=auth())
    assert library.search(q="Transport") == []
    assert (
        library.client.get(f"/lessons/{source['id']}/copy", headers=auth()).status_code
        == 404
    )
    assert library.copy(source).status_code == 404


def test_empty_and_no_result_search_and_input_limits(library: Library) -> None:
    """
    Verify that empty and no result search and input limits.
    """
    library.create()
    assert len(library.search(q="  ", tag="  ")) == 1
    assert library.search(q="not found") == []
    for params in [{"q": "a" * 256}, {"tag": "a" * 101}]:
        assert (
            library.client.get("/lessons", headers=auth(), params=params).status_code
            == 422
        )


def test_search_responds_within_two_seconds(library: Library) -> None:
    """
    Verify that search responds within two seconds.
    """
    for index in range(50):
        library.create(title=f"Transport {index}")
    started = monotonic()
    assert len(library.search(q="transport")) == 50
    assert monotonic() - started < 2


@pytest.mark.parametrize("who", [None, "visitor"])
def test_search_and_copy_require_staff(library: Library, who: str | None) -> None:
    """
    Verify that search and copy require staff.
    """
    source = library.create()
    headers = auth(who) if who else {}
    for method, path in [
        ("GET", "/lessons?q=Transport"),
        ("GET", f"/lessons/{source['id']}/copy"),
        ("POST", f"/lessons/{source['id']}/copy"),
    ]:
        assert (
            library.client.request(
                method,
                path,
                headers=headers,
                json=fields() if method == "POST" else None,
            ).status_code
            == 401
        )
    assert library.count() == 1


def test_copy_draft_is_unsaved_keeps_materials_tags_notes_and_empty_date(
    library: Library,
) -> None:
    """
    Verify that copy draft is unsaved keeps materials tags notes and empty date.
    """
    source = library.create(title="Transport", tags=["transport", "health"])
    material = library.upload(source)
    before = library.client.get(f"/lessons/{source['id']}", headers=auth()).json()
    for _ in range(2):
        reply = library.client.get(
            f"/lessons/{source['id']}/copy", headers=auth("other")
        )
        assert reply.status_code == 200
        draft = reply.json()
        assert draft["title"] == "Copy of Transport" and draft["lesson_date"] is None
        assert (
            draft["tags"] == ["health", "transport"] and draft["description"] == "Notes"
        )
        assert draft["materials"][0]["file_name"] == material["file_name"]
        assert draft["materials"][0]["share_with_learners"] is False
        assert "storage_key" not in reply.text and "created_by" not in draft
    assert library.count() == 1
    assert len(list(library.storage.iterdir())) == 1
    assert (
        library.client.get(f"/lessons/{source['id']}", headers=auth()).json() == before
    )


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"lesson_date": None}, "lesson_date"),
        ({"title": " "}, "title"),
        ({"tags": []}, "tags"),
        ({"title": "x" * 256}, "title"),
    ],
)
def test_copy_validation_saves_nothing(
    library: Library, changes: dict, field: str
) -> None:
    """
    Verify that copy validation saves nothing.
    """
    source = library.create()
    response = library.copy(source, **changes)
    assert response.status_code == 422
    assert field in response.json()["detail"]["errors"]
    if field == "lesson_date":
        assert response.json()["detail"]["errors"][field] == "Lesson date is required"
    assert library.count() == 1


@pytest.mark.parametrize("who", ["author", "other", "coordinator"])
def test_new_copy_has_current_author_and_independent_metadata(
    library: Library, who: str
) -> None:
    """
    Verify that new copy has current author and independent metadata.
    """
    source = library.create(title="Original", lesson_date="2025-01-01")
    response = library.copy(
        source, who=who, title="New topic", tags=["shopping"], description="New notes"
    )
    assert response.status_code == 201
    copy = response.json()
    people = {"author": AUTHOR, "other": OTHER, "coordinator": COORDINATOR}
    assert copy["created_by"] == str(people[who].id)
    assert copy["can_edit"] and copy["title"] == "New topic"
    assert copy["lesson_date"] == "2026-10-26" and copy["tags"] == ["shopping"]
    with library.factory() as db:
        row = (
            db.execute(select(lessons).where(lessons.c.id == UUID(copy["id"])))
            .mappings()
            .one()
        )
        assert row["source_lesson_id"] == UUID(source["id"])
    original = library.client.get(f"/lessons/{source['id']}", headers=auth()).json()
    assert original["title"] == "Original" and original["lesson_date"] == "2025-01-01"
    if who == "other":
        assert (
            library.client.put(
                f"/lessons/{source['id']}", headers=auth(who), json=fields()
            ).status_code
            == 403
        )


def test_copied_file_survives_original_deletion_and_keeps_original_name(
    library: Library,
) -> None:
    """
    Verify that copied file survives original deletion and keeps original name.
    """
    source = library.create()
    old = library.upload(source)
    saved = library.copy(source).json()
    new = saved["materials"][0]
    assert new["id"] != old["id"] and new["share_with_learners"] is False
    with library.factory() as db:
        keys = db.execute(select(lesson_materials.c.storage_key)).scalars().all()
        assert len(set(keys)) == 2
    library.client.delete(f"/lessons/{source['id']}", headers=auth())
    response = library.client.get(
        f"/materials/{new['id']}/download", headers=auth("other")
    )
    assert (
        response.content == PDF
        and "M%C4%81ori.pdf" in response.headers["content-disposition"]
    )
    assert (
        library.client.get(
            f"/materials/{old['id']}/download", headers=auth()
        ).status_code
        == 404
    )


def test_deleting_copy_does_not_remove_original_file(library: Library) -> None:
    """
    Verify that deleting copy does not remove original file.
    """
    source = library.create()
    original = library.upload(source)
    copied = library.copy(source).json()
    library.client.delete(f"/lessons/{copied['id']}", headers=auth("other"))
    assert (
        library.client.get(
            f"/materials/{original['id']}/download", headers=auth()
        ).content
        == PDF
    )


def test_draft_can_exclude_materials_without_removing_originals(
    library: Library,
) -> None:
    """
    Verify that draft can exclude materials without removing originals.
    """
    source = library.create()
    original = library.upload(source)
    copied = library.copy(source, material_ids=[]).json()
    assert copied["materials"] == []
    assert (
        library.client.get(
            f"/materials/{original['id']}/download", headers=auth()
        ).content
        == PDF
    )


def test_foreign_and_deleted_material_ids_are_rejected(library: Library) -> None:
    """
    Verify that foreign and deleted material ids are rejected.
    """
    source = library.create()
    other = library.create()
    foreign = library.upload(other)
    assert library.copy(source, material_ids=[foreign["id"]]).status_code == 409
    own = library.upload(source)
    library.client.delete(f"/materials/{own['id']}", headers=auth())
    assert library.copy(source, material_ids=[own["id"]]).status_code == 409
    assert library.count() == 2


def test_review_is_not_inherited_by_copy(library: Library) -> None:
    """
    Verify that review is not inherited by copy.
    """
    source = library.create()
    with library.factory.begin() as db:
        db.execute(
            lessons.update()
            .where(lessons.c.id == UUID(source["id"]))
            .values(
                has_maori_content=True,
                review_status="reviewed",
                reviewer_name="Reviewer",
                review_date=date(2026, 10, 25),
                reviewed_by=COORDINATOR.id,
            )
        )
    assert library.client.get(f"/lessons/{source['id']}/copy", headers=auth()).json()[
        "has_maori_content"
    ]
    result = library.copy(source).json()
    assert result["review_label"] == "Māori content – not yet reviewed"
    with library.factory() as db:
        row = (
            db.execute(select(lessons).where(lessons.c.id == UUID(result["id"])))
            .mappings()
            .one()
        )
        assert (
            row["review_status"] == "pending"
            and row["reviewer_name"] is None
            and row["review_date"] is None
            and row["reviewed_by"] is None
        )
        assert (
            db.execute(
                select(lessons.c.review_status).where(
                    lessons.c.id == UUID(source["id"])
                )
            ).scalar_one()
            == "reviewed"
        )


@pytest.mark.parametrize("failure", ["missing", "outside", "symlink", "size"])
def test_bad_source_file_rolls_back_all_copy_metadata_and_files(
    library: Library, failure: str
) -> None:
    """
    Verify that bad source file rolls back all copy metadata and files.
    """
    source = library.create()
    library.upload(source)
    second = library.upload(source, name="Second.pdf")
    with library.factory.begin() as db:
        row = (
            db.execute(
                select(lesson_materials).where(
                    lesson_materials.c.id == UUID(second["id"])
                )
            )
            .mappings()
            .one()
        )
        if failure == "missing":
            (library.storage / row["storage_key"]).unlink()
        elif failure in ("outside", "symlink"):
            outside = library.storage.parent / "outside"
            outside.write_bytes(PDF)
            if failure == "outside":
                db.execute(
                    lesson_materials.update()
                    .where(lesson_materials.c.id == UUID(second["id"]))
                    .values(storage_key="../outside")
                )
            else:
                path = library.storage / row["storage_key"]
                path.unlink()
                path.symlink_to(outside)
        else:
            (library.storage / row["storage_key"]).write_bytes(b"short")
    before = {p.name for p in library.storage.iterdir()}
    reply = library.copy(source)
    assert reply.status_code == 409
    assert (
        library.count() == 1 and {p.name for p in library.storage.iterdir()} == before
    )
    with library.factory() as db:
        assert db.scalar(select(func.count()).select_from(lesson_materials)) == 2


def test_database_failure_removes_already_copied_files(
    library: Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verify that database failure removes already copied files.
    """
    source = library.create()
    library.upload(source)
    original = lesson_copy.copy_file

    def fail_after_copy(folder, material, created):
        """
        Prepare or exercise fail after copy in the test lesson search copy test
        scenario.
        """
        original(folder, material, created)
        raise OperationalError(
            "insert failed", {}, Exception("stand-in database error")
        )

    monkeypatch.setattr(lesson_copy, "copy_file", fail_after_copy)
    response = library.copy(source)
    assert response.status_code == 503 and library.count() == 1
    assert len(list(library.storage.iterdir())) == 1


def test_existing_target_is_never_deleted_on_key_collision(
    library: Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verify that existing target is never deleted on key collision.
    """
    source = library.create()
    library.upload(source)
    existing = next(library.storage.iterdir())
    monkeypatch.setattr(lesson_copy, "uuid4", lambda: UUID(existing.name))
    assert library.copy(source).status_code == 503
    assert existing.read_bytes() == PDF and library.count() == 1


def test_maximum_size_source_material_copies(library: Library) -> None:
    """
    Verify that maximum size source material copies.
    """
    source = library.create()
    content = b"%PDF-" + b"x" * (MAX_FILE_SIZE - 5)
    library.upload(source, content=content)
    reply = library.copy(source)
    assert (
        reply.status_code == 201
        and reply.json()["materials"][0]["file_size"] == MAX_FILE_SIZE
    )


def test_title_prefix_fits_existing_maximum_length(library: Library) -> None:
    """
    Verify that title prefix fits existing maximum length.
    """
    source = library.create(title="x" * 255)
    draft = library.client.get(f"/lessons/{source['id']}/copy", headers=auth()).json()
    assert draft["title"].startswith("Copy of ") and len(draft["title"]) == 255


def test_unknown_source_and_forged_author_are_not_accepted(library: Library) -> None:
    """
    Verify that unknown source and forged author are not accepted.
    """
    assert (
        library.client.get(f"/lessons/{uuid4()}/copy", headers=auth()).status_code
        == 404
    )
    source = library.create()
    assert library.copy(source, created_by=str(AUTHOR.id)).status_code == 422
