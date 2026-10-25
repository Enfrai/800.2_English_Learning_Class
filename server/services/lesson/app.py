"""Serve staff lesson management, Māori review and protected learner materials.

Author: Sandhya Tiwari
Date: 26 Oct 2026
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from lesson_api import create_lesson_router
from maori_review_api import create_maori_review_router
from schema import prepare_schema
from shared_materials import create_shared_router
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")


@asynccontextmanager
async def lifespan(app: FastAPI):
    prepare_schema(engine)
    yield


app = FastAPI(title="Lesson Service", lifespan=lifespan)
app.include_router(create_lesson_router(SessionLocal))
app.include_router(create_shared_router(SessionLocal))
app.include_router(create_maori_review_router(SessionLocal))


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
def health():
    return {"status": "ok", "instance": INSTANCE}
