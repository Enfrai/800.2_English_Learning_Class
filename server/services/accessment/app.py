"""Implement a demonstration permission-checking API.

Author: Shuohui Liu
Date: 19 Oct 2026
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import Boolean, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")


class Base(DeclarativeBase):
    pass


class Accessment(Base):
    __tablename__ = "accessment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
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
    # Test-only policy; this is NOT authorization tied to a logged-in user.
    with SessionLocal() as db:
        rule = db.scalar(
            select(Accessment).where(
                Accessment.role == payload.role, Accessment.resource == payload.resource
            )
        )
        if rule is None:
            rule = Accessment(
                role=payload.role,
                resource=payload.resource,
                allowed=(payload.role == "admin"),
            )
            db.add(rule)
            db.commit()
        return {
            "role": payload.role,
            "resource": payload.resource,
            "allowed": rule.allowed,
            "instance": INSTANCE,
        }
