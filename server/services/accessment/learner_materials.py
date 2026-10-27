"""Provide learner material access using the shared classroom lesson association.

Author: Sandhya Tiwari
Date: 26 Oct 2026
Updated: Shuohui Liu, 26 Oct 2026
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
from sqlalchemy import select
from sqlalchemy.orm import Session

COOKIE = "ako_materials"
LIFETIME = 24 * 60 * 60


def now() -> datetime:
    """
    Return the current timezone-aware UTC instant.
    """
    return datetime.now(UTC)


def digest(token: str) -> str:
    """
    Hash the opaque learner material token with SHA-256.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def issue_grant(
    db: Session, session_id: UUID, response: Response, secure: bool = False
) -> None:
    """
    Persist a 24-hour class-material grant and set its HttpOnly browser cookie.
    """
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
    """
    Request learner-shared lesson data through the key-protected internal API.
    """
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
    factory: Callable[[], Session]
) -> APIRouter:
    """
    Build the materials API router with its injected dependencies.
    """
    router = APIRouter()

    def context(token: str | None):
        """
        Validate the material cookie and resolve its unexpired class and lesson
        association.
        """
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
        """
        Handle GET /learner/materials for materials, applying the route’s validation and
        authorization rules.
        """
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
        """
        Handle GET /learner/materials/{material_id}/download for download, applying the
        route’s validation and authorization rules.
        """
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

    return router
