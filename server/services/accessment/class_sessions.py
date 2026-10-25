"""Manage dated classes, shared lesson links and related access grants safely.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID

import lesson_client
from fastapi import APIRouter, Depends, HTTPException, Response
from models import (
    attendance_records,
    checkin_windows,
    class_sessions,
    learner_material_grants,
    session_lesson_links,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

HAS_ATTENDANCE = "This session has attendance and cannot be deleted"
FUTURE_DATE = "Date cannot be in the future"


class SessionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_date: date | None = None


class LessonLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lesson_id: UUID | None = None


def find_session(
    db: Session, session_id: UUID, *, lock: bool = False
) -> dict[str, Any]:
    statement = select(class_sessions).where(class_sessions.c.id == session_id)
    if lock:
        statement = statement.with_for_update()
    row = db.execute(statement).mappings().first()
    if row is None:
        raise HTTPException(404, "Class session not found")
    return dict(row)


def create_session_router(
    factory: Callable[[], Session],
    staff_dependency: Callable,
    today: Callable[[], date],
) -> APIRouter:
    router = APIRouter(tags=["US-014 class sessions"])

    def allowed(request: Any) -> None:
        if request.staff.role not in ("teacher", "coordinator"):
            raise HTTPException(403, "You do not have permission")

    def output(
        db: Session, row: dict[str, Any], titles: dict[UUID, str]
    ) -> dict[str, Any]:
        lesson_id = db.scalar(
            select(session_lesson_links.c.lesson_id).where(
                session_lesson_links.c.session_id == row["id"]
            )
        )
        count = db.scalar(
            select(func.count())
            .select_from(attendance_records)
            .where(attendance_records.c.session_id == row["id"])
        )
        present = db.scalar(
            select(func.count())
            .select_from(attendance_records)
            .where(
                attendance_records.c.session_id == row["id"],
                attendance_records.c.status == "present",
            )
        )
        return {
            "id": row["id"],
            "session_date": row["session_date"],
            "lesson_id": lesson_id,
            "lesson_title": titles.get(lesson_id) if lesson_id else None,
            "lesson_unavailable": bool(lesson_id and lesson_id not in titles),
            "attendance_count": count,
            "present_count": present,
            "can_delete": count == 0,
        }

    def titles_for(db: Session, ids: list[UUID], authorization: str) -> dict[UUID, str]:
        linked = db.scalar(
            select(session_lesson_links.c.session_id)
            .where(
                session_lesson_links.c.session_id.in_(ids),
                session_lesson_links.c.lesson_id.is_not(None),
            )
            .limit(1)
        )
        if linked is None:
            return {}
        try:
            return lesson_client.lesson_titles(authorization)
        except lesson_client.LessonServiceError as exc:
            raise HTTPException(
                503, "Lesson titles could not be loaded. Please try again."
            ) from exc

    @router.get("/sessions")
    def listing(request: Any = Depends(staff_dependency)) -> dict[str, Any]:
        allowed(request)
        with factory() as db:
            rows = (
                db.execute(
                    select(class_sessions).order_by(
                        class_sessions.c.session_date.desc(), class_sessions.c.id
                    )
                )
                .mappings()
                .all()
            )
            titles = titles_for(db, [row["id"] for row in rows], request.authorization)
            return {
                "today": today(),
                "sessions": [output(db, dict(row), titles) for row in rows],
            }

    def create_on(day: date, request: Any) -> dict[str, Any]:
        allowed(request)
        if day > today():
            raise HTTPException(
                422, detail={"field": "session_date", "message": FUTURE_DATE}
            )
        with factory() as db, db.begin():
            insert = (
                pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
            )
            row = (
                db.execute(
                    insert(class_sessions)
                    .values(session_date=day, created_by=request.staff.id)
                    .on_conflict_do_nothing(index_elements=["session_date"])
                    .returning(class_sessions)
                )
                .mappings()
                .first()
            )
            created = row is not None
            if row is None:
                row = (
                    db.execute(
                        select(class_sessions).where(
                            class_sessions.c.session_date == day
                        )
                    )
                    .mappings()
                    .one()
                )
            # A tiny return keeps the start-class operation independent of Lesson availability.
            return {
                "id": row["id"],
                "session_date": row["session_date"],
                "created": created,
            }

    @router.post("/sessions/today")
    def start_today(request: Any = Depends(staff_dependency)) -> dict[str, Any]:
        return create_on(today(), request)

    @router.post("/sessions")
    def create(
        payload: SessionIn, request: Any = Depends(staff_dependency)
    ) -> dict[str, Any]:
        allowed(request)
        if payload.session_date is None:
            raise HTTPException(
                422,
                detail={"field": "session_date", "message": "Class date is required"},
            )
        return create_on(payload.session_date, request)

    @router.get("/sessions/{session_id}")
    def detail(
        session_id: UUID, request: Any = Depends(staff_dependency)
    ) -> dict[str, Any]:
        allowed(request)
        with factory() as db:
            row = find_session(db, session_id)
            return {
                "today": today(),
                **output(db, row, titles_for(db, [session_id], request.authorization)),
            }

    @router.get("/sessions/{session_id}/lesson")
    def get_lesson_link(
        session_id: UUID, request: Any = Depends(staff_dependency)
    ) -> dict[str, Any]:
        allowed(request)
        with factory() as db:
            find_session(db, session_id)
            return {
                "lesson_id": db.scalar(
                    select(session_lesson_links.c.lesson_id).where(
                        session_lesson_links.c.session_id == session_id
                    )
                )
            }

    @router.put("/sessions/{session_id}/lesson")
    def link_lesson(
        session_id: UUID,
        payload: LessonLinkIn,
        request: Any = Depends(staff_dependency),
    ) -> dict[str, Any]:
        allowed(request)
        with factory() as db:
            find_session(db, session_id)
        title = None
        if payload.lesson_id:
            try:
                title = lesson_client.lesson_title(
                    payload.lesson_id, request.authorization
                )
            except lesson_client.LessonUnavailableError as exc:
                raise HTTPException(404, "Lesson is no longer available") from exc
            except lesson_client.LessonServiceError as exc:
                raise HTTPException(
                    503, "The lesson could not be checked. Please try again."
                ) from exc
        with factory() as db, db.begin():
            row = find_session(db, session_id, lock=True)
            db.execute(
                session_lesson_links.delete().where(
                    session_lesson_links.c.session_id == session_id
                )
            )
            db.execute(
                session_lesson_links.insert().values(
                    session_id=session_id, lesson_id=payload.lesson_id
                )
            )
            titles = {payload.lesson_id: title} if payload.lesson_id else {}
            return output(db, row, titles)

    @router.delete("/sessions/{session_id}", status_code=204)
    def delete(session_id: UUID, request: Any = Depends(staff_dependency)) -> Response:
        allowed(request)
        try:
            with factory() as db, db.begin():
                find_session(db, session_id, lock=True)
                if db.scalar(
                    select(func.count())
                    .select_from(attendance_records)
                    .where(attendance_records.c.session_id == session_id)
                ):
                    raise HTTPException(409, HAS_ATTENDANCE)
                db.execute(
                    learner_material_grants.delete().where(
                        learner_material_grants.c.session_id == session_id
                    )
                )
                db.execute(
                    checkin_windows.delete().where(
                        checkin_windows.c.session_id == session_id
                    )
                )
                db.execute(
                    session_lesson_links.delete().where(
                        session_lesson_links.c.session_id == session_id
                    )
                )
                db.execute(
                    class_sessions.delete().where(class_sessions.c.id == session_id)
                )
        except IntegrityError as exc:
            # A defensive FK barrier also protects against writers outside these routes.
            raise HTTPException(
                409, "This session has related records and cannot be deleted"
            ) from exc
        return Response(status_code=204)

    return router
