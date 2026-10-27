"""Read one learner's dated attendance history with inclusive date filtering.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import user_client
from fastapi import APIRouter, Depends, HTTPException, Response
from models import attendance_records, class_sessions
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session


class HistoryLearnerError(Exception):
    """The learner response could not be trusted."""


def history_learner(authorization: str, learner_id: UUID, timezone: ZoneInfo) -> dict:
    """
    Fetch and validate the learner identity and club-local registration date.
    """
    status, body = user_client._request("GET", f"/learners/{learner_id}", authorization)
    if status == 401:
        raise HTTPException(401, "Login required")
    if status == 404:
        raise HTTPException(404, "Learner not found")
    if status != 200 or not isinstance(body, dict):
        raise HistoryLearnerError()
    try:
        first, family = body["first_name"], body["family_name"]
        created = datetime.fromisoformat(body["created_at"].replace("Z", "+00:00"))
        if UUID(body["id"]) != learner_id or created.tzinfo is None:
            raise ValueError("Invalid learner")
        if not all(
            isinstance(value, str) and value.strip() for value in (first, family)
        ):
            raise ValueError("Invalid name")
        return {
            "id": learner_id,
            "name": f"{first} {family}",
            "created_date": created.astimezone(timezone).date(),
        }
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HistoryLearnerError() from exc


def collect_history(
    factory: Callable[[], Session],
    learner: dict,
    today: date,
    start: date | None,
    end: date | None,
) -> dict:
    # Keep explicit historical records even if a learner was imported later.
    """
    Collect dated attendance since learner registration, with inclusive date filtering.
    """
    with factory() as db:
        rows = (
            db.execute(
                select(
                    class_sessions.c.id,
                    class_sessions.c.session_date,
                    attendance_records.c.status,
                )
                .select_from(
                    class_sessions.outerjoin(
                        attendance_records,
                        and_(
                            attendance_records.c.session_id == class_sessions.c.id,
                            attendance_records.c.learner_id == learner["id"],
                        ),
                    )
                )
                .where(
                    or_(
                        class_sessions.c.session_date < today,
                        and_(
                            class_sessions.c.session_date == today,
                            class_sessions.c.status == "closed",
                        ),
                    )
                )
                .where(
                    or_(
                        class_sessions.c.session_date >= learner["created_date"],
                        attendance_records.c.id.is_not(None),
                    )
                )
                .order_by(
                    class_sessions.c.session_date.desc(), class_sessions.c.id.desc()
                )
            )
            .mappings()
            .all()
        )
    has_records = any(row["status"] is not None for row in rows)
    sessions = [
        {
            "session_id": row["id"],
            "session_date": row["session_date"],
            "status": "Present" if row["status"] == "present" else "Absent",
        }
        for row in rows
        if has_records
        and (start is None or row["session_date"] >= start)
        and (end is None or row["session_date"] <= end)
    ]
    return {
        "learner": {"id": learner["id"], "name": learner["name"]},
        "sessions": sessions,
        "present_count": sum(row["status"] == "Present" for row in sessions),
        "total_count": len(sessions),
        "has_records": has_records,
        "start_date": start,
        "end_date": end,
    }


def create_history_router(
    factory: Callable[[], Session],
    staff_dependency: Callable,
    today: Callable[[], date],
    timezone: ZoneInfo,
) -> APIRouter:
    """
    Build the history API router with its injected dependencies.
    """
    router = APIRouter(tags=["US-016 learner attendance history"])

    @router.get("/learners/{learner_id}/attendance-history")
    def read_history(
        learner_id: UUID,
        response: Response,
        start_date: date | None = None,
        end_date: date | None = None,
        request: Any = Depends(staff_dependency),
    ):
        """
        Handle GET /learners/{learner_id}/attendance-history for read history, applying
        the route’s validation and authorization rules.
        """
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.staff.role not in {"teacher", "coordinator"}:
            raise HTTPException(403, "You do not have permission")
        if start_date and end_date and start_date > end_date:
            raise HTTPException(
                422,
                {"field": "end_date", "message": "Start date must be before end date"},
            )
        try:
            learner = history_learner(request.authorization, learner_id, timezone)
        except (user_client.UserServiceError, HistoryLearnerError) as exc:
            raise HTTPException(
                503, "Learner information is unavailable. Please try again."
            ) from exc
        return collect_history(factory, learner, today(), start_date, end_date)

    return router
