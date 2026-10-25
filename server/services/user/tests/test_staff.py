"""US-002 API checks on an identity-verified disposable PostgreSQL database."""

import hashlib
import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select

from test_postgres import PgContext


@pytest.fixture
def coordinator(pg: PgContext) -> tuple[UUID, str]:
    """A separate actor keeps the target Teacher fixture unchanged."""
    return add_coordinator(pg)


def add_coordinator(pg: PgContext) -> tuple[UUID, str]:
    user_id, token = uuid4(), uuid4().hex
    now = datetime.now(UTC)
    with pg.engine.begin() as db:
        db.execute(
            pg.users.insert().values(
                id=user_id,
                username=f"coordinator_{user_id.hex}",
                display_name="Test Coordinator",
                password_hash="not-used-for-login",
                role="coordinator",
            )
        )
        db.execute(
            pg.sessions.insert().values(
                user_id=user_id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                last_activity_at=now,
                expires_at=now + timedelta(minutes=30),
            )
        )
    return user_id, token


def headers(token: str | None) -> dict[str, str]:
    return {"Cookie": "", **({"Authorization": f"Bearer {token}"} if token else {})}


def payload(**changes: Any) -> dict[str, Any]:
    return {
        "username": f"new_{uuid4().hex}",
        "display_name": "New Teacher",
        "temporary_password": "12345678",
        **changes,
    }


def count_username(pg: PgContext, username: str) -> int:
    with pg.engine.connect() as db:
        return db.scalar(
            select(func.count())
            .select_from(pg.users)
            .where(pg.users.c.username == username)
        )


def test_create_list_and_password_hash(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    data = payload()
    response = pg.clients[0].post("/staff", json=data, headers=headers(coordinator[1]))
    assert response.status_code == 201
    account = response.json()
    assert set(account) == {"id", "username", "display_name", "role", "is_active"}
    assert account["role"] == "teacher" and account["is_active"] is True
    UUID(account["id"])
    listed = pg.clients[1].get("/staff", headers=headers(coordinator[1]))
    assert account in listed.json()
    assert all(set(item) == set(account) for item in listed.json())
    assert (
        response.headers["cache-control"]
        == listed.headers["cache-control"]
        == "no-store"
    )
    with pg.engine.connect() as db:
        row = (
            db.execute(select(pg.users).where(pg.users.c.id == UUID(account["id"])))
            .mappings()
            .one()
        )
        assert row["password_hash"] != data["temporary_password"]
        assert pg.a.verify_password(data["temporary_password"], row["password_hash"])
    login = pg.clients[1].post(
        "/login",
        json={"username": data["username"], "password": data["temporary_password"]},
        headers={"Cookie": ""},
    )
    assert login.status_code == 200


@pytest.mark.parametrize("length, status", [(0, 422), (7, 422), (8, 201)])
def test_password_boundary(
    pg: PgContext, coordinator: tuple[UUID, str], length: int, status: int
) -> None:
    data = payload(temporary_password="x" * length)
    response = pg.clients[0].post("/staff", json=data, headers=headers(coordinator[1]))
    assert response.status_code == status
    if status == 422:
        assert response.json() == {"detail": "Password must be at least 8 characters"}
    assert count_username(pg, data["username"]) == int(status == 201)


@pytest.mark.parametrize("active", [True, False])
def test_duplicate_username(
    pg: PgContext, coordinator: tuple[UUID, str], active: bool
) -> None:
    with pg.engine.begin() as db:
        db.execute(
            pg.users.update()
            .where(pg.users.c.id == pg.user_id)
            .values(is_active=active)
        )
    before = pg.user()
    response = pg.clients[1].post(
        "/staff", json=payload(username=pg.username), headers=headers(coordinator[1])
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Username already taken"}
    assert pg.user() == before and count_username(pg, pg.username) == 1


def test_concurrent_duplicate_creation(
    pg: PgContext, coordinator: tuple[UUID, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    other = add_coordinator(pg)
    barrier = Barrier(2)
    staff = importlib.import_module("staff")
    original = staff.create_teacher

    def create(*args: Any, **kwargs: Any) -> Any:
        barrier.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(staff, "create_teacher", create)
    data = payload()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            pg.clients[0].post, "/staff", json=data, headers=headers(coordinator[1])
        )
        second = pool.submit(
            pg.clients[1].post, "/staff", json=data, headers=headers(other[1])
        )
        responses = [first.result(timeout=10), second.result(timeout=10)]
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert next(r for r in responses if r.status_code == 409).json() == {
        "detail": "Username already taken"
    }
    assert count_username(pg, data["username"]) == 1


@pytest.mark.parametrize("actor", ["anonymous", "teacher"])
@pytest.mark.parametrize("action", ["list", "create", "rename", "deactivate"])
def test_permission_denial(pg: PgContext, actor: str, action: str) -> None:
    token = pg.login().json()["sessionid"] if actor == "teacher" else None
    method, path, data = {
        "list": ("GET", "/staff", None),
        "create": ("POST", "/staff", payload()),
        "rename": ("PATCH", f"/staff/{pg.user_id}", {"display_name": "No"}),
        "deactivate": ("POST", f"/staff/{pg.user_id}/deactivate", None),
    }[action]
    before = pg.user()
    response = pg.clients[1].request(method, path, json=data, headers=headers(token))
    assert response.status_code == (401 if actor == "anonymous" else 403)
    if actor == "teacher":
        assert response.json() == {"detail": "You do not have permission"}
    assert response.headers["cache-control"] == "no-store"
    assert pg.user() == before


@pytest.mark.parametrize(
    "extra", ["role", "id", "is_active", "permissions", "password_hash"]
)
def test_create_rejects_extra_fields(
    pg: PgContext, coordinator: tuple[UUID, str], extra: str
) -> None:
    data = payload(**{extra: "coordinator"})
    response = pg.clients[0].post("/staff", json=data, headers=headers(coordinator[1]))
    assert response.status_code == 422 and count_username(pg, data["username"]) == 0


@pytest.mark.parametrize("extra", ["role", "username", "password", "id", "is_active"])
def test_rename_rejects_other_mutations(
    pg: PgContext, coordinator: tuple[UUID, str], extra: str
) -> None:
    before = pg.user()
    response = pg.clients[0].patch(
        f"/staff/{pg.user_id}",
        json={"display_name": "No", extra: "unexpected"},
        headers=headers(coordinator[1]),
    )
    assert response.status_code == 422 and pg.user() == before


def test_rename_updates_list_only_name_and_timestamp(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    before = pg.user()
    response = pg.clients[0].patch(
        f"/staff/{pg.user_id}",
        json={"display_name": "Renamed Teacher"},
        headers=headers(coordinator[1]),
    )
    assert response.status_code == 200
    after = pg.user()
    assert after["display_name"] == "Renamed Teacher"
    assert {
        k: v for k, v in after.items() if k not in ("display_name", "updated_at")
    } == {k: v for k, v in before.items() if k not in ("display_name", "updated_at")}
    assert (
        response.json()
        in pg.clients[1].get("/staff", headers=headers(coordinator[1])).json()
    )


def test_deactivate_preserves_account_and_revokes_session(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    token = pg.login().json()["sessionid"]
    before = pg.user()
    response = pg.clients[1].post(
        f"/staff/{pg.user_id}/deactivate", headers=headers(coordinator[1])
    )
    assert response.status_code == 200 and response.json()["is_active"] is False
    after = pg.user()
    assert {k: v for k, v in after.items() if k not in ("is_active", "updated_at")} == {
        k: v for k, v in before.items() if k not in ("is_active", "updated_at")
    }
    assert pg.session_rows()[0]["revoked_at"] is not None
    assert pg.login().status_code == pg.validate(token).status_code == 401
    assert pg.clients[0].post("/activity", headers=headers(token)).status_code == 401
    assert (
        response.json()
        in pg.clients[0].get("/staff", headers=headers(coordinator[1])).json()
    )
    # Repeating deactivation never deletes the account or rewrites revocation time.
    revoked = pg.session_rows()[0]["revoked_at"]
    assert (
        pg.clients[0]
        .post(f"/staff/{pg.user_id}/deactivate", headers=headers(coordinator[1]))
        .status_code
        == 200
    )
    assert pg.session_rows()[0]["revoked_at"] == revoked


def test_coordinator_name_is_not_a_mutation_target(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    response = pg.clients[0].patch(
        f"/staff/{coordinator[0]}",
        json={"display_name": "No"},
        headers=headers(coordinator[1]),
    )
    assert response.status_code == 403
    assert pg.validate(coordinator[1]).status_code == 200


# AC5 / Test Plan UT-12: at least one Coordinator must stay active.

LAST_COORDINATOR = {"detail": "At least one coordinator must stay active"}


def is_active(pg: PgContext, user_id: UUID) -> bool:
    with pg.engine.connect() as db:
        return db.scalar(select(pg.users.c.is_active).where(pg.users.c.id == user_id))


def keep_only_active_coordinator(pg: PgContext, user_id: UUID) -> None:
    """AC5's "Given": the test database is shared, so retire other Coordinators."""
    with pg.engine.begin() as db:
        db.execute(
            pg.users.update()
            .where(pg.users.c.role == "coordinator", pg.users.c.id != user_id)
            .values(is_active=False)
        )


def deactivate(pg: PgContext, target: UUID, actor_token: str, replica: int = 0) -> Any:
    return pg.clients[replica].post(
        f"/staff/{target}/deactivate", headers=headers(actor_token)
    )


def test_only_active_coordinator_cannot_deactivate_their_account(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    keep_only_active_coordinator(pg, coordinator[0])

    response = deactivate(pg, coordinator[0], coordinator[1])

    assert response.status_code == 409
    assert response.json() == LAST_COORDINATOR
    assert is_active(pg, coordinator[0])
    assert pg.validate(coordinator[1]).status_code == 200


def test_inactive_coordinators_do_not_count_as_staying_active(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    add_coordinator(pg)
    keep_only_active_coordinator(pg, coordinator[0])

    response = deactivate(pg, coordinator[0], coordinator[1])

    assert response.status_code == 409
    assert response.json() == LAST_COORDINATOR


def test_coordinator_can_be_deactivated_while_another_stays_active(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    keep_only_active_coordinator(pg, coordinator[0])
    other = add_coordinator(pg)

    response = deactivate(pg, other[0], coordinator[1])

    assert response.status_code == 200
    assert response.json()["role"] == "coordinator"
    assert response.json()["is_active"] is False
    assert pg.validate(other[1]).status_code == 401
    # Now only one is left, so it cannot deactivate itself.
    assert deactivate(pg, coordinator[0], coordinator[1]).json() == LAST_COORDINATOR


def test_coordinator_can_deactivate_own_account_while_another_stays_active(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    other = add_coordinator(pg)

    response = deactivate(pg, coordinator[0], coordinator[1])

    assert response.status_code == 200
    assert not is_active(pg, coordinator[0])
    assert pg.validate(coordinator[1]).status_code == 401
    assert is_active(pg, other[0])


def test_two_coordinators_deactivating_themselves_at_once_leave_one_active(
    pg: PgContext, coordinator: tuple[UUID, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    keep_only_active_coordinator(pg, coordinator[0])
    other = add_coordinator(pg)
    staff = importlib.import_module("staff")
    original = staff.deactivate_teacher
    held, release, waiting = Event(), Event(), Event()

    def hold_first(*args: Any) -> Any:
        row = original(*args)
        if not held.is_set():
            held.set()
            assert release.wait(5)
        return row

    def query(
        conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool
    ) -> None:
        if "FOR UPDATE" in statement and "users" in statement:
            waiting.set()

    monkeypatch.setattr(staff, "deactivate_teacher", hold_first)
    event.listen(pg.b.engine, "before_cursor_execute", query)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(deactivate, pg, coordinator[0], coordinator[1], 0)
            try:
                assert held.wait(5)
                # Each removes only itself, so without locking every active
                # Coordinator the two requests would not wait for each other.
                second = pool.submit(deactivate, pg, other[0], other[1], 1)
                assert waiting.wait(5)
            finally:
                release.set()
            first_status = first.result(timeout=10).status_code
            second_response = second.result(timeout=10)
    finally:
        event.remove(pg.b.engine, "before_cursor_execute", query)

    assert first_status == 200
    assert second_response.status_code == 409
    assert second_response.json() == LAST_COORDINATOR
    assert is_active(pg, other[0])


@pytest.mark.parametrize("origin", [None, "http://evil.example"])
@pytest.mark.parametrize("action", ["create", "rename", "deactivate"])
def test_cookie_csrf_denial(
    pg: PgContext, coordinator: tuple[UUID, str], origin: str | None, action: str
) -> None:
    method, path, data = {
        "create": ("POST", "/staff", payload()),
        "rename": ("PATCH", f"/staff/{pg.user_id}", {"display_name": "No"}),
        "deactivate": ("POST", f"/staff/{pg.user_id}/deactivate", None),
    }[action]
    before = pg.user()
    h = {
        "Cookie": f"ako_session={coordinator[1]}",
        **({"Origin": origin} if origin else {}),
    }
    response = pg.clients[1].request(method, path, json=data, headers=h)
    assert response.status_code == 403 and pg.user() == before


def test_same_origin_cookie_mutation(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    response = pg.clients[1].post(
        "/staff",
        json=payload(),
        headers={
            "Cookie": f"ako_session={coordinator[1]}",
            "Origin": "http://testserver",
        },
    )
    assert response.status_code == 201


def test_deactivation_database_failure_rolls_back(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    pg.login()
    before, sessions = pg.user(), pg.session_rows()

    def fail(
        conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool
    ) -> None:
        if statement.startswith("UPDATE user_sessions"):
            cursor.execute("SELECT 1 / 0")

    event.listen(pg.engine, "before_cursor_execute", fail)
    try:
        response = pg.clients[0].post(
            f"/staff/{pg.user_id}/deactivate", headers=headers(coordinator[1])
        )
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
        assert response.headers["cache-control"] == "no-store"
    finally:
        event.remove(pg.engine, "before_cursor_execute", fail)
    assert pg.user() == before and pg.session_rows() == sessions


@pytest.mark.parametrize("operation", ["login", "activity"])
def test_deactivation_wins_concurrent_login_or_activity(
    pg: PgContext,
    coordinator: tuple[UUID, str],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    token = pg.login().json()["sessionid"]
    staff = importlib.import_module("staff")
    original = staff.deactivate_teacher
    held, release, waiting = Event(), Event(), Event()

    def hold(*args: Any) -> Any:
        row = original(*args)
        held.set()
        assert release.wait(5)
        return row

    def query(
        conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool
    ) -> None:
        if "FOR UPDATE" in statement and "users" in statement:
            waiting.set()

    monkeypatch.setattr(staff, "deactivate_teacher", hold)
    event.listen(pg.b.engine, "before_cursor_execute", query)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            stop = pool.submit(
                pg.clients[0].post,
                f"/staff/{pg.user_id}/deactivate",
                headers=headers(coordinator[1]),
            )
            try:
                assert held.wait(5)
                pending = (
                    pool.submit(pg.login, 1)
                    if operation == "login"
                    else pool.submit(
                        pg.clients[1].post, "/activity", headers=headers(token)
                    )
                )
                assert waiting.wait(5)
            finally:
                release.set()
            assert stop.result(timeout=10).status_code == 200
            assert pending.result(timeout=10).status_code == 401
    finally:
        event.remove(pg.b.engine, "before_cursor_execute", query)
    assert pg.user()["is_active"] is False and pg.validate(token).status_code == 401


def test_actor_revoked_while_waiting_cannot_mutate(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    waiting = Event()

    def query(
        conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool
    ) -> None:
        if "FOR UPDATE" in statement:
            waiting.set()

    event.listen(pg.b.engine, "before_cursor_execute", query)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pg.engine.begin() as db:
                db.execute(
                    select(pg.users)
                    .where(pg.users.c.id == coordinator[0])
                    .with_for_update()
                )
                pending = pool.submit(
                    pg.clients[1].patch,
                    f"/staff/{pg.user_id}",
                    json={"display_name": "No"},
                    headers=headers(coordinator[1]),
                )
                assert waiting.wait(5)
                db.execute(
                    pg.sessions.update()
                    .where(pg.sessions.c.user_id == coordinator[0])
                    .values(revoked_at=datetime.now(UTC))
                )
            assert pending.result(timeout=10).status_code == 401
    finally:
        event.remove(pg.b.engine, "before_cursor_execute", query)
    assert pg.user()["display_name"] == "Integration Teacher"


@pytest.mark.parametrize("target,status", [("missing", 404), ("invalid-uuid", 422)])
def test_target_errors(
    pg: PgContext, coordinator: tuple[UUID, str], target: str, status: int
) -> None:
    value = str(uuid4()) if target == "missing" else target
    response = pg.clients[0].patch(
        f"/staff/{value}", json={"display_name": "No"}, headers=headers(coordinator[1])
    )
    assert (
        response.status_code == status
        and response.headers["cache-control"] == "no-store"
    )


def test_deactivation_rejects_mutation_payload(
    pg: PgContext, coordinator: tuple[UUID, str]
) -> None:
    response = pg.clients[0].post(
        f"/staff/{pg.user_id}/deactivate",
        json={"role": "coordinator"},
        headers=headers(coordinator[1]),
    )
    assert response.status_code == 422 and pg.user()["is_active"] is True
