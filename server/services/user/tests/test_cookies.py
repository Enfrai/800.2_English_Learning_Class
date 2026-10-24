"""Cookie transport, credential ambiguity, origin checks and cache controls."""

import importlib
from http.cookies import SimpleCookie
from typing import Any

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select

from test_auth import AuthContext
from test_login import LoginContext


def cookie_headers(context: AuthContext) -> dict[str, str]:
    return {"Cookie": f"ako_session={context['token']}"}


@pytest.mark.parametrize(
    "scheme,forced,public_origin,secure",
    [
        ("http", False, None, False),
        ("https", False, None, True),
        ("http", True, None, True),
        ("http", False, "https://ako.example", True),
        ("http", False, "HTTPS://ako.example", True),
    ],
)
def test_login_cookie_attributes(
    api: LoginContext,
    scheme: str,
    forced: bool,
    public_origin: str | None,
    secure: bool,
) -> None:
    module, _, _, _, _ = api
    security = importlib.import_module("security")
    module.app.state.session_security = security.SessionSecurity(public_origin, forced)
    client = TestClient(module.app, base_url=f"{scheme}://testserver")
    try:
        response = client.post(
            "/login", json={"username": "teacher", "password": "CorrectPass!"}
        )
        assert response.status_code == 200
        cookies = SimpleCookie(response.headers["set-cookie"])
        cookie = cookies["ako_session"]
        assert cookie.value == response.json()["sessionid"]
        assert cookie["httponly"]
        assert bool(cookie["secure"]) == secure
        assert cookie["samesite"] == "lax"
        assert cookie["path"] == "/" and cookie["domain"] == ""
        assert cookie["max-age"] == "1800"
        assert response.headers["cache-control"] == "no-store"
    finally:
        client.close()


def test_cookie_only_authentication_is_read_only(context: AuthContext) -> None:
    c = context

    with c["factory"]() as db:
        before = dict(db.execute(select(c["sessions"])).mappings().one())
    response = c["client"].get("/session", headers=cookie_headers(c))
    assert response.status_code == 200
    assert response.json()["user_id"] == str(c["user_id"])
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers
    with c["factory"]() as db:
        assert dict(db.execute(select(c["sessions"])).mappings().one()) == before


@pytest.mark.parametrize(
    "authorization,cookie,status",
    [
        ("valid", "valid", 200),
        ("valid", "other", 401),
        ("other", "valid", 401),
        ("Basic abc", "valid", 401),
        ("Bearer", "valid", 401),
        ("valid", "", 401),
        (None, "other", 401),
    ],
)
def test_credentials_never_silently_fall_back(
    context: AuthContext, authorization: str | None, cookie: str, status: int
) -> None:
    c = context
    headers = {"Cookie": f"ako_session={c['token'] if cookie == 'valid' else cookie}"}
    if authorization is not None:
        headers["Authorization"] = (
            f"Bearer {c['token']}"
            if authorization == "valid"
            else "Bearer other"
            if authorization == "other"
            else authorization
        )
    response = c["client"].get("/session", headers=headers)
    assert response.status_code == status
    if status == 401:
        assert response.json() == {"detail": "Not authenticated"}
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("kind", ["cookie", "authorization"])
def test_duplicate_credentials_rejected(context: AuthContext, kind: str) -> None:
    token = context["token"]
    headers = (
        [("Cookie", f"ako_session={token}; ako_session=other")]
        if kind == "cookie"
        else [("Authorization", f"Bearer {token}"), ("Authorization", "Bearer other")]
    )
    assert context["client"].get("/session", headers=headers).status_code == 401


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "null",
        "http://testserver/path",
        "http://testserver.evil.example",
        "http://testserver:0",
    ],
)
def test_login_origin_rejected_before_database(api: LoginContext, origin: str) -> None:
    _, client, db, _, _ = api
    response = client.post(
        "/login",
        headers={"Origin": origin},
        json={"username": "teacher", "password": "CorrectPass!"},
    )
    assert response.status_code == 403
    db.execute.assert_not_called()
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "headers",
    [
        {"Cookie": "ako_session=existing"},
        {"Sec-Fetch-Site": "same-origin"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_browser_login_requires_origin(
    api: LoginContext, headers: dict[str, str]
) -> None:
    _, client, db, _, _ = api
    response = client.post(
        "/login",
        headers=headers,
        json={"username": "teacher", "password": "CorrectPass!"},
    )
    assert response.status_code == 403
    db.execute.assert_not_called()


def test_same_origin_browser_login(api: LoginContext) -> None:
    _, client, _, _, _ = api
    response = client.post(
        "/login",
        headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
        json={"username": "teacher", "password": "CorrectPass!"},
    )
    assert response.status_code == 200
    assert "set-cookie" in response.headers


def test_public_origin_proxy_configuration(api: LoginContext) -> None:
    module, client, _, _, _ = api
    security = importlib.import_module("security")
    module.app.state.session_security = security.SessionSecurity(
        public_origin="https://ako.example"
    )
    response = client.post(
        "/login",
        headers={"Origin": "https://ako.example"},
        json={"username": "teacher", "password": "CorrectPass!"},
    )
    assert response.status_code == 200
    assert SimpleCookie(response.headers["set-cookie"])["ako_session"]["secure"]


@pytest.mark.parametrize(
    "origin,with_bearer,status",
    [
        (None, False, 403),
        ("https://evil.example", False, 403),
        ("http://testserver", False, 200),
        (None, True, 403),
        ("http://testserver", True, 200),
    ],
)
def test_cookie_mutation_guard(
    context: AuthContext, origin: str | None, with_bearer: bool, status: int
) -> None:
    c = context
    calls = []

    @c["module"].app.post("/test/cookie-mutation")
    def guarded(user: Any = Depends(c["auth"].get_current_user)) -> dict[str, str]:
        calls.append(user.user_id)
        return {"user_id": str(user.user_id)}

    headers = cookie_headers(c)
    if origin is not None:
        headers["Origin"] = origin
    if with_bearer:
        headers["Authorization"] = f"Bearer {c['token']}"
    response = c["client"].post("/test/cookie-mutation", headers=headers)
    assert response.status_code == status
    assert bool(calls) == (status == 200)


@pytest.mark.parametrize("status", [401, 422, 423])
def test_failed_login_never_issues_cookie(api: LoginContext, status: int) -> None:
    _, client, _, row, _ = api
    if status == 423:
        row["failed_login_attempts"] = 4
    payload = {"username": "teacher", "password": "wrong"} if status != 422 else {}
    response = client.post("/login", json=payload)
    assert response.status_code == status
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"


def test_cookie_settings_reject_insecure_override(
    monkeypatch: pytest.MonkeyPatch, api: LoginContext
) -> None:
    security = importlib.import_module("security")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    with pytest.raises(ValueError):
        security.SessionSecurity.from_environment()


def test_bearer_only_mutation_does_not_require_origin(context: AuthContext) -> None:
    c = context

    @c["module"].app.post("/test/bearer-mutation")
    def guarded(user: Any = Depends(c["auth"].get_current_user)) -> dict[str, str]:
        return {"user_id": str(user.user_id)}

    response = c["client"].post(
        "/test/bearer-mutation", headers={"Authorization": f"Bearer {c['token']}"}
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == str(c["user_id"])


def test_raw_forwarded_header_is_not_a_trusted_origin(api: LoginContext) -> None:
    _, client, db, _, _ = api
    response = client.post(
        "/login",
        headers={
            "Origin": "https://evil.example",
            "X-Forwarded-Host": "evil.example",
            "X-Forwarded-Proto": "https",
        },
        json={"username": "teacher", "password": "CorrectPass!"},
    )
    assert response.status_code == 403
    db.execute.assert_not_called()
