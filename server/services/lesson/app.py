"""Lesson Service: lessons, topic tags and lesson files (US-006).

Every endpoint except ``/health`` needs a login. The session is checked with
the User Service, and the author and role come from that check, never from
the request body.

Author: Shuohui Liu
Date: 19 Oct 2026
Updated: Sandhya Tiwari, 23 Oct 2026 (US-006 lesson endpoints)
Updated: Sandhya Tiwari, 24 Oct 2026 (teacher access to materials: file counts,
review status, no caching of downloaded files)
"""

import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import user_client
from files import FileRuleError, FileStore
from lessons import (
    LessonError,
    LessonNotFoundError,
    LessonPermissionError,
    LessonValidationError,
    add_lesson,
    add_material,
    can_change,
    check_can_add_material,
    delete_lesson,
    get_lesson,
    get_material,
    list_lessons,
    list_tags,
    remove_material,
    seed_tags,
    set_share_with_learners,
    update_lesson,
)
from models import Base

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")
# Any fixed number; it only has to be the same for every replica of this service.
STARTUP_LOCK_KEY = 800_2
file_store = FileStore.from_environment()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Both replicas start at the same time. Without this lock they can both try
    # to create the tables on a new database, and one fails to start.
    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": STARTUP_LOCK_KEY}
        )
        Base.metadata.create_all(bind=connection)
    with SessionLocal.begin() as db:
        seed_tags(db)
    file_store.root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Lesson Service", lifespan=lifespan)


def logged_in_staff(
    authorization: Annotated[str | None, Header()] = None,
) -> user_client.Staff:
    """Check the session with the User Service. Teachers and coordinators pass."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Login required")
    try:
        return user_client.current_staff(authorization)
    except user_client.LoginRequiredError as exc:
        raise HTTPException(status_code=401, detail="Login required") from exc
    except user_client.UserServiceError as exc:
        raise HTTPException(status_code=503, detail="User service unavailable") from exc


LoggedInStaff = Annotated[user_client.Staff, Depends(logged_in_staff)]


def lesson_http_error(exc: LessonError) -> HTTPException:
    """Translate a lesson error into the HTTP response the website shows."""
    if isinstance(exc, LessonNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, LessonPermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LessonValidationError):
        return HTTPException(
            status_code=422, detail={"field": exc.field, "message": exc.message}
        )
    return HTTPException(status_code=400, detail=str(exc))


class LessonIn(BaseModel):
    """Lesson details. Rules are checked in lessons.py so messages match US-006."""

    title: str | None = None
    lesson_date: date | None = None
    tags: list[str] | None = None


class MaterialOut(BaseModel):
    id: UUID
    file_name: str
    mime_type: str
    file_size: int
    share_with_learners: bool
    created_at: datetime


class LessonSummaryOut(BaseModel):
    id: UUID
    title: str
    lesson_date: date
    tags: list[str]
    created_by: UUID
    # True when the logged-in user may edit or delete it (author or coordinator).
    can_change: bool
    updated_at: datetime
    # Files that can be downloaded.
    material_count: int
    # US-008: the page shows "Māori content – not yet reviewed" until reviewed.
    has_maori_content: bool
    review_status: str


class LessonOut(LessonSummaryOut):
    materials: list[MaterialOut]


class ShareIn(BaseModel):
    share_with_learners: bool


def with_can_change(lesson: dict, staff: user_client.Staff) -> dict:
    return {**lesson, "can_change": can_change(lesson, staff)}


@app.get("/health")
def health():
    return {"status": "ok", "instance": INSTANCE}


@app.get("/tags", response_model=list[str])
def read_tags(staff: LoggedInStaff):
    with SessionLocal() as db:
        return list_tags(db)


@app.get("/lessons", response_model=list[LessonSummaryOut])
def read_lessons(staff: LoggedInStaff):
    with SessionLocal() as db:
        return [with_can_change(lesson, staff) for lesson in list_lessons(db)]


@app.post("/lessons", response_model=LessonOut, status_code=201)
def create_lesson(payload: LessonIn, staff: LoggedInStaff):
    try:
        with SessionLocal.begin() as db:
            lesson = add_lesson(
                db,
                title=payload.title,
                lesson_date=payload.lesson_date,
                tag_names=payload.tags,
                created_by=staff.id,
            )
            return with_can_change(lesson, staff)
    except LessonError as exc:
        raise lesson_http_error(exc) from exc


@app.get("/lessons/{lesson_id}", response_model=LessonOut)
def read_lesson(lesson_id: UUID, staff: LoggedInStaff):
    try:
        with SessionLocal() as db:
            return with_can_change(get_lesson(db, lesson_id), staff)
    except LessonError as exc:
        raise lesson_http_error(exc) from exc


@app.put("/lessons/{lesson_id}", response_model=LessonOut)
def change_lesson(lesson_id: UUID, payload: LessonIn, staff: LoggedInStaff):
    try:
        with SessionLocal.begin() as db:
            lesson = update_lesson(
                db,
                lesson_id,
                title=payload.title,
                lesson_date=payload.lesson_date,
                tag_names=payload.tags,
                staff=staff,
            )
            return with_can_change(lesson, staff)
    except LessonError as exc:
        raise lesson_http_error(exc) from exc


@app.delete("/lessons/{lesson_id}", status_code=204)
def remove_lesson(lesson_id: UUID, staff: LoggedInStaff):
    try:
        with SessionLocal.begin() as db:
            delete_lesson(db, lesson_id, staff=staff)
    except LessonError as exc:
        raise lesson_http_error(exc) from exc
    return Response(status_code=204)


@app.post("/lessons/{lesson_id}/materials", response_model=MaterialOut, status_code=201)
def upload_material(
    lesson_id: UUID,
    staff: LoggedInStaff,
    file: Annotated[UploadFile, File()],
    share_with_learners: Annotated[bool, Form()] = False,
):
    try:
        with SessionLocal() as db:
            check_can_add_material(db, lesson_id, staff=staff)
        stored = file_store.save(file.filename, file.file)
    except LessonError as exc:
        raise lesson_http_error(exc) from exc
    except FileRuleError as exc:
        raise HTTPException(
            status_code=422, detail={"field": "file", "message": exc.message}
        ) from exc
    try:
        with SessionLocal.begin() as db:
            return add_material(
                db,
                lesson_id,
                file_name=stored.file_name,
                storage_key=stored.storage_key,
                mime_type=stored.mime_type,
                file_size=stored.file_size,
                share_with_learners=share_with_learners,
                staff=staff,
            )
    except LessonError as exc:
        # The lesson changed while the file was stored; do not keep the file.
        file_store.remove(stored.storage_key)
        raise lesson_http_error(exc) from exc
    except Exception:
        file_store.remove(stored.storage_key)
        raise


@app.patch("/materials/{material_id}", response_model=MaterialOut)
def change_material(material_id: UUID, payload: ShareIn, staff: LoggedInStaff):
    try:
        with SessionLocal.begin() as db:
            return set_share_with_learners(
                db, material_id, share=payload.share_with_learners, staff=staff
            )
    except LessonError as exc:
        raise lesson_http_error(exc) from exc


@app.delete("/materials/{material_id}", status_code=204)
def delete_material(material_id: UUID, staff: LoggedInStaff):
    try:
        with SessionLocal.begin() as db:
            remove_material(db, material_id, staff=staff)
    except LessonError as exc:
        raise lesson_http_error(exc) from exc
    return Response(status_code=204)


@app.get("/materials/{material_id}/download")
def download_material(material_id: UUID, staff: LoggedInStaff):
    """Send the file with its original name, including macrons (UT-41)."""
    try:
        with SessionLocal() as db:
            material = get_material(db, material_id)
    except LessonError as exc:
        raise lesson_http_error(exc) from exc
    path = file_store.path_for(material["storage_key"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path,
        media_type=material["mime_type"],
        filename=material["file_name"],
        # Browsers must use the stored type, never guess one from the content.
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
