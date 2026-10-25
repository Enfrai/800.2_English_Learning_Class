"""Call the User Service: check a session and find or add learners (US-004).

The browser's ``Authorization`` header is passed on, so the User Service
checks the session and records which staff member added a learner.

Author: Pei Wu
Date: 23 Oct 2026
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from uuid import UUID

# Inside Docker, "user-service" reaches user1 and user2 in turn.
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8000").rstrip("/")
TIMEOUT_SECONDS = 5
# Shared with the User Service for calls made without a login (US-012).
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


class UserServiceError(Exception):
    """The User Service could not be reached or gave an unexpected answer."""


class LoginRequiredError(Exception):
    """No session, or the session has ended."""


class LearnerFieldError(Exception):
    """A learner field breaks a rule. The message comes from the User Service."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class SignInNameNotFoundError(Exception):
    """No active learner has the typed name (US-012)."""


class AmbiguousSignInNameError(Exception):
    """Several active learners have the typed name (US-012)."""


@dataclass(frozen=True)
class Staff:
    id: UUID
    display_name: str
    role: str


def _request(
    method: str,
    path: str,
    authorization: str | None,
    body: dict[str, Any] | None = None,
    *,
    internal: bool = False,
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if authorization is not None:
        headers["Authorization"] = authorization
    if internal:
        headers["X-Internal-Key"] = INTERNAL_API_KEY
    request = urllib.request.Request(
        f"{USER_SERVICE_URL}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.load(error)
        except ValueError:
            return error.code, None
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise UserServiceError("User service unavailable") from error


def current_staff(authorization: str) -> Staff:
    """Return the logged-in staff member.

    Raises:
        LoginRequiredError: the session is missing or has ended.
        UserServiceError: the User Service could not answer.
    """
    status, body = _request("GET", "/me", authorization)
    if status == 401:
        raise LoginRequiredError("Login required")
    if status != 200:
        raise UserServiceError(f"User service answered {status}")
    return Staff(UUID(body["id"]), body["display_name"], body["role"])


def learner_exists(authorization: str, learner_id: UUID) -> bool:
    """Return whether the User Service has a learner with this id."""
    status, _ = _request("GET", f"/learners/{learner_id}", authorization)
    if status == 200:
        return True
    if status == 404:
        return False
    if status == 401:
        raise LoginRequiredError("Login required")
    raise UserServiceError(f"User service answered {status}")


def add_or_find_learner(
    authorization: str, details: dict[str, str | None]
) -> tuple[dict[str, Any], bool]:
    """Add a learner, or use the existing learner with the same name.

    Returns the learner and whether it was newly added. When several
    learners share the name, the one added first is used (Test Plan UT-29).

    Raises:
        LearnerFieldError: a field is missing or too long.
        LoginRequiredError: the session is missing or has ended.
        UserServiceError: the User Service could not answer.
    """
    status, body = _request("POST", "/learners", authorization, details)
    if status == 201:
        return body, True
    if status == 409:
        duplicates = body["detail"]["duplicates"]
        return min(duplicates, key=lambda learner: learner["created_at"]), False
    if status == 422 and isinstance(body.get("detail"), dict):
        raise LearnerFieldError(body["detail"]["field"], body["detail"]["message"])
    if status == 401:
        raise LoginRequiredError("Login required")
    raise UserServiceError(f"User service answered {status}")


def find_learner_for_sign_in(first_name: str, family_name: str) -> dict[str, Any]:
    """Return the learner matching a typed name, for QR sign-in (US-012).

    The learner has no login, so this call proves the service with the shared
    internal key. Only the matched learner comes back, never the class list.

    Raises:
        SignInNameNotFoundError: no active learner has this name.
        AmbiguousSignInNameError: several active learners have this name.
        UserServiceError: the User Service could not answer, or refused the
            key. A misconfigured key is never reported as "not found".
    """
    status, body = _request(
        "POST",
        "/internal/learners/match",
        None,
        {"first_name": first_name, "family_name": family_name},
        internal=True,
    )
    if status == 200:
        return body
    if status == 404:
        raise SignInNameNotFoundError("Learner not found")
    if status == 409:
        raise AmbiguousSignInNameError("Several learners have this name")
    raise UserServiceError(f"User service answered {status}")


def staff_names(authorization: str) -> dict[UUID, str]:
    """Return every staff member's display name, by id (coordinators only).

    Used to show who made each attendance correction (US-015 AC4).

    Raises:
        LoginRequiredError: the session is missing or has ended.
        UserServiceError: the User Service could not answer or refused.
    """
    status, body = _request("GET", "/staff", authorization)
    if status == 401:
        raise LoginRequiredError("Login required")
    if status != 200:
        raise UserServiceError(f"User service answered {status}")
    return {UUID(row["id"]): row["display_name"] for row in body}


def learner_names(authorization: str, learner_ids: set[UUID]) -> dict[UUID, str]:
    """Return "First Family" for each learner id that still exists.

    Active learners come from one list call; a learner no longer on the list
    is looked up by id, so history still names them.

    Raises:
        LoginRequiredError: the session is missing or has ended.
        UserServiceError: the User Service could not answer.
    """
    names: dict[UUID, str] = {}
    if not learner_ids:
        return names
    status, body = _request("GET", "/learners", authorization)
    if status == 401:
        raise LoginRequiredError("Login required")
    if status != 200:
        raise UserServiceError(f"User service answered {status}")
    for row in body:
        names[UUID(row["id"])] = f"{row['first_name']} {row['family_name']}"
    for learner_id in learner_ids - names.keys():
        status, row = _request("GET", f"/learners/{learner_id}", authorization)
        if status == 200:
            names[learner_id] = f"{row['first_name']} {row['family_name']}"
        elif status == 401:
            raise LoginRequiredError("Login required")
        elif status != 404:
            raise UserServiceError(f"User service answered {status}")
    return {
        learner_id: names[learner_id]
        for learner_id in learner_ids
        if learner_id in names
    }
