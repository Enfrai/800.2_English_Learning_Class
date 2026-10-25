"""Call the User Service to check who is logged in (US-006).

The browser's ``Authorization`` header is passed on, so the User Service
checks the session. The lesson author and role always come from here, never
from the request body.

Author: Sandhya Tiwari
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


@dataclass(frozen=True)
class Staff:
    id: UUID
    display_name: str
    role: str

    @property
    def is_coordinator(self) -> bool:
        return self.role == "coordinator"


def _request(method: str, path: str, authorization: str) -> tuple[int, Any]:
    request = urllib.request.Request(
        f"{USER_SERVICE_URL}{path}",
        method=method,
        headers={"Authorization": authorization},
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
