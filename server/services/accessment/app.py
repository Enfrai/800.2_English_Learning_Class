"""Implement the demo permission check with the Ako database schema.

Author: Shuohui Liu
Date: 19 Oct 2026
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from models import Base
from pydantic import BaseModel
from sqlalchemy import create_engine

engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
INSTANCE = os.getenv("INSTANCE_NAME", "unknown")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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
