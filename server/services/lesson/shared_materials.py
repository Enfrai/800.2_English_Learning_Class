"""Provide learner material access after classroom sign-in (US-013).

Author: Sandhya Tiwari
Date: 26 Oct 2026
"""

import hmac
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from models import lesson_materials, lessons
from sqlalchemy import select
from sqlalchemy.orm import Session


def internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("INTERNAL_API_KEY", "")
    if (
        not expected
        or not x_internal_key
        or not hmac.compare_digest(expected, x_internal_key)
    ):
        raise HTTPException(403, "Access refused")


def create_shared_router(
    factory: Callable[[], Session], storage: Path | None = None
) -> APIRouter:
    router = APIRouter(dependencies=[Depends(internal_key)])
    folder = storage or Path(os.getenv("MATERIALS_DIR", "/var/lib/ako/materials"))

    def lesson(db: Session, lesson_id: UUID) -> Mapping[str, Any]:
        row = (
            db.execute(
                select(lessons).where(
                    lessons.c.id == lesson_id, lessons.c.deleted_at.is_(None)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(404, "Lesson not found")
        return row

    def visible(row: Mapping[str, Any]) -> bool:
        return not row["has_maori_content"] or row["review_status"] == "reviewed"

    @router.get("/internal/lessons/{lesson_id}/shared-materials")
    def listing(lesson_id: UUID) -> dict[str, Any]:
        with factory() as db:
            row = lesson(db, lesson_id)
            if not visible(row):
                return {"materials": [], "message": "Materials will be added soon"}
            files = (
                db.execute(
                    select(
                        lesson_materials.c.id,
                        lesson_materials.c.file_name,
                        lesson_materials.c.file_size,
                    )
                    .where(
                        lesson_materials.c.lesson_id == lesson_id,
                        lesson_materials.c.share_with_learners.is_(True),
                        lesson_materials.c.deleted_at.is_(None),
                    )
                    .order_by(lesson_materials.c.created_at, lesson_materials.c.id)
                )
                .mappings()
                .all()
            )
            return {
                "materials": [dict(f) for f in files],
                "message": "" if files else "No materials for today",
            }

    @router.get("/internal/lessons/{lesson_id}/shared-materials/{material_id}")
    def download(lesson_id: UUID, material_id: UUID) -> FileResponse:
        with factory() as db:
            if not visible(lesson(db, lesson_id)):
                raise HTTPException(404, "Material not found")
            row = (
                db.execute(
                    select(lesson_materials).where(
                        lesson_materials.c.id == material_id,
                        lesson_materials.c.lesson_id == lesson_id,
                        lesson_materials.c.share_with_learners.is_(True),
                        lesson_materials.c.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise HTTPException(404, "Material not found")
            path = folder / row["storage_key"]
            if path.resolve().parent != folder.resolve() or not path.is_file():
                raise HTTPException(404, "Material not found")
            return FileResponse(
                path,
                media_type=row["mime_type"],
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''"
                    + quote(row["file_name"], safe=""),
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    return router
