"""Implement the demo permission check with the Ako database schema.

Author: Shuohui Liu
Date: 19 Oct 2026
Updated: Sandhya Tiwari, 23 Oct 2026 (replicas no longer race to create tables)
"""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

import user_client
from attendance import (
    AlreadySignedInError,
    AttendanceError,
    NotMarkedPresentError,
    PastSessionError,
    SessionNotFoundError,
    check_session_is_running,
    mark_present,
    present_count,
    present_records,
    unmark,
)
from fastapi import Depends, FastAPI, Header, HTTPException
from models import Base, class_sessions
from pydantic import BaseModel
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")
# Any fixed number; it only has to be the same for every replica of this service.
STARTUP_LOCK_KEY = 800_2
# Attendance rules use the club's local date, not the server's UTC date.
CLUB_TIMEZONE = ZoneInfo(os.getenv("CLUB_TIMEZONE", "Pacific/Auckland"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Both replicas start at the same time. Without this lock they can both try
    # to create the tables on a new database, and one fails to start.
    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": STARTUP_LOCK_KEY}
        )
        Base.metadata.create_all(bind=connection)
    yield


app = FastAPI(title="Accessment Service", lifespan=lifespan)


class CheckRequest(BaseModel):
    role: str
    resource: str


@app.get("/health")
def health():
    return {"status": "ok", "instance": INSTANCE}


@app.post("/check")
def check(payload: CheckRequest):
    # Demo-only policy: this is NOT authenticated authorization.
    return {
        "role": payload.role,
        "resource": payload.resource,
        "allowed": payload.role == "admin",
        "instance": INSTANCE,
    }


# Attendance in class (US-004). Author: Pei Wu, 23 Oct 2026.


def club_today() -> date:
    return datetime.now(CLUB_TIMEZONE).date()


@dataclass(frozen=True)
class StaffRequest:
    staff: user_client.Staff
    authorization: str


def staff_request(
    authorization: Annotated[str | None, Header()] = None,
) -> StaffRequest:
    """Check the session with the User Service. Teachers and coordinators pass."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Login required")
    try:
        staff = user_client.current_staff(authorization)
    except user_client.LoginRequiredError as exc:
        raise HTTPException(status_code=401, detail="Login required") from exc
    except user_client.UserServiceError as exc:
        raise HTTPException(status_code=503, detail="User service unavailable") from exc
    return StaffRequest(staff, authorization)


LoggedInStaff = Annotated[StaffRequest, Depends(staff_request)]


class AttendanceOut(BaseModel):
    learner_id: UUID
    status: str
    recorded_by: UUID
    recorded_at: datetime


class AttendanceList(BaseModel):
    session_date: date
    # False for a session before today: only a coordinator can correct it.
    editable: bool
    present_count: int
    records: list[AttendanceOut]


class AttendanceChange(BaseModel):
    present_count: int
    attendance: AttendanceOut | None = None


class MarkPresentIn(BaseModel):
    learner_id: UUID


class NewLearnerIn(BaseModel):
    """Details for "Add and mark present". The User Service checks the rules."""

    first_name: str | None = None
    family_name: str | None = None
    first_language: str | None = None
    contact: str | None = None


class LearnerOut(BaseModel):
    id: UUID
    first_name: str
    family_name: str
    first_language: str | None
    contact: str | None


class AddAndMarkOut(AttendanceChange):
    learner: LearnerOut
    learner_added: bool


def attendance_http_error(exc: AttendanceError) -> HTTPException:
    """Translate an attendance error into the HTTP response the website shows."""
    if isinstance(exc, SessionNotFoundError | NotMarkedPresentError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PastSessionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, AlreadySignedInError):
        record = AttendanceOut.model_validate(exc.record).model_dump(mode="json")
        return HTTPException(
            status_code=409, detail={"message": str(exc), "attendance": record}
        )
    return HTTPException(status_code=400, detail=str(exc))


def user_service_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, user_client.LoginRequiredError):
        return HTTPException(status_code=401, detail="Login required")
    if isinstance(exc, user_client.LearnerFieldError):
        return HTTPException(
            status_code=422, detail={"field": exc.field, "message": exc.message}
        )
    return HTTPException(status_code=503, detail="User service unavailable")


USER_SERVICE_ERRORS = (
    user_client.LoginRequiredError,
    user_client.LearnerFieldError,
    user_client.UserServiceError,
)


@app.get("/sessions/{session_id}/attendance", response_model=AttendanceList)
def read_attendance(session_id: UUID, request: LoggedInStaff):
    with SessionLocal() as db:
        session_date = db.execute(
            select(class_sessions.c.session_date).where(
                class_sessions.c.id == session_id
            )
        ).scalar_one_or_none()
        if session_date is None:
            raise HTTPException(status_code=404, detail="Class session not found")
        return {
            "session_date": session_date,
            "editable": session_date >= club_today(),
            "present_count": present_count(db, session_id),
            "records": present_records(db, session_id),
        }


@app.post(
    "/sessions/{session_id}/attendance",
    response_model=AttendanceChange,
    status_code=201,
)
def tick_learner(session_id: UUID, payload: MarkPresentIn, request: LoggedInStaff):
    try:
        if not user_client.learner_exists(request.authorization, payload.learner_id):
            raise HTTPException(status_code=404, detail="Learner not found")
    except USER_SERVICE_ERRORS as exc:
        raise user_service_http_error(exc) from exc
    try:
        with SessionLocal.begin() as db:
            record = mark_present(
                db,
                session_id=session_id,
                learner_id=payload.learner_id,
                recorded_by=request.staff.id,
                today=club_today(),
            )
            return {
                "attendance": record,
                "present_count": present_count(db, session_id),
            }
    except AttendanceError as exc:
        raise attendance_http_error(exc) from exc


@app.delete(
    "/sessions/{session_id}/attendance/{learner_id}", response_model=AttendanceChange
)
def untick_learner(session_id: UUID, learner_id: UUID, request: LoggedInStaff):
    try:
        with SessionLocal.begin() as db:
            unmark(db, session_id=session_id, learner_id=learner_id, today=club_today())
            return {"present_count": present_count(db, session_id)}
    except AttendanceError as exc:
        raise attendance_http_error(exc) from exc


@app.post(
    "/sessions/{session_id}/attendance/new-learner",
    response_model=AddAndMarkOut,
    status_code=201,
)
def add_and_mark_present(
    session_id: UUID, payload: NewLearnerIn, request: LoggedInStaff
):
    """Add a learner who is not on the list and mark them present (US-004 AC2).

    If a learner with the same name exists, that learner is used (UT-29).
    """
    today = club_today()
    try:
        # Check first, so a learner is not added for a session that is locked.
        with SessionLocal() as db:
            check_session_is_running(db, session_id, today)
    except AttendanceError as exc:
        raise attendance_http_error(exc) from exc
    try:
        learner, added = user_client.add_or_find_learner(
            request.authorization, payload.model_dump()
        )
    except USER_SERVICE_ERRORS as exc:
        raise user_service_http_error(exc) from exc
    try:
        with SessionLocal.begin() as db:
            record = mark_present(
                db,
                session_id=session_id,
                learner_id=UUID(learner["id"]),
                recorded_by=request.staff.id,
                today=today,
            )
            return {
                "learner": learner,
                "learner_added": added,
                "attendance": record,
                "present_count": present_count(db, session_id),
            }
    except AttendanceError as exc:
        raise attendance_http_error(exc) from exc
