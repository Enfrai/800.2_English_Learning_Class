"""Implement Ako login with UUID-backed SQLAlchemy tables.

Author: Shuohui Liu
Date: 19 Oct 2026
Updated: Sandhya Tiwari, 23-24 Oct 2026 (test teacher accounts for US-006;
replicas no longer race to create tables; sessions end after 30 idle
minutes and on log out)
"""

import hashlib
import hmac
import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Response
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
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")
# Any fixed number; it only has to be the same for every replica of this service.
STARTUP_LOCK_KEY = 800_2
ROUNDS = 600_000
# A session ends after this many minutes without activity (US-001).
SESSION_IDLE_MINUTES = 30


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


def seed_user(db, username: str, password: str, display_name: str, role: str) -> None:
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


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1)


@app.get("/health")
def health():
    return {"status": "ok", "instance": INSTANCE}


@app.post("/login")
def login(payload: LoginRequest):
    with SessionLocal() as db:
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
                raise HTTPException(
                    status_code=401, detail="Invalid username or password"
                )
            if row["locked_until"] and row["locked_until"] > now:
                raise HTTPException(
                    status_code=423, detail="Account temporarily locked"
                )
            if not verify_password(payload.password, row["password_hash"]):
                attempts = row["failed_login_attempts"] + 1
                db.execute(
                    users.update()
                    .where(users.c.id == row["id"])
                    .values(
                        failed_login_attempts=0 if attempts >= 5 else attempts,
                        locked_until=now + timedelta(minutes=10)
                        if attempts >= 5
                        else None,
                    )
                )
                # Commit failed-attempt tracking before raising.
                db.commit()
                raise HTTPException(
                    status_code=401, detail="Invalid username or password"
                )
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
            db.execute(
                delete(user_sessions).where(user_sessions.c.user_id == row["id"])
            )
            token = secrets.token_urlsafe(32)
            expires = now + timedelta(minutes=SESSION_IDLE_MINUTES)
            db.execute(
                user_sessions.insert().values(
                    user_id=row["id"],
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    expires_at=expires,
                    last_activity_at=now,
                )
            )
            return {
                "sessionid": token,
                "expires_at": expires.isoformat(),
                "user_id": str(row["id"]),
                "instance": INSTANCE,
            }


def session_token(authorization: str | None) -> str:
    """Return the sessionid from ``Authorization: Bearer <sessionid>``."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Login required")
    return token


def current_user_id(authorization: Annotated[str | None, Header()] = None) -> UUID:
    """Return the id of the user whose session is in the Authorization header.

    The header is ``Authorization: Bearer <sessionid>``, using the sessionid
    returned by ``/login``. Coordinators and teachers are both accepted.

    A session ends after SESSION_IDLE_MINUTES without activity (US-001), so
    each accepted request moves the end time forward.
    """
    token_hash = hashlib.sha256(session_token(authorization).encode()).hexdigest()
    now = datetime.now(UTC)
    with SessionLocal.begin() as db:
        user_id = db.execute(
            user_sessions.update()
            .where(
                user_sessions.c.token_hash == token_hash,
                user_sessions.c.revoked_at.is_(None),
                user_sessions.c.expires_at > now,
                user_sessions.c.user_id == users.c.id,
                users.c.is_active.is_(True),
            )
            .values(
                last_activity_at=now,
                expires_at=now + timedelta(minutes=SESSION_IDLE_MINUTES),
            )
            .returning(user_sessions.c.user_id)
        ).scalar_one_or_none()
    if user_id is None:
        raise HTTPException(status_code=401, detail="Login required")
    return user_id


CurrentUser = Annotated[UUID, Depends(current_user_id)]


class StaffOut(BaseModel):
    id: UUID
    display_name: str
    role: str


@app.get("/me", response_model=StaffOut)
def read_me(user_id: CurrentUser):
    """Return the logged-in user. Other services call this to check a session."""
    with SessionLocal() as db:
        return (
            db.execute(
                select(users.c.id, users.c.display_name, users.c.role).where(
                    users.c.id == user_id
                )
            )
            .mappings()
            .one()
        )


@app.post("/logout", status_code=204)
def logout(authorization: Annotated[str | None, Header()] = None):
    """End the session on the server, so its sessionid no longer works."""
    token_hash = hashlib.sha256(session_token(authorization).encode()).hexdigest()
    with SessionLocal.begin() as db:
        db.execute(
            user_sessions.update()
            .where(
                user_sessions.c.token_hash == token_hash,
                user_sessions.c.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
    return Response(status_code=204)


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
def create_learner(payload: LearnerIn, user_id: CurrentUser):
    try:
        with SessionLocal.begin() as db:
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
def read_learners(user_id: CurrentUser, search: str | None = None):
    with SessionLocal() as db:
        return list_learners(db, search)


@app.get("/learners/{learner_id}", response_model=LearnerOut)
def read_learner(learner_id: UUID, user_id: CurrentUser):
    try:
        with SessionLocal() as db:
            return get_learner(db, learner_id)
    except LearnerError as exc:
        raise learner_http_error(exc) from exc


@app.put("/learners/{learner_id}", response_model=LearnerOut)
def change_learner(learner_id: UUID, payload: LearnerIn, user_id: CurrentUser):
    try:
        with SessionLocal.begin() as db:
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
