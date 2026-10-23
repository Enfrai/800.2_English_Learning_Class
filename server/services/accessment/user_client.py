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


@dataclass(frozen=True)
class Staff:
    id: UUID
    display_name: str
    role: str


def _request(
    method: str, path: str, authorization: str, body: dict[str, Any] | None = None
) -> tuple[int, Any]:
    request = urllib.request.Request(
        f"{USER_SERVICE_URL}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": authorization, "Content-Type": "application/json"},
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
