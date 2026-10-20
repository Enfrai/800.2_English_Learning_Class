"""Implement user login, password verification, and database-backed sessions.

Author: Shuohui Liu
Date: 19 Oct 2026
"""

import hashlib
import hmac
import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    create_engine,
    delete,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    session_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000).hex()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Demo-only table creation and demo user seeding. Use migrations in production.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        username = os.getenv("DEMO_USERNAME", "demo")
        if not db.scalar(select(User).where(User.username == username)):
            salt = secrets.token_bytes(16)
            db.add(
                User(
                    username=username,
                    password_salt=salt.hex(),
                    password_hash=hash_password(
                        os.getenv("DEMO_PASSWORD", "DemoPass123!"), salt
                    ),
                )
            )
            try:
                db.commit()
            except IntegrityError:  # Two replicas may seed concurrently.
                db.rollback()
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
        user = db.scalar(select(User).where(User.username == payload.username))
        if user is None or not hmac.compare_digest(
            user.password_hash,
            hash_password(payload.password, bytes.fromhex(user.password_salt)),
        ):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        # Lock the user row to serialize concurrent logins across both replicas.
        # A successful new login invalidates all previously issued sessions.
        user = db.scalar(select(User).where(User.id == user.id).with_for_update())
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        session_id = secrets.token_urlsafe(32)
        expiry = datetime.now(UTC) + timedelta(hours=1)
        db.add(
            LoginSession(
                user_id=user.id,
                session_hash=hashlib.sha256(session_id.encode()).hexdigest(),
                expires_at=expiry,
            )
        )
        db.commit()
        return {
            "sessionid": session_id,
            "expires_at": expiry.isoformat(),
            "user_id": user.id,
            "instance": INSTANCE,
        }
