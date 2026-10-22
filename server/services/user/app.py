"""Implement Ako login with UUID-backed SQLAlchemy tables.

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
from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from models import Base, user_sessions, users

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")
ROUNDS = 600_000


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    username = os.getenv("DEMO_USERNAME", "demo")
    with SessionLocal.begin() as db:
        if db.execute(select(users.c.id).where(users.c.username == username)).first() is None:
            salt = secrets.token_bytes(16)
            try:
                with db.begin_nested():
                    db.execute(users.insert().values(
                        username=username,
                        password_hash=password_hash(os.getenv("DEMO_PASSWORD", "DemoPass123!"), salt),
                        display_name="Demo Coordinator",
                        role="coordinator",
                    ))
            except IntegrityError:
                # Another replica may have seeded the same username.
                pass
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
            row = db.execute(
                select(users).where(users.c.username == payload.username).with_for_update()
            ).mappings().first()
            now = datetime.now(UTC)
            if row is None or not row["is_active"]:
                raise HTTPException(status_code=401, detail="Invalid username or password")
            if row["locked_until"] and row["locked_until"] > now:
                raise HTTPException(status_code=423, detail="Account temporarily locked")
            if not verify_password(payload.password, row["password_hash"]):
                attempts = row["failed_login_attempts"] + 1
                db.execute(users.update().where(users.c.id == row["id"]).values(
                    failed_login_attempts=0 if attempts >= 5 else attempts,
                    locked_until=now + timedelta(minutes=10) if attempts >= 5 else None,
                ))
                # Commit failed-attempt tracking before raising.
                db.commit()
                raise HTTPException(status_code=401, detail="Invalid username or password")
            db.execute(users.update().where(users.c.id == row["id"]).values(
                failed_login_attempts=0, locked_until=None, last_login_at=now, updated_at=now
            ))
            # The partial unique index permits only one unrevoked session per user.
            db.execute(delete(user_sessions).where(user_sessions.c.user_id == row["id"]))
            token = secrets.token_urlsafe(32)
            expires = now + timedelta(minutes=30)
            db.execute(user_sessions.insert().values(
                user_id=row["id"], token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=expires, last_activity_at=now
            ))
            return {"sessionid": token, "expires_at": expires.isoformat(),
                    "user_id": str(row["id"]), "instance": INSTANCE}
