"""Provide minimal coordinator-only learner names for attendance reports.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from models import learners
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.orm import Session


class RosterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_ids: list[UUID]


class ReportLearner(BaseModel):
    id: UUID
    first_name: str
    family_name: str


def create_report_roster_router(
    factory: Callable[[], Session], coordinator: Callable
) -> APIRouter:
    router = APIRouter(tags=["Attendance reports"])

    @router.post("/reports/attendance/learners", response_model=list[ReportLearner])
    def roster(payload: RosterIn, user: Any = Depends(coordinator)):
        ids = set(payload.learner_ids)
        with factory() as db:
            rows = (
                db.execute(
                    select(learners.c.id, learners.c.first_name, learners.c.family_name)
                    .where(or_(learners.c.is_active.is_(True), learners.c.id.in_(ids)))
                    .order_by(
                        learners.c.family_name, learners.c.first_name, learners.c.id
                    )
                )
                .mappings()
                .all()
            )
        if ids - {row["id"] for row in rows}:
            raise HTTPException(409, "Learner records are unavailable")
        return rows

    return router
