"""Session writes and race checks against the isolated PostgreSQL instance."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from threading import Barrier, Event
from typing import Any

import pytest
from sqlalchemy import event, select

from test_postgres import PgContext


def mutation(
    pg: PgContext, path: str, token: str, replica: int = 0, cookie: bool = False
) -> Any:
    """
    Prepare or exercise mutation in the test lifecycle test scenario.
    """
    headers = {"Cookie": "", "Authorization": f"Bearer {token}"}
    if cookie:
        headers = {"Cookie": f"ako_session={token}", "Origin": "http://testserver"}
    return pg.clients[replica].post(path, headers=headers)


@pytest.mark.parametrize("cookie", [False, True])
def test_logout_revokes_and_clears_cookie(pg: PgContext, cookie: bool) -> None:
    """
    Verify that logout revokes and clears cookie.
    """
    token = pg.login().json()["sessionid"]
    response = mutation(pg, "/logout", token, 1, cookie)
    assert response.status_code == 204 and response.content == b""
    cleared = SimpleCookie(response.headers["set-cookie"])["ako_session"]
    assert cleared["max-age"] == "0" and cleared["httponly"]
    assert cleared["path"] == "/" and cleared["samesite"] == "lax"
    assert response.headers["cache-control"] == "no-store"
    assert pg.session_rows()[0]["revoked_at"] is not None
    for replica in (0, 1):
        assert pg.validate(token, replica).status_code == 401
        assert mutation(pg, "/activity", token, replica).status_code == 401


@pytest.mark.parametrize("cookie", [False, True])
def test_explicit_activity_slides_expiry_and_passive_reads_do_not(
    pg: PgContext, cookie: bool
) -> None:
    """
    Verify that explicit activity slides expiry and passive reads do not.
    """
    token = pg.login().json()["sessionid"]
    now = datetime.now(UTC)
    pg.update_session(
        created_at=now - timedelta(hours=1),
        last_activity_at=now - timedelta(minutes=20),
        expires_at=now + timedelta(minutes=10),
    )
    before = pg.session_rows()
    assert pg.validate(token).status_code == 200
    assert pg.session_rows() == before
    start = datetime.now(UTC)
    response = mutation(pg, "/activity", token, 1, cookie)
    end = datetime.now(UTC)
    assert response.status_code == 200
    row = pg.session_rows()[0]
    assert start <= row["last_activity_at"] <= end
    assert row["expires_at"] == row["last_activity_at"] + timedelta(minutes=30)
    assert datetime.fromisoformat(response.json()["expires_at"]) == row["expires_at"]
    assert SimpleCookie(response.headers["set-cookie"])["ako_session"].value == token
    assert pg.validate(token, 0).status_code == 200
    assert pg.session_rows()[0] == row


@pytest.mark.parametrize(
    "state", ["expired", "revoked", "inactive", "idle_boundary", "expiry_boundary"]
)
def test_invalid_sessions_cannot_refresh(
    pg: PgContext, state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verify that invalid sessions cannot refresh.
    """
    token = pg.login().json()["sessionid"]
    now = datetime.now(UTC)
    if state == "revoked":
        pg.update_session(revoked_at=now)
    elif state == "inactive":
        with pg.engine.begin() as db:
            db.execute(
                pg.users.update()
                .where(pg.users.c.id == pg.user_id)
                .values(is_active=False)
            )
    else:
        pg.update_session(
            created_at=now - timedelta(hours=1),
            last_activity_at=now - timedelta(minutes=30)
            if state == "idle_boundary"
            else now,
            expires_at=now + timedelta(minutes=1) if state == "idle_boundary" else now,
        )
    before = pg.session_rows()
    response = mutation(pg, "/activity", token)
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert pg.session_rows() == before
    assert pg.validate(token).status_code == 401


@pytest.mark.parametrize("path", ["/activity", "/logout"])
@pytest.mark.parametrize("origin", [None, "https://evil.example", "null"])
def test_csrf_rejected_without_session_changes(
    pg: PgContext, path: str, origin: str | None
) -> None:
    """
    Verify that csrf rejected without session changes.
    """
    token = pg.login().json()["sessionid"]
    before = pg.session_rows()
    headers = {"Cookie": f"ako_session={token}"}
    if origin is not None:
        headers["Origin"] = origin
    response = pg.clients[1].post(path, headers=headers)
    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    assert pg.session_rows() == before


@pytest.mark.parametrize("first", ["/logout", "/activity"])
def test_both_serializations_of_logout_activity_race(
    pg: PgContext, first: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verify that both serializations of logout activity race.
    """
    token = pg.login().json()["sessionid"]
    held, release = Event(), Event()
    original = pg.a.lock_active_session

    def hold(db: Any, value: str) -> Any:
        """
        Prepare or exercise hold in the test lifecycle test scenario.
        """
        row = original(db, value)
        held.set()
        assert release.wait(5)
        return row

    monkeypatch.setattr(pg.a, "lock_active_session", hold)
    second = "/activity" if first == "/logout" else "/logout"
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(mutation, pg, first, token, 0)
        try:
            assert held.wait(5)
            two = pool.submit(mutation, pg, second, token, 1)
        finally:
            release.set()
        assert one.result(timeout=10).status_code == (
            204 if first == "/logout" else 200
        )
        assert two.result(timeout=10).status_code == (
            401 if second == "/activity" else 204
        )
    row = pg.session_rows()[0]
    assert row["revoked_at"] is not None
    assert pg.validate(token).status_code == 401
    assert mutation(pg, "/activity", token, 1).status_code == 401
    assert pg.session_rows()[0] == row


def test_expiry_is_rechecked_after_lock_wait(pg: PgContext) -> None:
    """
    Verify that expiry is rechecked after lock wait.
    """
    token = pg.login().json()["sessionid"]
    waiting = Event()

    def query_started(
        conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool
    ) -> None:
        """
        Signal that the observed database query has begun for the concurrency test.
        """
        if "FOR UPDATE" in statement and "users" in statement:
            waiting.set()

    event.listen(pg.b.engine, "before_cursor_execute", query_started)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pg.engine.begin() as db:
                db.execute(
                    select(pg.users.c.id)
                    .where(pg.users.c.id == pg.user_id)
                    .with_for_update()
                )
                pending = pool.submit(mutation, pg, "/activity", token, 1)
                assert waiting.wait(5)
                now = datetime.now(UTC)
                db.execute(
                    pg.sessions.update()
                    .where(pg.sessions.c.user_id == pg.user_id)
                    .values(
                        created_at=now - timedelta(hours=1),
                        expires_at=now - timedelta(seconds=1),
                    )
                )
            assert pending.result(timeout=10).status_code == 401
    finally:
        event.remove(pg.b.engine, "before_cursor_execute", query_started)
    assert pg.validate(token).status_code == 401


def test_replacement_and_activity_do_not_restore_old_token(pg: PgContext) -> None:
    """
    Verify that replacement and activity do not restore old token.
    """
    old = pg.login().json()["sessionid"]
    barrier = Barrier(2)

    def refresh() -> int:
        """
        Prepare or exercise refresh in the test lifecycle test scenario.
        """
        barrier.wait(5)
        return mutation(pg, "/activity", old, 0).status_code

    def replace() -> str:
        """
        Prepare or exercise replace in the test lifecycle test scenario.
        """
        barrier.wait(5)
        response = pg.login(1)
        assert response.status_code == 200
        return response.json()["sessionid"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(refresh)
        new = pool.submit(replace).result(timeout=10)
        assert pending.result(timeout=10) in (200, 401)
    assert pg.validate(old).status_code == 401
    assert pg.validate(new).status_code == 200
    assert len(pg.session_rows()) == 1


def test_teacher_account_boundary_discloses_no_accounts(pg: PgContext) -> None:
    """
    Verify that teacher account boundary discloses no accounts.
    """
    token = pg.login().json()["sessionid"]
    response = pg.clients[1].get(
        "/account-management/access",
        headers={"Cookie": "", "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission"}
    with pg.engine.begin() as db:
        db.execute(
            pg.users.update()
            .where(pg.users.c.id == pg.user_id)
            .values(role="coordinator")
        )
    response = pg.clients[1].get(
        "/account-management/access",
        headers={"Cookie": "", "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200 and response.json() == {"allowed": True}
