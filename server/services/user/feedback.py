"""Validate public feedback and submit mail through configurable SMTP settings.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import logging
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from security import require_same_origin

DEFAULT_RECIPIENT = "270926691@yoobeestudent.ac.nz"
SUCCESS = "Thank you. Your feedback has been submitted."
UNAVAILABLE = "Feedback is temporarily unavailable. Please try again later."
UNCONFIRMED = "Unable to confirm delivery. Please try again later."
logger = logging.getLogger(__name__)


def valid_email(value: str) -> bool:
    """Accept one mailbox only, excluding display names and header injection."""
    if len(value) > 254 or any(ord(c) < 33 or ord(c) == 127 for c in value):
        return False
    parts = value.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    return bool(
        re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local)
        and not local.startswith(".")
        and not local.endswith(".")
        and ".." not in local
        and "." in domain
        and all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in domain.split(".")
        )
    )


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=1, max_length=254)
    description: str = Field(min_length=1, max_length=5000)

    @field_validator("title")
    @classmethod
    def safe_title(cls, value: str) -> str:
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Title must not contain control characters")
        return value

    @field_validator("email")
    @classmethod
    def mailbox(cls, value: str) -> str:
        if not valid_email(value):
            raise ValueError("Please enter a valid email address")
        return value

    @field_validator("description")
    @classmethod
    def safe_description(cls, value: str) -> str:
        if any(ord(c) < 32 and c not in "\r\n\t" for c in value):
            raise ValueError("Description contains invalid characters")
        return value


@dataclass(frozen=True)
class MailSettings:
    recipients: tuple[str, ...]
    host: str
    port: int
    security: str
    username: str
    password: str
    sender: str

    @classmethod
    def load(cls) -> "MailSettings":
        recipients = tuple(
            dict.fromkeys(
                item.strip()
                for item in os.getenv("FEEDBACK_RECIPIENTS", DEFAULT_RECIPIENT).split(
                    ";"
                )
                if item.strip()
            )
        )
        host = os.getenv("FEEDBACK_SMTP_HOST", "").strip()
        security = os.getenv("FEEDBACK_SMTP_SECURITY", "starttls").strip().lower()
        port = int(
            os.getenv("FEEDBACK_SMTP_PORT", "465" if security == "ssl" else "587")
        )
        username = os.getenv("FEEDBACK_SMTP_USERNAME", "").strip()
        password = os.getenv("FEEDBACK_SMTP_PASSWORD", "")
        sender = os.getenv("FEEDBACK_SMTP_FROM", "").strip() or username
        if (
            not recipients
            or len(recipients) > 20
            or not all(valid_email(value) for value in recipients)
            or not host
            or any(c.isspace() or ord(c) < 32 for c in host)
            or security not in {"starttls", "ssl", "none"}
            or not 1 <= port <= 65535
            or bool(username) != bool(password)
            or not valid_email(sender)
        ):
            raise ValueError("Invalid feedback mail configuration")
        return cls(recipients, host, port, security, username, password, sender)


def send_feedback(payload: FeedbackIn, settings: MailSettings) -> None:
    """Return only after the relay accepts every recipient; never retry implicitly."""
    message = EmailMessage()
    message["Subject"] = f"[Ako feedback] {payload.title}"
    message["From"] = settings.sender
    message["To"] = "undisclosed-recipients:;"
    message["Reply-To"] = payload.email
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid()
    message.set_content(
        f"Title: {payload.title}\nEmail: {payload.email}\n\nDescription:\n{payload.description}\n"
    )
    options = {"host": settings.host, "port": settings.port, "timeout": 10}
    if settings.security == "ssl":
        client = smtplib.SMTP_SSL(**options, context=ssl.create_default_context())
    else:
        client = smtplib.SMTP(**options)
    with client:
        if settings.security == "starttls":
            client.starttls(context=ssl.create_default_context())
        if settings.username:
            client.login(settings.username, settings.password)
        refused = client.send_message(
            message, from_addr=settings.sender, to_addrs=list(settings.recipients)
        )
        if refused:
            raise smtplib.SMTPException("Not every recipient accepted")


def feedback_origin(request: Request) -> None:
    require_same_origin(request, required=True)


def create_feedback_router() -> APIRouter:
    router = APIRouter(tags=["Feedback"])

    @router.post("/feedback", dependencies=[Depends(feedback_origin)])
    def submit(payload: FeedbackIn, response: Response) -> dict[str, str]:
        try:
            settings = MailSettings.load()
        except ValueError as exc:
            raise HTTPException(503, UNAVAILABLE) from exc
        try:
            send_feedback(payload, settings)
        except (OSError, smtplib.SMTPException, ValueError) as exc:
            # SMTP exception messages can include credentials or recipient details.
            logger.warning("Feedback SMTP submission failed (%s)", type(exc).__name__)
            raise HTTPException(502, UNCONFIRMED) from exc
        response.headers["Cache-Control"] = "no-store"
        return {"message": SUCCESS}

    return router
