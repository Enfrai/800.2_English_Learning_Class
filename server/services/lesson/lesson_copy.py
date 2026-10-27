"""Create independent lesson copies from unsaved drafts (US-007).

Author: Sandhya Tiwari
Date: 26 Oct 2026
"""

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from lesson_api import (
    MAX_FILE_SIZE,
    LessonIn,
    find_lesson,
    lesson_out,
    save_tags,
    validate_lesson,
)
from maori_review_api import LoggedInStaff
from models import lesson_materials, lessons
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CopyIn(LessonIn):
    material_ids: list[UUID] | None = Field(default=None, max_length=1000)


def copy_file(folder: Path, material: dict[str, Any], created: list[Path]) -> str:
    """Copy bounded file content under a new key; never reuse source storage."""
    source = folder / material["storage_key"]
    if source.resolve().parent != folder.resolve():
        raise HTTPException(
            409, "A source material is unavailable. Reopen the copy draft."
        )
    key = uuid4().hex
    target = folder / key
    try:
        with source.open("rb") as original, target.open("xb") as output:
            created.append(target)
            size = 0
            while chunk := original.read(64 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(
                        409, "A source material exceeds the file size limit."
                    )
                output.write(chunk)
            if size != material["file_size"]:
                raise HTTPException(
                    409, "A source material changed. Reopen the copy draft."
                )
    except FileNotFoundError as exc:
        raise HTTPException(
            409, "A source material is unavailable. Reopen the copy draft."
        ) from exc
    return key


def create_copy_router(
    factory: Callable[[], Session], storage: Path | None = None
) -> APIRouter:
    """
    Build the copy API router with its injected dependencies.
    """
    router = APIRouter(tags=["US-007 lesson copies"])
    folder = storage or Path(os.getenv("MATERIALS_DIR", "/var/lib/ako/materials"))

    @router.get("/lessons/{lesson_id}/copy")
    def draft(lesson_id: UUID, staff: LoggedInStaff) -> dict[str, Any]:
        """
        Handle GET /lessons/{lesson_id}/copy for draft, applying the route’s validation
        and authorization rules.
        """
        with factory() as db:
            source = find_lesson(db, lesson_id)
            result = lesson_out(db, source, staff)
            return {
                "source_lesson_id": lesson_id,
                "title": ("Copy of " + source["title"])[:255],
                "lesson_date": None,
                "description": source["description"] or "",
                "tags": result["tags"],
                "materials": [
                    {**item, "share_with_learners": False}
                    for item in result["materials"]
                ],
                "has_maori_content": source["has_maori_content"],
            }

    @router.post("/lessons/{lesson_id}/copy", status_code=201)
    def save_copy(
        lesson_id: UUID, payload: CopyIn, staff: LoggedInStaff
    ) -> dict[str, Any]:
        """
        Handle POST /lessons/{lesson_id}/copy for save copy, applying the route’s
        validation and authorization rules.
        """
        title, names = validate_lesson(payload)
        created: list[Path] = []
        try:
            with factory() as db, db.begin():
                # All source edits/deletes take this same row lock (US-006).
                source = (
                    db.execute(
                        select(lessons)
                        .where(
                            lessons.c.id == lesson_id, lessons.c.deleted_at.is_(None)
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if source is None:
                    raise HTTPException(404, "Lesson not found")
                files = (
                    db.execute(
                        select(lesson_materials).where(
                            lesson_materials.c.lesson_id == lesson_id,
                            lesson_materials.c.deleted_at.is_(None),
                        )
                    )
                    .mappings()
                    .all()
                )
                selected = (
                    set(payload.material_ids)
                    if payload.material_ids is not None
                    else {item["id"] for item in files}
                )
                if not selected <= {item["id"] for item in files}:
                    raise HTTPException(
                        409, "Source materials changed. Reopen the copy draft."
                    )
                copied = (
                    db.execute(
                        lessons.insert()
                        .values(
                            title=title,
                            description=payload.description,
                            lesson_date=payload.lesson_date,
                            created_by=staff.id,
                            source_lesson_id=lesson_id,
                            has_maori_content=source["has_maori_content"],
                            review_status="pending"
                            if source["has_maori_content"]
                            else "not_required",
                        )
                        .returning(lessons)
                    )
                    .mappings()
                    .one()
                )
                save_tags(db, copied["id"], names)
                for item in files:
                    if item["id"] not in selected:
                        continue
                    key = copy_file(folder, dict(item), created)
                    db.execute(
                        lesson_materials.insert().values(
                            lesson_id=copied["id"],
                            file_name=item["file_name"],
                            storage_key=key,
                            mime_type=item["mime_type"],
                            file_size=item["file_size"],
                            uploaded_by=staff.id,
                            share_with_learners=False,
                        )
                    )
                result = lesson_out(db, copied, staff)
            return result
        except (HTTPException, OSError, SQLAlchemyError) as exc:
            for path in created:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Unable to remove an uncommitted copied material")
            if isinstance(exc, HTTPException):
                raise
            logger.warning("Lesson copy failed", exc_info=True)
            raise HTTPException(
                503, "The lesson could not be copied. Please try again."
            ) from exc

    return router
