"""Manage classroom QR check-in windows with shared locks and printable codes.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import base64
import hashlib
import hmac
import io
import os
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import qrcode
import qrcode.image.svg
from checkin import hash_token
from fastapi import APIRouter, Depends, HTTPException
from models import checkin_windows, class_sessions
from sqlalchemy import select
from sqlalchemy.orm import Session


def utc(value: datetime) -> datetime:
    """
    Normalize the input datetime to timezone-aware UTC.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def origin() -> str:
    """
    Validate and return the configured browser-reachable check-in origin.
    """
    value = os.getenv("CHECKIN_PUBLIC_ORIGIN", "http://localhost:8080").rstrip("/")
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError()
        if (
            value != f"{parsed.scheme}://{parsed.netloc}"
            or any(c.isspace() for c in value)
            or "\\" in value
        ):
            raise ValueError()
        _ = parsed.port
    except ValueError as exc:
        raise HTTPException(
            503, "The public check-in address is not configured correctly"
        ) from exc
    return value


def token_for(window_id: UUID, session_id: UUID) -> str:
    """
    Derive the recoverable QR token from the window, session and shared secret.
    """
    secret = os.getenv("CHECKIN_TOKEN_SECRET") or os.getenv("INTERNAL_API_KEY", "")
    if not secret:
        raise HTTPException(503, "The check-in token secret is not configured")
    # A fresh cryptographically random UUID seeds every window. A domain-separated
    # HMAC makes a stable, unguessable 256-bit token recoverable on either replica.
    # Only its hash is stored; neither the raw token nor the secret is persisted.
    value = hmac.new(
        secret.encode(),
        b"ako-checkin-v1:" + window_id.bytes + session_id.bytes,
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def qr_svg(url: str) -> str:
    """
    Encode the check-in URL as a printable SVG QR code.
    """
    code = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4
    )
    code.add_data(url)
    code.make(fit=True)
    output = io.BytesIO()
    code.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(output)
    return output.getvalue().decode()


def create_checkin_router(
    factory: Callable[[], Session],
    staff_dependency: Callable,
    today: Callable[[], date],
    clock: Callable[[], datetime],
) -> APIRouter:
    """
    Build the checkin API router with its injected dependencies.
    """
    router = APIRouter(tags=["US-011 QR check-in"])

    def staff_only(request):
        """
        Require a Teacher or Coordinator for classroom check-in management.
        """
        if request.staff.role not in ("teacher", "coordinator"):
            raise HTTPException(403, "You do not have permission")

    def session(db, sid, lock=False):
        """
        Load the requested class and optionally lock it before a window change.
        """
        statement = select(class_sessions).where(class_sessions.c.id == sid)
        if lock:
            statement = statement.with_for_update()
        row = db.execute(statement).mappings().first()
        if row is None:
            raise HTTPException(404, "Class session not found")
        return row

    def latest(db, sid):
        """
        Load the most recent check-in window for the class session.
        """
        return (
            db.execute(
                select(checkin_windows)
                .where(checkin_windows.c.session_id == sid)
                .order_by(
                    checkin_windows.c.opened_at.desc(),
                    checkin_windows.c.closed_at.is_(None).desc(),
                    checkin_windows.c.id.desc(),
                )
                .limit(1)
            )
            .mappings()
            .first()
        )

    def output(row, window, now):
        """
        Build the check-in state, expiry and available QR display data.
        """
        can_open = row["session_date"] == today() and row["status"] != "closed"
        state, url, svg = "not-open", None, None
        if window:
            state = (
                "closed"
                if window["closed_at"] is not None
                else "expired"
                if utc(window["expires_at"]) <= now or not can_open
                else "open"
            )
            if state == "open":
                token = token_for(window["id"], row["id"])
                if not hmac.compare_digest(hash_token(token), window["token_hash"]):
                    state = "unavailable"
                else:
                    url = f"{origin()}/sign-in/{token}"
                    svg = qr_svg(url)
        return {
            "state": state,
            "session_date": row["session_date"],
            "can_open": can_open,
            "opened_at": utc(window["opened_at"]) if window else None,
            "expires_at": utc(window["expires_at"]) if window else None,
            "sign_in_url": url,
            "qr_svg": svg,
        }

    @router.get("/sessions/{session_id}/check-in")
    def status(session_id: UUID, request: Any = Depends(staff_dependency)):
        """
        Handle GET /sessions/{session_id}/check-in for status, applying the route’s
        validation and authorization rules.
        """
        staff_only(request)
        with factory() as db:
            row = session(db, session_id)
            return output(row, latest(db, session_id), utc(clock()))

    @router.post("/sessions/{session_id}/check-in")
    def open_checkin(session_id: UUID, request: Any = Depends(staff_dependency)):
        """
        Handle POST /sessions/{session_id}/check-in for open checkin, applying the
        route’s validation and authorization rules.
        """
        staff_only(request)
        with factory() as db, db.begin():
            row = session(db, session_id, lock=True)
            if row["session_date"] != today() or row["status"] == "closed":
                raise HTTPException(
                    409, "Check-in can only open for today's active class"
                )
            now = utc(clock())
            window = latest(db, session_id)
            if (
                window
                and window["closed_at"] is None
                and utc(window["expires_at"]) > now
            ):
                result = output(row, window, now)
                if result["state"] == "unavailable":
                    raise HTTPException(
                        409, "Close check-in and open it again to display a new code"
                    )
                return result
            identifier = uuid4()
            token = token_for(identifier, session_id)
            origin()  # Reject bad configuration before saving a window.
            zone = ZoneInfo(os.getenv("CLUB_TIMEZONE", "Pacific/Auckland"))
            midnight = datetime.combine(
                row["session_date"] + timedelta(days=1), time.min, zone
            ).astimezone(UTC)
            expiry = min(now + timedelta(hours=4), midnight)
            if expiry <= now:
                raise HTTPException(
                    409, "Check-in can only open for today's active class"
                )
            db.execute(
                checkin_windows.update()
                .where(
                    checkin_windows.c.session_id == session_id,
                    checkin_windows.c.closed_at.is_(None),
                )
                .values(closed_at=now)
            )
            db.execute(
                checkin_windows.insert().values(
                    id=identifier,
                    session_id=session_id,
                    token_hash=hash_token(token),
                    opened_by=request.staff.id,
                    opened_at=now,
                    expires_at=expiry,
                )
            )
            return output(row, latest(db, session_id), now)

    @router.delete("/sessions/{session_id}/check-in")
    def close_checkin(session_id: UUID, request: Any = Depends(staff_dependency)):
        """
        Handle DELETE /sessions/{session_id}/check-in for close checkin, applying the
        route’s validation and authorization rules.
        """
        staff_only(request)
        with factory() as db, db.begin():
            row = session(db, session_id, lock=True)
            now = utc(clock())
            # Close every unclosed window, including codes made by older versions.
            db.execute(
                checkin_windows.update()
                .where(
                    checkin_windows.c.session_id == session_id,
                    checkin_windows.c.closed_at.is_(None),
                )
                .values(closed_at=now)
            )
            return output(row, latest(db, session_id), now)

    return router
