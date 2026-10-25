"""Implement Ako login with UUID-backed SQLAlchemy tables.

Author: Shuohui Liu
Date: 19 Oct 2026
"""

import hashlib
import hmac
import logging
import math
import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.base import RequestResponseEndpoint

from auth import (
    AuthenticatedUser,
    get_current_user,
    get_db,
    get_session_token,
    require_coordinator,
    unauthenticated,
)
from learner_import import router as learner_import_router
from learners import (
    DuplicateLearnerError,
    LearnerError,
    LearnerNotFoundError,
    LearnerValidationError,
    add_learner,
    get_learner,
    list_learners,
    update_learner,
)
from models import Base, user_sessions, users
from security import (
    SessionSecurity,
    clear_session_cookie,
    protect_login,
    set_session_cookie,
)
from staff import create_staff_router

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")
STARTUP_LOCK_KEY = 800_2
ROUNDS = 600_000
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=10)
SESSION_DURATION = timedelta(minutes=30)
INVALID_CREDENTIALS = "Username or password is incorrect"
AUTH_PATHS = frozenset(
    {"/login", "/session", "/logout", "/activity", "/account-management/access", "/me"}
)


def password_hash(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ROUNDS).hex()
    return f"pbkdf2_sha256${ROUNDS}${salt.hex()}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, digest = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(rounds) != ROUNDS:
            return False
        actual = password_hash(password, bytes.fromhex(salt)).split("$")[-1]
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False


def seed_user(
    db: Session, username: str, password: str, display_name: str, role: str
) -> None:
    """Add a starting account once. Existing accounts are never changed."""
    if db.execute(select(users.c.id).where(users.c.username == username)).first():
        return
    salt = secrets.token_bytes(16)
    try:
        with db.begin_nested():
            db.execute(
                users.insert().values(
                    username=username,
                    password_hash=password_hash(password, salt),
                    display_name=display_name,
                    role=role,
                )
            )
    except IntegrityError:
        # Another replica may have seeded the same username.
        pass


# Test teacher accounts for US-006 until US-001 adds teacher accounts.
# Two are needed to test that a teacher cannot change another's lesson.
TEST_TEACHERS = (("teacher1", "Test Teacher One"), ("teacher2", "Test Teacher Two"))


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
        seed_user(
            db,
            os.getenv("DEMO_USERNAME", "demo"),
            os.getenv("DEMO_PASSWORD", "DemoPass123!"),
            "Demo Coordinator",
            "coordinator",
        )
        teacher_password = os.getenv("TEST_TEACHER_PASSWORD", "")
        # Leave the variable empty to start without test teachers.
        if teacher_password:
            for username, display_name in TEST_TEACHERS:
                seed_user(db, username, teacher_password, display_name, "teacher")
    yield


app = FastAPI(title="User Service", lifespan=lifespan)
app.state.session_factory = SessionLocal
app.state.session_security = SessionSecurity.from_environment()
app.include_router(create_staff_router(password_hash))
app.include_router(learner_import_router)


@app.middleware("http")
async def authentication_cache_control(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    response = await call_next(request)
    if (
        request.url.path in AUTH_PATHS
        or request.url.path == "/learners/import"
        or request.url.path == "/staff"
        or request.url.path.startswith("/staff/")
    ):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    sessionid: str
    expires_at: datetime
    user_id: UUID
    instance: str
    role: Literal["teacher", "coordinator"]
    display_name: str


def locked_response(locked_until: datetime, now: datetime) -> HTTPException:
    retry_after = max(1, math.ceil((locked_until - now).total_seconds()))
    return HTTPException(
        status_code=423,
        detail={
            "code": "account_locked",
            "message": "Account temporarily locked. Please try again at "
            f"{locked_until.isoformat()}.",
            "locked_until": locked_until.isoformat(),
            "retry_after_seconds": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )


@app.get("/health")
def health():
    return {"status": "ok", "instance": INSTANCE}


@app.post("/login", response_model=LoginResponse, dependencies=[Depends(protect_login)])
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    with db.begin():
        row = (
            db.execute(
                select(users)
                .where(users.c.username == payload.username)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        now = datetime.now(UTC)
        if row is None or not row["is_active"]:
            raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)
        if row["locked_until"] and row["locked_until"] > now:
            raise locked_response(row["locked_until"], now)
        if not verify_password(payload.password, row["password_hash"]):
            attempts = row["failed_login_attempts"] + 1
            locked_until = (
                now + LOCKOUT_DURATION if attempts >= MAX_LOGIN_ATTEMPTS else None
            )
            db.execute(
                users.update()
                .where(users.c.id == row["id"])
                .values(
                    failed_login_attempts=0 if locked_until else attempts,
                    locked_until=locked_until,
                )
            )
            # Commit failed-attempt tracking before raising.
            db.commit()
            if locked_until:
                raise locked_response(locked_until, now)
            raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)
        db.execute(
            users.update()
            .where(users.c.id == row["id"])
            .values(
                failed_login_attempts=0,
                locked_until=None,
                last_login_at=now,
                updated_at=now,
            )
        )
        # The partial unique index permits only one unrevoked session per user.
        db.execute(delete(user_sessions).where(user_sessions.c.user_id == row["id"]))
        token = secrets.token_urlsafe(32)
        expires = now + SESSION_DURATION
        db.execute(
            user_sessions.insert().values(
                user_id=row["id"],
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=expires,
                last_activity_at=now,
            )
        )
        result = LoginResponse(
            sessionid=token,
            expires_at=expires,
            user_id=row["id"],
            instance=INSTANCE,
            role=row["role"],
            display_name=row["display_name"],
        )

    set_session_cookie(request, response, token)
    return result


class SessionResponse(BaseModel):
    user_id: UUID
    display_name: str
    role: str


@app.get("/session", response_model=SessionResponse)
def current_session(
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> SessionResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Session-Expires-At"] = user.expires_at.isoformat()
    return SessionResponse(
        user_id=user.user_id, display_name=user.display_name, role=user.role
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Do not include SQL parameters, credentials or tokens in the response/log entry.
    logging.getLogger(__name__).error(
        "User service request failed: %s", type(exc).__name__
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def lock_active_session(db: Session, token: str) -> tuple[UUID, datetime]:
    """Lock user then session, matching login's order; check time after waiting.

    The caller owns the transaction. Neither this function nor the credential
    dependency opens a second transaction or refreshes any field implicitly.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user_id = db.execute(
        select(user_sessions.c.user_id).where(user_sessions.c.token_hash == token_hash)
    ).scalar_one_or_none()
    if user_id is None:
        raise unauthenticated()
    active = db.execute(
        select(users.c.is_active).where(users.c.id == user_id).with_for_update()
    ).scalar_one_or_none()
    row = (
        db.execute(
            select(user_sessions)
            .where(
                user_sessions.c.token_hash == token_hash,
                user_sessions.c.user_id == user_id,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    now = datetime.now(UTC)
    if (
        not active
        or row is None
        or row["revoked_at"] is not None
        or row["expires_at"] <= now
        or row["last_activity_at"] <= now - SESSION_DURATION
    ):
        raise unauthenticated()
    return row["id"], now


@app.post("/logout", status_code=204)
def logout(
    request: Request,
    token: Annotated[str, Depends(get_session_token)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        with db.begin():
            session_id, now = lock_active_session(db, token)
            db.execute(
                user_sessions.update()
                .where(user_sessions.c.id == session_id)
                .values(revoked_at=now)
            )
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
        # Credential selection and Origin protection already succeeded. Also clear
        # an expired cookie, but never clear one in response to a CSRF rejection.
        result = JSONResponse(
            status_code=401, content={"detail": exc.detail}, headers=exc.headers
        )
    else:
        result = Response(status_code=204)
    clear_session_cookie(request, result)
    return result


class ActivityResponse(BaseModel):
    expires_at: datetime


@app.post("/activity", response_model=ActivityResponse)
def activity(
    request: Request,
    response: Response,
    token: Annotated[str, Depends(get_session_token)],
    db: Annotated[Session, Depends(get_db)],
) -> ActivityResponse:
    with db.begin():
        session_id, now = lock_active_session(db, token)
        expires = now + SESSION_DURATION
        db.execute(
            user_sessions.update()
            .where(user_sessions.c.id == session_id)
            .values(
                last_activity_at=now,
                expires_at=expires,
            )
        )
    set_session_cookie(request, response, token)
    return ActivityResponse(expires_at=expires)


@app.get("/account-management/access")
def account_management_access(
    user: Annotated[AuthenticatedUser, Depends(require_coordinator)],
) -> dict[str, bool]:
    """Authorization boundary only; no account queries or CRUD are implemented."""
    return {"allowed": True}


# Preserve dev's UUID dependency and /me contract while sharing US-001 validation.
def current_user_id(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> UUID:
    return user.user_id


CurrentUser = Annotated[UUID, Depends(current_user_id)]


class StaffOut(BaseModel):
    id: UUID
    display_name: str
    role: str


@app.get("/me", response_model=StaffOut)
def read_me(user: Annotated[AuthenticatedUser, Depends(get_current_user)]) -> StaffOut:
    """Keep the cross-service identity contract; session reads never extend expiry."""
    return StaffOut(id=user.user_id, display_name=user.display_name, role=user.role)


class LearnerIn(BaseModel):
    """Learner details. Rules are checked in learners.py so messages match US-003."""

    first_name: str | None = None
    family_name: str | None = None
    contact: str | None = None
    first_language: str | None = None
    allow_duplicate: bool = False


class LearnerOut(BaseModel):
    id: UUID
    first_name: str
    family_name: str
    contact: str | None
    first_language: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


def learner_http_error(exc: LearnerError) -> HTTPException:
    """Translate a learner error into the HTTP response the website shows."""
    if isinstance(exc, LearnerNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, DuplicateLearnerError):
        duplicates = [
            LearnerOut.model_validate(row).model_dump(mode="json")
            for row in exc.duplicates
        ]
        return HTTPException(
            status_code=409, detail={"message": str(exc), "duplicates": duplicates}
        )
    if isinstance(exc, LearnerValidationError):
        return HTTPException(
            status_code=422, detail={"field": exc.field, "message": exc.message}
        )
    return HTTPException(status_code=400, detail=str(exc))


@app.post("/learners", response_model=LearnerOut, status_code=201)
def create_learner(payload: LearnerIn, user_id: CurrentUser, request: Request) -> dict:
    try:
        with request.app.state.session_factory.begin() as db:
            return add_learner(
                db,
                first_name=payload.first_name,
                family_name=payload.family_name,
                contact=payload.contact,
                first_language=payload.first_language,
                allow_duplicate=payload.allow_duplicate,
                created_by=user_id,
            )
    except LearnerError as exc:
        raise learner_http_error(exc) from exc


@app.get("/learners", response_model=list[LearnerOut])
def read_learners(user_id: CurrentUser, request: Request, search: str | None = None):
    with request.app.state.session_factory() as db:
        return list_learners(db, search)


@app.get("/learners/{learner_id}", response_model=LearnerOut)
def read_learner(learner_id: UUID, user_id: CurrentUser, request: Request):
    try:
        with request.app.state.session_factory() as db:
            return get_learner(db, learner_id)
    except LearnerError as exc:
        raise learner_http_error(exc) from exc


@app.put("/learners/{learner_id}", response_model=LearnerOut)
def change_learner(
    learner_id: UUID, payload: LearnerIn, user_id: CurrentUser, request: Request
):
    try:
        with request.app.state.session_factory.begin() as db:
            return update_learner(
                db,
                learner_id,
                first_name=payload.first_name,
                family_name=payload.family_name,
                contact=payload.contact,
                first_language=payload.first_language,
                allow_duplicate=payload.allow_duplicate,
                updated_by=user_id,
            )
    except LearnerError as exc:
        raise learner_http_error(exc) from exc
