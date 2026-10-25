"""Verify the lesson API trusts only validated staff identities.

Author: Sandhya Tiwari
Date: 25 Oct 2026
"""

from uuid import uuid4

import pytest
import user_client


@pytest.mark.parametrize("role", ["teacher", "coordinator"])
def test_valid_staff(monkeypatch, role):
    identifier = uuid4()
    monkeypatch.setattr(
        user_client,
        "_request",
        lambda *args: (
            200,
            {"id": str(identifier), "display_name": "Staff", "role": role},
        ),
    )
    staff = user_client.current_staff("Bearer opaque")
    assert staff.id == identifier
    assert staff.is_coordinator == (role == "coordinator")


@pytest.mark.parametrize(
    "body", [None, {}, {"id": "bad"}, {"id": str(uuid4()), "display_name": "Staff"}]
)
def test_malformed_identity_is_service_failure(monkeypatch, body):
    monkeypatch.setattr(user_client, "_request", lambda *args: (200, body))
    with pytest.raises(user_client.UserServiceError):
        user_client.current_staff("Bearer opaque")


def test_non_staff_role_cannot_access_lesson_library(monkeypatch):
    monkeypatch.setattr(
        user_client,
        "_request",
        lambda *args: (
            200,
            {"id": str(uuid4()), "display_name": "Visitor", "role": "visitor"},
        ),
    )
    with pytest.raises(user_client.LoginRequiredError):
        user_client.current_staff("Bearer opaque")


@pytest.mark.parametrize(
    "status,error",
    [(401, user_client.LoginRequiredError), (503, user_client.UserServiceError)],
)
def test_identity_service_errors(monkeypatch, status, error):
    monkeypatch.setattr(user_client, "_request", lambda *args: (status, None))
    with pytest.raises(error):
        user_client.current_staff("Bearer opaque")


def test_request_forwards_identity_without_cookies(monkeypatch):
    import io
    import json

    class Response(io.BytesIO):
        status = 200

    def open_request(request, timeout):
        assert request.get_header("Authorization") == "Bearer opaque"
        assert request.get_header("Cookie") is None
        assert timeout == user_client.TIMEOUT_SECONDS
        return Response(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(user_client.urllib.request, "urlopen", open_request)
    assert user_client._request("GET", "/me", "Bearer opaque") == (200, {"ok": True})


@pytest.mark.parametrize("kind", ["network", "timeout", "invalid-json"])
def test_request_failures_are_sanitized(monkeypatch, kind):
    import io
    import urllib.error

    class Response(io.BytesIO):
        status = 200

    def fail(*args, **kwargs):
        if kind == "network":
            raise urllib.error.URLError("private hostname")
        if kind == "timeout":
            raise TimeoutError()
        return Response(b"not json")

    monkeypatch.setattr(user_client.urllib.request, "urlopen", fail)
    with pytest.raises(user_client.UserServiceError, match="User service unavailable"):
        user_client._request("GET", "/me", "Bearer opaque")


@pytest.mark.parametrize(
    "body,expected",
    [(b'{"detail":"expired"}', {"detail": "expired"}), (b"invalid", None)],
)
def test_http_errors_preserve_status(monkeypatch, body, expected):
    import io
    import urllib.error

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "http://user-service/me", 401, "Unauthorized", {}, io.BytesIO(body)
        )

    monkeypatch.setattr(user_client.urllib.request, "urlopen", fail)
    assert user_client._request("GET", "/me", "Bearer opaque") == (401, expected)
