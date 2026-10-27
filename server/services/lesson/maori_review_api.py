"""Endpoints to flag Māori content and record its review (US-008).

Kept apart from the US-006 lesson endpoints; app.py only includes this
router. The session is checked with the User Service, like US-006.

| Method and path | Who | What |
| --- | --- | --- |
| GET /lessons/{id}/review | Staff | Review status, label and learner visibility |
| PUT /lessons/{id}/maori-content | Lesson author or coordinator | Tick or untick |
| POST /lessons/{id}/review | Coordinator | Record a review |

Author: Pei Wu
Date: 25 Oct 2026
"""

import os
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

import user_client
from fastapi import APIRouter, Depends, Header, HTTPException
from maori_review import (
    LessonNotFoundError,
    MaoriReviewError,
    NotCoordinatorError,
    NotFlaggedError,
    ReviewValidationError,
    record_review,
    review_label,
    set_maori_content,
    visible_to_learners,
)
from models import lessons
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

# Review dates are checked against the club's local date, not the server's.
CLUB_TIMEZONE = ZoneInfo(os.getenv("CLUB_TIMEZONE", "Pacific/Auckland"))
NO_PERMISSION = "You do not have permission"


def club_today() -> date:
    """
    Return the current date in the configured club timezone.
    """
    return datetime.now(CLUB_TIMEZONE).date()


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


class MaoriContentIn(BaseModel):
    has_maori_content: bool


class ReviewIn(BaseModel):
    reviewer_name: str | None = None
    review_date: date | None = None


class ReviewOut(BaseModel):
    lesson_id: UUID
    has_maori_content: bool
    review_status: str
    reviewer_name: str | None
    review_date: date | None
    # "Māori content – not yet reviewed", "Reviewed by [name], [date]" or None.
    label: str | None
    visible_to_learners: bool


def review_out(lesson: dict[str, Any]) -> ReviewOut:
    """
    Project review metadata and learner visibility into the API response.
    """
    return ReviewOut(
        lesson_id=lesson["id"],
        has_maori_content=lesson["has_maori_content"],
        review_status=lesson["review_status"],
        reviewer_name=lesson.get("reviewer_name"),
        review_date=lesson.get("review_date"),
        label=review_label(lesson),
        visible_to_learners=visible_to_learners(lesson),
    )


def review_http_error(exc: MaoriReviewError) -> HTTPException:
    """Translate a review error into the HTTP response the website shows."""
    if isinstance(exc, LessonNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, NotCoordinatorError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ReviewValidationError):
        return HTTPException(status_code=422, detail={"errors": exc.errors})
    if isinstance(exc, NotFlaggedError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def find_lesson(db: Session, lesson_id: UUID) -> dict[str, Any]:
    """
    Load a live lesson for reading or changing its review metadata.
    """
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
        raise HTTPException(status_code=404, detail="Lesson not found")
    return dict(row)


def create_maori_review_router(
    session_factory: Callable[[], Session],
) -> APIRouter:
    """Build the router with the app's session factory (no import of app.py)."""
    router = APIRouter(tags=["US-008 Māori content review"])

    @router.get("/lessons/{lesson_id}/review", response_model=ReviewOut)
    def read_review(lesson_id: UUID, staff: LoggedInStaff) -> ReviewOut:
        """
        Handle GET /lessons/{lesson_id}/review for read review, applying the route’s
        validation and authorization rules.
        """
        with session_factory() as db:
            return review_out(find_lesson(db, lesson_id))

    @router.put("/lessons/{lesson_id}/maori-content", response_model=ReviewOut)
    def change_maori_content(
        lesson_id: UUID, payload: MaoriContentIn, staff: LoggedInStaff
    ) -> ReviewOut:
        # Same rule as editing a lesson (US-006): its author or a coordinator.
        """
        Handle PUT /lessons/{lesson_id}/maori-content for change maori content, applying
        the route’s validation and authorization rules.
        """
        try:
            with session_factory() as db, db.begin():
                lesson = find_lesson(db, lesson_id)
                if not staff.is_coordinator and lesson["created_by"] != staff.id:
                    raise HTTPException(status_code=403, detail=NO_PERMISSION)
                saved = set_maori_content(db, lesson_id, payload.has_maori_content)
                return review_out(saved)
        except MaoriReviewError as exc:
            raise review_http_error(exc) from exc

    @router.post("/lessons/{lesson_id}/review", response_model=ReviewOut)
    def add_review(
        lesson_id: UUID, payload: ReviewIn, staff: LoggedInStaff
    ) -> ReviewOut:
        """
        Handle POST /lessons/{lesson_id}/review for add review, applying the route’s
        validation and authorization rules.
        """
        try:
            with session_factory() as db, db.begin():
                saved = record_review(
                    db,
                    lesson_id,
                    reviewer_name=payload.reviewer_name,
                    review_date=payload.review_date,
                    recorded_by=staff.id,
                    recorder_role=staff.role,
                    today=club_today(),
                )
                return review_out(saved)
        except MaoriReviewError as exc:
            raise review_http_error(exc) from exc

    return router
