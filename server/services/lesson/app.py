"""Create Ako lessons with UUID keys using SQLAlchemy Core.

Author: Shuohui Liu
Date: 19 Oct 2026
"""
import os
from contextlib import asynccontextmanager
from datetime import date
from uuid import UUID

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, lessons

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Lesson Service", lifespan=lifespan)


class CreateLessonRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    lesson_date: date = Field(default_factory=date.today)
    created_by: UUID


@app.get("/health")
def health():
    return {"status": "ok", "instance": INSTANCE}


@app.post("/create", status_code=201)
def create(payload: CreateLessonRequest):
    with SessionLocal.begin() as db:
        row = db.execute(
            lessons.insert().values(
                title=payload.title, lesson_date=payload.lesson_date,
                created_by=payload.created_by
            ).returning(lessons.c.id, lessons.c.title)
        ).one()
        return {"lesson_id": str(row.id), "title": row.title, "instance": INSTANCE}
