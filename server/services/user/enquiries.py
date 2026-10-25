"""Public US-010 submissions; enquiries never create learner or user accounts."""

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_db, require_coordinator
from models import public_enquiries

SUCCESS_MESSAGE = "Thank you, the club will contact you"
EMAIL_ERROR = "Please enter a valid email address"
MESSAGE_ERROR = "Message must be 500 characters or fewer"
CONSENT_ERROR = "Please consent to being contacted by the club"


class EnquiryIn(BaseModel):
    """Only public input is accepted; clients cannot set status, UUID or date."""

    model_config = ConfigDict(extra="forbid")
    name: str
    contact_type: Literal["email", "phone"]
    contact: str
    message: str | None = None
    consent: StrictBool


class EnquiryOut(BaseModel):
    message: str


def validated_values(payload: EnquiryIn) -> dict[str, str | None]:
    """Validate before opening a transaction; preserve message character counts."""
    name = payload.name.strip()
    contact = payload.contact.strip()
    if not name or len(name) > 150:
        raise HTTPException(422, "Name must contain 1 to 150 characters")
    if payload.contact_type == "email":
        # Basic mailbox syntax only; no delivery/DNS checks or extra dependency.
        parts = contact.rsplit("@", 1)
        valid = len(parts) == 2 and len(contact) <= 255
        if valid:
            local, domain = parts
            valid = bool(
                re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local)
                and not local.startswith(".")
                and not local.endswith(".")
                and ".." not in local
                and "." in domain
                and all(
                    re.fullmatch(
                        r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label
                    )
                    for label in domain.split(".")
                )
            )
        if not valid:
            raise HTTPException(422, EMAIL_ERROR)
    else:
        # Allow common international/local formatting, without guessing a country.
        digits = re.sub(r"[^0-9]", "", contact)
        if (
            len(contact) > 255
            or not re.fullmatch(r"\+?[0-9 ()-]+", contact)
            or not 7 <= len(digits) <= 15
        ):
            raise HTTPException(422, "Please enter a valid phone number")
    if payload.message is not None and len(payload.message) > 500:
        raise HTTPException(422, MESSAGE_ERROR)
    if not payload.consent:
        raise HTTPException(422, CONSENT_ERROR)
    # Consent is a submission gate, not a new persisted column. Keep existing schema.
    return {"name": name, "contact": contact, "message": payload.message}


def create_enquiries_router() -> APIRouter:
    """Public submission uses the same injectable database as authentication."""
    router = APIRouter()

    @router.post("/enquiries", status_code=201, response_model=EnquiryOut)
    def submit_enquiry(
        payload: EnquiryIn, response: Response, db: Annotated[Session, Depends(get_db)]
    ) -> EnquiryOut:
        values = validated_values(payload)
        # This public route has no authentication read transaction. Commit before
        # returning success; a failed insert rolls back without creating an account.
        with db.begin():
            db.execute(public_enquiries.insert().values(**values))
        response.headers["Cache-Control"] = "no-store"
        return EnquiryOut(message=SUCCESS_MESSAGE)

    return router


class EnquiryRecord(BaseModel):
    """Explicit public-field projection for the private Coordinator list."""

    id: UUID
    name: str
    contact: str
    message: str | None
    created_at: datetime


def create_enquiry_listing_router() -> APIRouter:
    """Reuse database-derived roles and Cookie/Bearer authentication unchanged."""
    router = APIRouter(dependencies=[Depends(require_coordinator)])

    @router.get("/enquiries", response_model=list[EnquiryRecord])
    def list_enquiries(
        db: Annotated[Session, Depends(get_db)],
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=10000),
    ) -> list[EnquiryRecord]:
        # UUID breaks timestamp ties; bounded offset pagination avoids unbounded reads.
        rows = db.execute(
            select(
                public_enquiries.c.id,
                public_enquiries.c.name,
                public_enquiries.c.contact,
                public_enquiries.c.message,
                public_enquiries.c.created_at,
            )
            .order_by(
                public_enquiries.c.created_at.desc(), public_enquiries.c.id.desc()
            )
            .limit(limit)
            .offset(offset)
        ).mappings()
        return [EnquiryRecord.model_validate(row) for row in rows]

    return router
