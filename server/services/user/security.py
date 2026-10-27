"""Cookie transport and same-origin checks for User-service authentication."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response

SESSION_COOKIE = "ako_session"
SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_MAX_AGE = 30 * 60
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def origin_identity(value: str) -> tuple[str, str, int]:
    """Parse a serialized HTTP origin, rejecting paths and opaque origins."""
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Expected an HTTP(S) origin without a path")
    return (
        parts.scheme,
        parts.hostname.lower(),
        parts.port
        if parts.port is not None
        else (443 if parts.scheme == "https" else 80),
    )


@dataclass(frozen=True)
class SessionSecurity:
    public_origin: str | None = None
    force_secure: bool = False

    @classmethod
    def from_environment(cls) -> "SessionSecurity":
        """
        Load and validate session cookie and public-origin security settings.
        """
        origin = os.getenv("SESSION_PUBLIC_ORIGIN") or None
        if origin is not None:
            origin_identity(origin)
        secure = os.getenv("SESSION_COOKIE_SECURE", "auto").lower()
        if secure not in {"auto", "true"}:
            raise ValueError("SESSION_COOKIE_SECURE must be auto or true")
        return cls(public_origin=origin, force_secure=secure == "true")

    def secure_cookie(self, request: Request) -> bool:
        """
        Determine whether the browser session cookie must use the Secure attribute.
        """
        return (
            self.force_secure
            or request.url.scheme == "https"
            or bool(
                self.public_origin and origin_identity(self.public_origin)[0] == "https"
            )
        )


def require_same_origin(request: Request, *, required: bool) -> None:
    """
    Validate the request origin against the configured or incoming public origin.
    """
    settings: SessionSecurity = request.app.state.session_security
    origins = request.headers.getlist("origin")
    if not origins:
        if required:
            raise HTTPException(status_code=403, detail="Request origin is not allowed")
        return
    expected = settings.public_origin or str(request.base_url).rstrip("/")
    try:
        allowed = len(origins) == 1 and origin_identity(origins[0]) == origin_identity(
            expected
        )
    except ValueError:
        allowed = False
    if not allowed:
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


def protect_login(request: Request) -> None:
    """Block login CSRF; origin-less non-browser JSON API clients remain supported."""
    require_same_origin(
        request,
        required=SESSION_COOKIE in request.cookies
        or "sec-fetch-site" in request.headers,
    )


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    """
    Attach the staff token as a scoped HttpOnly browser cookie.
    """
    settings: SessionSecurity = request.app.state.session_security
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_COOKIE_MAX_AGE,
        path=SESSION_COOKIE_PATH,
        secure=settings.secure_cookie(request),
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(request: Request, response: Response) -> None:
    """
    Expire the staff session cookie in the response.
    """
    settings: SessionSecurity = request.app.state.session_security
    response.delete_cookie(
        SESSION_COOKIE,
        path=SESSION_COOKIE_PATH,
        secure=settings.secure_cookie(request),
        httponly=True,
        samesite="lax",
    )
