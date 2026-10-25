"""Provide learner material access after classroom sign-in (US-013).

Author: Sandhya Tiwari
Date: 26 Oct 2026
"""

import hashlib
import json
import os
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import RedirectResponse
from models import class_sessions, learner_material_grants, session_lesson_links
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

COOKIE = "ako_materials"
LIFETIME = 24 * 60 * 60


def now() -> datetime:
    return datetime.now(UTC)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_grant(
    db: Session, session_id: UUID, response: Response, secure: bool = False
) -> None:
    token = secrets.token_urlsafe(32)
    issued = now()
    db.execute(
        learner_material_grants.delete().where(
            learner_material_grants.c.expires_at <= issued
        )
    )
    db.execute(
        learner_material_grants.insert().values(
            token_hash=digest(token),
            session_id=session_id,
            issued_at=issued,
            expires_at=issued + timedelta(seconds=LIFETIME),
        )
    )
    response.set_cookie(
        COOKIE,
        token,
        max_age=LIFETIME,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def lesson_request(path: str) -> tuple[bytes, dict[str, str]]:
    key = os.getenv("INTERNAL_API_KEY", "")
    if not key:
        raise HTTPException(503, "Materials are not available right now")
    base = os.getenv("LESSON_SERVICE_URL", "http://lesson-service:8000")
    request = Request(base + path, headers={"X-Internal-Key": key})
    try:
        with urlopen(request, timeout=10) as reply:
            return reply.read(), dict(reply.headers)
    except HTTPError as exc:
        raise HTTPException(
            404 if exc.code == 404 else 503,
            "Material is no longer available"
            if exc.code == 404
            else "Materials are not available right now",
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HTTPException(503, "Materials are not available right now") from exc


def create_materials_router(
    factory: Callable[[], Session], logged_in_staff: Any
) -> APIRouter:
    router = APIRouter()

    def context(token: str | None):
        if not token or not 32 <= len(token) <= 256:
            raise HTTPException(401, "Please scan a class code and sign in again")
        with factory() as db:
            row = (
                db.execute(
                    select(
                        class_sessions.c.id,
                        class_sessions.c.session_date,
                        session_lesson_links.c.lesson_id,
                    )
                    .select_from(
                        learner_material_grants.join(
                            class_sessions,
                            learner_material_grants.c.session_id == class_sessions.c.id,
                        ).outerjoin(
                            session_lesson_links,
                            session_lesson_links.c.session_id == class_sessions.c.id,
                        )
                    )
                    .where(
                        learner_material_grants.c.token_hash == digest(token),
                        learner_material_grants.c.expires_at > now(),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise HTTPException(401, "Please scan a class code and sign in again")
            return row

    @router.get("/learner/materials")
    def materials(ako_materials: str | None = Cookie(default=None)) -> dict[str, Any]:
        row = context(ako_materials)
        result = {
            "session_date": row["session_date"],
            "materials": [],
            "message": "No materials for today",
        }
        if row["lesson_id"]:
            body, _ = lesson_request(
                f"/internal/lessons/{row['lesson_id']}/shared-materials"
            )
            try:
                result.update(json.loads(body))
            except (ValueError, TypeError) as exc:
                raise HTTPException(
                    503, "Materials are not available right now"
                ) from exc
        return result

    @router.get("/learner/materials/{material_id}/download")
    def download(
        material_id: UUID, ako_materials: str | None = Cookie(default=None)
    ) -> Response:
        try:
            row = context(ako_materials)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse(
                    "/sign-in", status_code=303, headers={"Cache-Control": "no-store"}
                )
            raise
        if not row["lesson_id"]:
            raise HTTPException(404, "Material is no longer available")
        body, headers = lesson_request(
            f"/internal/lessons/{row['lesson_id']}/shared-materials/{material_id}"
        )
        allowed = {
            k: v
            for k, v in headers.items()
            if k.lower() in ("content-type", "content-disposition")
        }
        return Response(
            body,
            headers={
                **allowed,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    class LinkIn(BaseModel):
        lesson_id: UUID | None = None

    @router.get("/sessions/{session_id}/lesson")
    def get_link(session_id: UUID, staff: logged_in_staff) -> dict[str, UUID | None]:
        with factory() as db:
            if not db.execute(
                select(class_sessions.c.id).where(class_sessions.c.id == session_id)
            ).first():
                raise HTTPException(404, "Class session not found")
            lesson_id = db.execute(
                select(session_lesson_links.c.lesson_id).where(
                    session_lesson_links.c.session_id == session_id
                )
            ).scalar_one_or_none()
            return {"lesson_id": lesson_id}

    @router.put("/sessions/{session_id}/lesson")
    def link(
        session_id: UUID, payload: LinkIn, staff: logged_in_staff
    ) -> dict[str, UUID | None]:
        # Validate the cross-service reference before holding a write lock.
        if payload.lesson_id:
            lesson_request(f"/internal/lessons/{payload.lesson_id}/shared-materials")
        with factory() as db, db.begin():
            if not db.execute(
                select(class_sessions.c.id)
                .where(class_sessions.c.id == session_id)
                .with_for_update()
            ).first():
                raise HTTPException(404, "Class session not found")
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
        return {"lesson_id": payload.lesson_id}

    return router
