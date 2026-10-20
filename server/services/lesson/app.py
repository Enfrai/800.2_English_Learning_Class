"""Implement lesson creation and persistence in PostgreSQL.

Author: Shuohui Liu
Date: 19 Oct 2026
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")


class Base(DeclarativeBase):
    pass


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Lesson Service", lifespan=lifespan)


class CreateLessonRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@app.get("/health")
def health():
    return {"status": "ok", "instance": INSTANCE}


@app.post("/create", status_code=201)
def create(payload: CreateLessonRequest):
    with SessionLocal() as db:
        lesson = Lesson(title=payload.title)
        db.add(lesson)
        db.commit()
        db.refresh(lesson)
        return {"lesson_id": lesson.id, "title": lesson.title, "instance": INSTANCE}
