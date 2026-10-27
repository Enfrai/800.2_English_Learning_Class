"""Manage staff lessons, title/topic searches and protected teaching materials.

Author: Sandhya Tiwari
Date: 25 Oct 2026
Updated: Pei Wu, 26 Oct 2026 (Māori content flag and review status, US-008)
"""

import io
import logging
import os
import zipfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from maori_review import reset_review_after_material_change, review_label
from maori_review_api import LoggedInStaff
from models import lesson_materials, lesson_tags, lessons, tags
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

MAX_FILE_SIZE = 10 * 1024 * 1024
TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
FILE_RULE = "Use PDF, DOCX, JPG or PNG files, up to 10 MB (10,485,760 bytes) each"


class LessonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = ""
    lesson_date: date | None = None
    tags: list[str] = []
    description: str = ""


class SharingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    share_with_learners: bool


def validate_lesson(payload: LessonIn) -> tuple[str, list[str]]:
    """
    Validate the lesson title, date and tags and normalize the tag names.
    """
    errors = {}
    title = payload.title.strip()
    if not title:
        errors["title"] = "Title is required"
    elif len(title) > 255:
        errors["title"] = "Title must be 255 characters or fewer"
    if payload.lesson_date is None:
        errors["lesson_date"] = "Lesson date is required"
    names = list(dict.fromkeys(name.strip() for name in payload.tags if name.strip()))
    if not names:
        errors["tags"] = "At least one topic tag is required"
    elif any(len(name) > 100 for name in names):
        errors["tags"] = "Each topic tag must be 100 characters or fewer"
    if errors:
        raise HTTPException(422, detail={"errors": errors})
    return title, names


def find_lesson(db: Session, lesson_id: UUID, staff=None, edit=False):
    """
    Load a live lesson, optionally locking it and requiring author or Coordinator edit
    access.
    """
    query = select(lessons).where(
        lessons.c.id == lesson_id, lessons.c.deleted_at.is_(None)
    )
    if edit:
        query = query.with_for_update()
    row = db.execute(query).mappings().first()
    if row is None:
        raise HTTPException(404, detail="Lesson not found")
    if edit and not staff.is_coordinator and row["created_by"] != staff.id:
        raise HTTPException(403, detail="You do not have permission")
    return dict(row)


def save_tags(db: Session, lesson_id: UUID, names: list[str]):
    """
    Replace the lesson’s tag associations using normalized reusable tag records.
    """
    db.execute(lesson_tags.delete().where(lesson_tags.c.lesson_id == lesson_id))
    for name in names:
        insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        db.execute(
            insert(tags)
            .values(name=name)
            .on_conflict_do_nothing(index_elements=["name"])
        )
        tag_id = db.scalar(select(tags.c.id).where(tags.c.name == name))
        db.execute(lesson_tags.insert().values(lesson_id=lesson_id, tag_id=tag_id))


def material_out(row):
    """
    Project stored material metadata into the public staff API response.
    """
    return {
        key: row[key]
        for key in (
            "id",
            "lesson_id",
            "file_name",
            "mime_type",
            "file_size",
            "share_with_learners",
            "created_at",
        )
    }


def lesson_out(db: Session, lesson, staff):
    """
    Build the lesson response with tags, materials and staff edit permissions.
    """
    names = (
        db.execute(
            select(tags.c.name)
            .join(lesson_tags, tags.c.id == lesson_tags.c.tag_id)
            .where(lesson_tags.c.lesson_id == lesson["id"])
            .order_by(tags.c.name)
        )
        .scalars()
        .all()
    )
    materials = (
        db.execute(
            select(lesson_materials)
            .where(
                lesson_materials.c.lesson_id == lesson["id"],
                lesson_materials.c.deleted_at.is_(None),
            )
            .order_by(lesson_materials.c.created_at, lesson_materials.c.id)
        )
        .mappings()
        .all()
    )
    return {
        **{
            key: lesson[key]
            for key in ("id", "title", "lesson_date", "description", "created_by")
        },
        "tags": names,
        "materials": [material_out(row) for row in materials],
        "can_edit": staff.is_coordinator or lesson["created_by"] == staff.id,
        # US-008: the form's tick box and the colour of the review pill.
        "has_maori_content": lesson["has_maori_content"],
        "review_status": lesson["review_status"],
        "review_label": review_label(lesson),
    }


def read_file(upload: UploadFile) -> tuple[str, str, bytes]:
    """
    Read a bounded upload and validate its filename, type and content signature.
    """
    name = (upload.filename or "").replace("\\", "/").split("/")[-1]
    suffix = Path(name).suffix.lower()
    if (
        not name
        or len(name) > 255
        or any(c in name for c in "\r\n\x00")
        or suffix not in TYPES
    ):
        raise HTTPException(422, detail=FILE_RULE)
    chunks, size = [], 0
    while chunk := upload.file.read(64 * 1024):
        size += len(chunk)
        if size > MAX_FILE_SIZE:
            raise HTTPException(413, detail=FILE_RULE)
        chunks.append(chunk)
    data = b"".join(chunks)
    valid = (
        suffix == ".pdf"
        and data.startswith(b"%PDF-")
        or suffix in (".jpg", ".jpeg")
        and data.startswith(b"\xff\xd8\xff")
        or suffix == ".png"
        and data.startswith(b"\x89PNG\r\n\x1a\n")
    )
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                valid = {"[Content_Types].xml", "word/document.xml"} <= set(
                    archive.namelist()
                )
        except (zipfile.BadZipFile, OSError):
            valid = False
    if not valid:
        raise HTTPException(
            422, detail="The file content does not match its type. " + FILE_RULE
        )
    return name, TYPES[suffix], data


def create_lesson_router(
    session_factory: Callable[[], Session], storage: Path | None = None
):
    """
    Build the lesson API router with its injected dependencies.
    """
    router = APIRouter(tags=["US-006 lesson library"])
    folder = storage or Path(os.getenv("MATERIALS_DIR", "/var/lib/ako/materials"))

    def purge(key):
        """
        Remove a stored lesson file when its key stays inside the configured storage
        folder.
        """
        path = folder / key
        if path.parent.resolve() != folder.resolve():
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).warning(
                "Unable to purge a deleted lesson material"
            )

    @router.get("/tags")
    def list_tags(staff: LoggedInStaff):
        """
        Handle GET /tags for list tags, applying the route’s validation and
        authorization rules.
        """
        with session_factory() as db:
            return [
                dict(row)
                for row in db.execute(
                    select(tags.c.id, tags.c.name).order_by(tags.c.name)
                ).mappings()
            ]

    @router.get("/lessons")
    def list_lessons(
        staff: LoggedInStaff,
        q: str = Query(default="", max_length=255),
        tag: str = Query(default="", max_length=100),
    ) -> list[dict]:
        """
        Handle GET /lessons for list lessons, applying the route’s validation and
        authorization rules.
        """
        conditions = [lessons.c.deleted_at.is_(None)]
        keyword, topic = q.strip(), tag.strip()
        if keyword:
            tagged = (
                select(lesson_tags.c.lesson_id)
                .join(tags, lesson_tags.c.tag_id == tags.c.id)
                .where(tags.c.name.icontains(keyword, autoescape=True))
            )
            conditions.append(
                or_(
                    lessons.c.title.icontains(keyword, autoescape=True),
                    lessons.c.id.in_(tagged),
                )
            )
        if topic:
            tagged = (
                select(lesson_tags.c.lesson_id)
                .join(tags, lesson_tags.c.tag_id == tags.c.id)
                .where(tags.c.name == topic)
            )
            conditions.append(lessons.c.id.in_(tagged))
        with session_factory() as db:
            rows = (
                db.execute(
                    select(lessons)
                    .where(*conditions)
                    .order_by(
                        lessons.c.lesson_date.desc(),
                        lessons.c.created_at.desc(),
                        lessons.c.id,
                    )
                )
                .mappings()
                .all()
            )
            return [lesson_out(db, row, staff) for row in rows]

    @router.post("/lessons", status_code=201)
    def create_lesson(payload: LessonIn, staff: LoggedInStaff):
        """
        Handle POST /lessons for create lesson, applying the route’s validation and
        authorization rules.
        """
        title, names = validate_lesson(payload)
        with session_factory() as db, db.begin():
            row = (
                db.execute(
                    lessons.insert()
                    .values(
                        title=title,
                        lesson_date=payload.lesson_date,
                        description=payload.description,
                        created_by=staff.id,
                    )
                    .returning(lessons)
                )
                .mappings()
                .one()
            )
            save_tags(db, row["id"], names)
            return lesson_out(db, row, staff)

    @router.get("/lessons/{lesson_id}")
    def get_lesson(lesson_id: UUID, staff: LoggedInStaff):
        """
        Handle GET /lessons/{lesson_id} for get lesson, applying the route’s validation
        and authorization rules.
        """
        with session_factory() as db:
            return lesson_out(db, find_lesson(db, lesson_id), staff)

    @router.put("/lessons/{lesson_id}")
    def update_lesson(lesson_id: UUID, payload: LessonIn, staff: LoggedInStaff):
        """
        Handle PUT /lessons/{lesson_id} for update lesson, applying the route’s
        validation and authorization rules.
        """
        title, names = validate_lesson(payload)
        with session_factory() as db, db.begin():
            find_lesson(db, lesson_id, staff, edit=True)
            row = (
                db.execute(
                    lessons.update()
                    .where(lessons.c.id == lesson_id)
                    .values(
                        title=title,
                        lesson_date=payload.lesson_date,
                        description=payload.description,
                        updated_at=func.now(),
                    )
                    .returning(lessons)
                )
                .mappings()
                .one()
            )
            save_tags(db, lesson_id, names)
            return lesson_out(db, row, staff)

    @router.delete("/lessons/{lesson_id}", status_code=204)
    def delete_lesson(lesson_id: UUID, staff: LoggedInStaff):
        """
        Handle DELETE /lessons/{lesson_id} for delete lesson, applying the route’s
        validation and authorization rules.
        """
        with session_factory() as db, db.begin():
            find_lesson(db, lesson_id, staff, edit=True)
            keys = db.scalars(
                select(lesson_materials.c.storage_key).where(
                    lesson_materials.c.lesson_id == lesson_id,
                    lesson_materials.c.deleted_at.is_(None),
                )
            ).all()
            db.execute(
                lessons.update()
                .where(lessons.c.id == lesson_id)
                .values(deleted_at=func.now(), updated_at=func.now())
            )
            db.execute(
                lesson_materials.update()
                .where(
                    lesson_materials.c.lesson_id == lesson_id,
                    lesson_materials.c.deleted_at.is_(None),
                )
                .values(deleted_at=func.now())
            )
        for key in keys:
            purge(key)
        # Keep tombstones for session references. Download routes always check them.
        return Response(status_code=204)

    @router.post("/lessons/{lesson_id}/materials", status_code=201)
    def upload_material(
        lesson_id: UUID,
        staff: LoggedInStaff,
        file: UploadFile = File(...),
        share_with_learners: bool = Form(False),
    ):
        """
        Handle POST /lessons/{lesson_id}/materials for upload material, applying the
        route’s validation and authorization rules.
        """
        path = None
        try:
            with session_factory() as db, db.begin():
                find_lesson(db, lesson_id, staff, edit=True)
                name, mime, data = read_file(file)
                folder.mkdir(parents=True, exist_ok=True)
                key = uuid4().hex
                path = folder / key
                with path.open("xb") as output:
                    output.write(data)
                row = (
                    db.execute(
                        lesson_materials.insert()
                        .values(
                            lesson_id=lesson_id,
                            file_name=name,
                            storage_key=key,
                            mime_type=mime,
                            file_size=len(data),
                            uploaded_by=staff.id,
                            share_with_learners=share_with_learners,
                        )
                        .returning(lesson_materials)
                    )
                    .mappings()
                    .one()
                )
                reset_review_after_material_change(db, lesson_id, staff.id)
                result = material_out(row)
            return result
        except Exception:
            if path is not None:
                path.unlink(missing_ok=True)
            raise
        finally:
            file.file.close()

    def find_material(db, material_id):
        """
        Load live material metadata or reject a missing material.
        """
        row = (
            db.execute(
                select(lesson_materials).where(
                    lesson_materials.c.id == material_id,
                    lesson_materials.c.deleted_at.is_(None),
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(404, detail="Material not found")
        return dict(row)

    @router.get("/materials/{material_id}/download")
    def download_material(material_id: UUID, staff: LoggedInStaff):
        """
        Handle GET /materials/{material_id}/download for download material, applying the
        route’s validation and authorization rules.
        """
        with session_factory() as db:
            material = find_material(db, material_id)
            find_lesson(db, material["lesson_id"])
            path = folder / material["storage_key"]
            if path.parent.resolve() != folder.resolve():
                raise HTTPException(404, detail="Material not found")
            try:
                source = path.open("rb")
            except FileNotFoundError as exc:
                raise HTTPException(404, detail="Material file is unavailable") from exc

        def content():
            """
            Stream stored file chunks and close the source when streaming ends.
            """
            try:
                while chunk := source.read(64 * 1024):
                    yield chunk
            finally:
                source.close()

        return StreamingResponse(
            content(),
            media_type=material["mime_type"],
            headers={
                "Content-Disposition": "attachment; filename*=UTF-8''"
                + quote(material["file_name"], safe=""),
                "Content-Length": str(material["file_size"]),
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.patch("/materials/{material_id}")
    def change_sharing(material_id: UUID, payload: SharingIn, staff: LoggedInStaff):
        """
        Handle PATCH /materials/{material_id} for change sharing, applying the route’s
        validation and authorization rules.
        """
        with session_factory() as db, db.begin():
            material = find_material(db, material_id)
            find_lesson(db, material["lesson_id"], staff, edit=True)
            row = (
                db.execute(
                    lesson_materials.update()
                    .where(
                        lesson_materials.c.id == material_id,
                        lesson_materials.c.deleted_at.is_(None),
                    )
                    .values(share_with_learners=payload.share_with_learners)
                    .returning(lesson_materials)
                )
                .mappings()
                .first()
            )
            if row is None:
                raise HTTPException(404, detail="Material not found")
            return material_out(row)

    @router.delete("/materials/{material_id}", status_code=204)
    def delete_material(material_id: UUID, staff: LoggedInStaff):
        """
        Handle DELETE /materials/{material_id} for delete material, applying the route’s
        validation and authorization rules.
        """
        with session_factory() as db, db.begin():
            material = find_material(db, material_id)
            find_lesson(db, material["lesson_id"], staff, edit=True)
            db.execute(
                lesson_materials.update()
                .where(lesson_materials.c.id == material_id)
                .values(deleted_at=func.now())
            )
            reset_review_after_material_change(db, material["lesson_id"], staff.id)
        purge(material["storage_key"])
        return Response(status_code=204)

    return router
