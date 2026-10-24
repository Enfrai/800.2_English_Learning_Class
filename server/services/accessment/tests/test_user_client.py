"""Unit tests for the User Service client used by attendance (US-004).

Covers UT-29 ("Add and mark present": a new learner is added, and an
existing learner with the same name is used) and how the client reports
login and connection problems. A small fake User Service runs on a local
port, so no real service or database is needed.

Author: Pei Wu
Date: 23 Oct 2026
"""

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from uuid import UUID, uuid4

import pytest

import user_client

AUTHORIZATION = "Bearer test-session"


@dataclass
class FakeUserService:
    """Answers each (method, path) with a fixed status and JSON body."""

    answers: dict[tuple[str, str], tuple[int, Any]] = field(default_factory=dict)
    requests: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def user_service(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeUserService]:
    fake = FakeUserService()

    class Handler(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            fake.requests.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "body": json.loads(body) if body else None,
                }
            )
            status, answer = fake.answers.get((self.command, self.path), (500, {}))
            payload = json.dumps(answer).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = _answer

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        user_client, "USER_SERVICE_URL", f"http://127.0.0.1:{server.server_port}"
    )
    yield fake
    server.shutdown()
    server.server_close()


def learner(first: str, family: str, created_at: str) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "first_name": first,
        "family_name": family,
        "first_language": None,
        "contact": None,
        "created_at": created_at,
    }


DETAILS = {
    "first_name": "Mere",
    "family_name": "Walker",
    "first_language": "Samoan",
    "contact": None,
}


# UT-29 (US-004 AC2)


def test_new_name_adds_the_learner_as_the_logged_in_staff_member(
    user_service: FakeUserService,
) -> None:
    added = learner("Mere", "Walker", "2026-10-23T09:00:00Z")
    user_service.answers[("POST", "/learners")] = (201, added)

    result, is_new = user_client.add_or_find_learner(AUTHORIZATION, DETAILS)

    assert (result, is_new) == (added, True)
    request = user_service.requests[0]
    assert request["authorization"] == AUTHORIZATION
    assert request["body"] == DETAILS


def test_existing_name_uses_the_learner_added_first(
    user_service: FakeUserService,
) -> None:
    newer = learner("Mere", "Walker", "2026-10-20T09:00:00Z")
    older = learner("Mere", "Walker", "2026-10-01T09:00:00Z")
    user_service.answers[("POST", "/learners")] = (
        409,
        {
            "detail": {
                "message": "A learner with this name already exists",
                "duplicates": [newer, older],
            }
        },
    )

    result, is_new = user_client.add_or_find_learner(AUTHORIZATION, DETAILS)

    assert (result, is_new) == (older, False)


def test_invalid_name_is_reported_with_the_user_service_message(
    user_service: FakeUserService,
) -> None:
    user_service.answers[("POST", "/learners")] = (
        422,
        {"detail": {"field": "first_name", "message": "First name is required"}},
    )

    with pytest.raises(user_client.LearnerFieldError) as error:
        user_client.add_or_find_learner(AUTHORIZATION, {**DETAILS, "first_name": ""})

    assert (error.value.field, error.value.message) == (
        "first_name",
        "First name is required",
    )


def test_ended_session_asks_for_login_when_adding_a_learner(
    user_service: FakeUserService,
) -> None:
    user_service.answers[("POST", "/learners")] = (401, {"detail": "Login required"})

    with pytest.raises(user_client.LoginRequiredError):
        user_client.add_or_find_learner(AUTHORIZATION, DETAILS)


# Checking the session and learner ids


def test_current_staff_is_read_from_the_user_service(
    user_service: FakeUserService,
) -> None:
    staff_id = uuid4()
    user_service.answers[("GET", "/me")] = (
        200,
        {"id": str(staff_id), "display_name": "Ana Silva", "role": "teacher"},
    )

    staff = user_client.current_staff(AUTHORIZATION)

    assert staff == user_client.Staff(staff_id, "Ana Silva", "teacher")
    assert user_service.requests[0]["authorization"] == AUTHORIZATION


def test_ended_session_is_reported_as_login_required(
    user_service: FakeUserService,
) -> None:
    user_service.answers[("GET", "/me")] = (401, {"detail": "Login required"})

    with pytest.raises(user_client.LoginRequiredError):
        user_client.current_staff(AUTHORIZATION)


@pytest.mark.parametrize(("status", "exists"), [(200, True), (404, False)])
def test_learner_exists_follows_the_user_service(
    user_service: FakeUserService, status: int, exists: bool
) -> None:
    learner_id = uuid4()
    user_service.answers[("GET", f"/learners/{learner_id}")] = (status, {})

    assert user_client.learner_exists(AUTHORIZATION, learner_id) is exists


def test_unexpected_answer_is_not_turned_into_not_found(
    user_service: FakeUserService,
) -> None:
    learner_id = uuid4()
    user_service.answers[("GET", f"/learners/{learner_id}")] = (500, {})

    with pytest.raises(user_client.UserServiceError):
        user_client.learner_exists(AUTHORIZATION, learner_id)


def test_unreachable_user_service_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Port 9 (discard) is closed on test machines, so the connection fails.
    monkeypatch.setattr(user_client, "USER_SERVICE_URL", "http://127.0.0.1:9")

    with pytest.raises(user_client.UserServiceError):
        user_client.current_staff(AUTHORIZATION)
    with pytest.raises(user_client.UserServiceError):
        user_client.learner_exists(AUTHORIZATION, UUID(int=1))
