"""Serve attendance, QR sign-in and protected learner material access.

Author: Sandhya Tiwari
Date: 26 Oct 2026
"""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
from checkin import (
    CHECKIN_CLOSED,
    NAME_NOT_FOUND,
    SIGNED_IN,
    TOO_MANY_TRIES,
    CheckinUnavailableError,
    OpenCheckin,
    blocked_until,
    find_open_checkin,
    record_wrong_name,
    sign_in,
    wrong_name_limits,
)
from corrections import (
    CorrectionError,
    NotCoordinatorError,
    SessionNotPastError,
    change_history,
    correct_attendance,
    corrected_learners,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from learner_materials import create_materials_router, issue_grant
from models import Base, class_sessions
from pydantic import BaseModel
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")
# Attendance rules use the club's local date, not the server's UTC date.
CLUB_TIMEZONE = ZoneInfo(os.getenv("CLUB_TIMEZONE", "Pacific/Auckland"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(800013)"))
        Base.metadata.create_all(bind=connection)
    yield


app = FastAPI(title="Accessment Service", lifespan=lifespan)


@app.middleware("http")
async def learner_private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/learner/", "/checkin/")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response



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
app.include_router(create_materials_router(lambda: SessionLocal(), LoggedInStaff))


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
    # Learners whose attendance was corrected later (US-015), present or not.
    corrected_learner_ids: list[UUID]


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
            "corrected_learner_ids": corrected_learners(db, session_id),
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


# QR sign-in for learners (US-012). Public: learners have no login.
# Author: Pei Wu, 25 Oct 2026.


class CheckinOut(BaseModel):
    session_date: date


class SignInIn(BaseModel):
    first_name: str | None = None
    family_name: str | None = None


class SignInOut(BaseModel):
    message: str
    session_date: date


def open_checkin(token: str, now: datetime) -> OpenCheckin:
    """Return the open check-in for a token, or the "closed" answer (AC5)."""
    try:
        with SessionLocal() as db:
            return find_open_checkin(db, token, now=now, today=club_today())
    except CheckinUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/checkin/{token}", response_model=CheckinOut)
def read_checkin(token: str):
    """Tell the sign-in page which class this is (AC1)."""
    return {"session_date": open_checkin(token, datetime.now(UTC)).session_date}


@app.post("/checkin/{token}/sign-in", response_model=SignInOut, status_code=201)
def learner_sign_in(
    token: str,
    payload: SignInIn,
    response: Response,
    x_real_ip: Annotated[str | None, Header()] = None,
    x_device_id: Annotated[str | None, Header()] = None,
):
    """Sign a learner in by the name they type (AC2 to AC5, NFR-11)."""
    now = datetime.now(UTC)
    checkin = open_checkin(token, now)
    # Nginx sets X-Real-IP; the sign-in page sends a random X-Device-Id.
    # Only keyed hashes of them are stored, briefly.
    limits = wrong_name_limits(x_real_ip, x_device_id, user_client.INTERNAL_API_KEY)
    with SessionLocal() as db:
        if any(blocked_until(db, key, now, limit) for key, limit in limits):
            raise HTTPException(status_code=429, detail=TOO_MANY_TRIES)
    try:
        learner = user_client.find_learner_for_sign_in(
            payload.first_name or "", payload.family_name or ""
        )
    except user_client.SignInNameNotFoundError as exc:
        with SessionLocal.begin() as db:
            for key, _ in limits:
                record_wrong_name(db, key, now)
        raise HTTPException(status_code=404, detail=NAME_NOT_FOUND) from exc
    except user_client.AmbiguousSignInNameError as exc:
        # A real name shared by several learners: not a guess, so not counted.
        raise HTTPException(status_code=404, detail=NAME_NOT_FOUND) from exc
    except user_client.UserServiceError as exc:
        raise HTTPException(status_code=503, detail="User service unavailable") from exc
    try:
        with SessionLocal.begin() as db:
            sign_in(db, checkin, UUID(learner["id"]), club_today())
            issue_grant(db, checkin.session_id, response, secure=os.getenv("COOKIE_SECURE", "false").lower() == "true")
    except AlreadySignedInError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AttendanceError as exc:
        # The class ended between the check above and now.
        raise HTTPException(status_code=404, detail=CHECKIN_CLOSED) from exc
    return {"message": SIGNED_IN, "session_date": checkin.session_date}


# Correcting a past class (US-015). Coordinators only.
# Author: Pei Wu, 25 Oct 2026.


class CorrectionIn(BaseModel):
    learner_id: UUID
    present: bool
    reason: str | None = None


class CorrectionOut(BaseModel):
    learner_id: UUID
    learner_name: str | None
    old_status: str
    new_status: str
    corrected_by: UUID
    corrected_by_name: str | None
    reason: str | None
    created_at: datetime


def require_coordinator(request: StaffRequest) -> None:
    # Checked before any lookup, so a teacher learns nothing about the class.
    if request.staff.role != "coordinator":
        raise HTTPException(status_code=403, detail=str(NotCoordinatorError()))


def correction_http_error(exc: CorrectionError) -> HTTPException:
    if isinstance(exc, NotCoordinatorError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, SessionNotPastError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.post("/sessions/{session_id}/corrections", response_model=AttendanceChange)
def correct_learner(session_id: UUID, payload: CorrectionIn, request: LoggedInStaff):
    """Mark a learner present or not present at a past class (AC1, AC2)."""
    require_coordinator(request)
    try:
        if not user_client.learner_exists(request.authorization, payload.learner_id):
            raise HTTPException(status_code=404, detail="Learner not found")
    except USER_SERVICE_ERRORS as exc:
        raise user_service_http_error(exc) from exc
    try:
        with SessionLocal.begin() as db:
            record = correct_attendance(
                db,
                session_id=session_id,
                learner_id=payload.learner_id,
                present=payload.present,
                corrected_by=request.staff.id,
                corrector_role=request.staff.role,
                today=club_today(),
                reason=payload.reason,
            )
            return {
                "attendance": record,
                "present_count": present_count(db, session_id),
            }
    except CorrectionError as exc:
        raise correction_http_error(exc) from exc
    except AttendanceError as exc:
        raise attendance_http_error(exc) from exc


@app.get("/sessions/{session_id}/corrections", response_model=list[CorrectionOut])
def read_corrections(session_id: UUID, request: LoggedInStaff):
    """The change history of a class, oldest first, with names (AC4)."""
    require_coordinator(request)
    try:
        with SessionLocal() as db:
            history = change_history(db, session_id)
    except AttendanceError as exc:
        raise attendance_http_error(exc) from exc
    if not history:
        return []
    try:
        staff = user_client.staff_names(request.authorization)
        learners = user_client.learner_names(
            request.authorization, {entry["learner_id"] for entry in history}
        )
    except USER_SERVICE_ERRORS as exc:
        raise user_service_http_error(exc) from exc
    return [
        {
            **entry,
            "learner_name": learners.get(entry["learner_id"]),
            "corrected_by_name": staff.get(entry["corrected_by"]),
        }
        for entry in history
    ]

