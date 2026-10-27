"""Bootstrap checks use unique schemas inside the verified disposable test DB."""

import importlib
import os
import pty
import select as io_select
import subprocess
import sys
import termios
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.schema import CreateSchema, DropSchema

from test_postgres import PgContext


@pytest.fixture
def bootstrap(pg: PgContext) -> Iterator[tuple[Engine, ModuleType, PgContext]]:
    """
    Provide isolated Coordinator-bootstrap test environment.
    """
    module = importlib.import_module("init_coordinator")
    schema = f"bootstrap_{uuid4().hex}"
    with pg.engine.begin() as db:
        db.execute(CreateSchema(schema))
    engine = create_engine(
        pg.engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    )
    pg.users.create(
        engine
    )  # Fixture preparation only; the bootstrap must never do this.
    try:
        yield engine, module, pg
    finally:
        engine.dispose()
        with pg.engine.begin() as db:
            db.execute(DropSchema(schema, cascade=True))


def rows(engine: Engine, pg: PgContext) -> list[dict[str, Any]]:
    """
    Prepare or exercise rows in the test init coordinator test scenario.
    """
    with engine.connect() as db:
        return [dict(row) for row in db.execute(select(pg.users)).mappings()]


def test_create_uuid_hash_and_no_ddl(
    bootstrap: tuple[Engine, ModuleType, PgContext],
) -> None:
    """
    Verify that create uuid hash and no ddl.
    """
    engine, module, pg = bootstrap
    statements = []

    def record(
        conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool
    ) -> None:
        """
        Inspect or record record events for the surrounding database or HTTP test.
        """
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        result = module.initialize_coordinator(
            engine, "first", "First Coordinator", "TestPass123!", pg.a.password_hash
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert result is module.BootstrapResult.CREATED
    row = rows(engine, pg)[0]
    assert (
        isinstance(row["id"], UUID)
        and row["role"] == "coordinator"
        and row["is_active"]
    )
    assert pg.a.verify_password("TestPass123!", row["password_hash"])
    assert not any(
        s.lstrip().upper().startswith(("CREATE", "ALTER", "DROP")) for s in statements
    )


def test_repeat_preserves_existing_account(
    bootstrap: tuple[Engine, ModuleType, PgContext],
) -> None:
    """
    Verify that repeat preserves existing account.
    """
    engine, module, pg = bootstrap
    module.initialize_coordinator(
        engine, "first", "First", "TestPass123!", pg.a.password_hash
    )
    before = rows(engine, pg)
    assert (
        module.initialize_coordinator(
            engine, "another", "Changed", "OtherPass!", pg.a.password_hash
        )
        is module.BootstrapResult.EXISTS
    )
    assert rows(engine, pg) == before


def test_username_conflict_preserves_teacher(
    bootstrap: tuple[Engine, ModuleType, PgContext],
) -> None:
    """
    Verify that username conflict preserves teacher.
    """
    engine, module, pg = bootstrap
    with engine.begin() as db:
        db.execute(
            pg.users.insert().values(
                username="taken",
                display_name="Teacher",
                role="teacher",
                password_hash="unchanged",
            )
        )
    before = rows(engine, pg)
    assert (
        module.initialize_coordinator(
            engine, "taken", "Coordinator", "TestPass123!", pg.a.password_hash
        )
        is module.BootstrapResult.USERNAME_TAKEN
    )
    assert rows(engine, pg) == before


def test_inactive_account_is_not_reactivated(
    bootstrap: tuple[Engine, ModuleType, PgContext],
) -> None:
    """
    Verify that inactive account is not reactivated.
    """
    engine, module, pg = bootstrap
    with engine.begin() as db:
        db.execute(
            pg.users.insert().values(
                username="inactive",
                display_name="Old",
                role="coordinator",
                is_active=False,
                password_hash="unchanged",
            )
        )
    before = rows(engine, pg)[0]
    assert (
        module.initialize_coordinator(
            engine, "new", "New", "TestPass123!", pg.a.password_hash
        )
        is module.BootstrapResult.CREATED
    )
    assert next(r for r in rows(engine, pg) if r["username"] == "inactive") == before


def test_concurrent_initialization_creates_only_one(
    bootstrap: tuple[Engine, ModuleType, PgContext],
) -> None:
    """
    Verify that concurrent initialization creates only one.
    """
    engine, module, pg = bootstrap
    barrier = Barrier(2)

    def run(name: str) -> Any:
        """
        Execute a subprocess with the requested exit-code and output-capture policy.
        """
        barrier.wait(5)
        return module.initialize_coordinator(
            engine, name, name, "TestPass123!", pg.a.password_hash
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(run, "one"), pool.submit(run, "two")
        results = {a.result(timeout=10), b.result(timeout=10)}
    assert results == {module.BootstrapResult.CREATED, module.BootstrapResult.EXISTS}
    assert len(rows(engine, pg)) == 1


def test_insert_failure_rolls_back(
    bootstrap: tuple[Engine, ModuleType, PgContext],
) -> None:
    """
    Verify that insert failure rolls back.
    """
    engine, module, pg = bootstrap

    def fail(
        conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool
    ) -> None:
        """
        Simulate an unavailable dependency or failing operation for the surrounding
        test.
        """
        if statement.startswith("INSERT"):
            cursor.execute("SELECT 1 / 0")

    event.listen(engine, "after_cursor_execute", fail)
    try:
        from sqlalchemy.exc import SQLAlchemyError

        with pytest.raises(SQLAlchemyError):
            module.initialize_coordinator(
                engine, "first", "First", "TestPass123!", pg.a.password_hash
            )
    finally:
        event.remove(engine, "after_cursor_execute", fail)
    assert rows(engine, pg) == []


@pytest.mark.parametrize(
    "username,name,password",
    [
        ("", "Name", "TestPass123!"),
        ("user", " ", "TestPass123!"),
        ("user", "Name", "1234567"),
    ],
)
def test_invalid_input_no_writes(
    bootstrap: tuple[Engine, ModuleType, PgContext],
    username: str,
    name: str,
    password: str,
) -> None:
    """
    Verify that invalid input no writes.
    """
    engine, module, pg = bootstrap
    with pytest.raises(ValueError):
        module.initialize_coordinator(
            engine, username, name, password, pg.a.password_hash
        )
    assert rows(engine, pg) == []


def test_cli_requires_explicit_source(pg: PgContext) -> None:
    """
    Verify that cli requires explicit source.
    """
    script = Path(__file__).resolve().parents[1] / "init_coordinator.py"
    result = subprocess.run(
        [sys.executable, str(script), "--username", "test", "--display-name", "Test"],
        env=os.environ | {"DATABASE_URL": "must-not-be-used"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "--database-url-env" in result.stderr
    assert "must-not-be-used" not in result.stderr


def test_cli_rejects_nonterminal(
    bootstrap: tuple[Engine, ModuleType, PgContext],
) -> None:
    """
    Verify that cli rejects nonterminal.
    """
    engine, module, pg = bootstrap
    result = subprocess.run(
        [
            sys.executable,
            module.__file__,
            "--database-url-env",
            "BOOTSTRAP_TEST_URL",
            "--username",
            "first",
            "--display-name",
            "First",
        ],
        env=os.environ
        | {"BOOTSTRAP_TEST_URL": engine.url.render_as_string(hide_password=False)},
        input="must-not-be-consumed\n",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "interactive terminal" in result.stderr
    assert "must-not-be-consumed" not in result.stderr and rows(engine, pg) == []


def test_real_hidden_terminal_password(
    bootstrap: tuple[Engine, ModuleType, PgContext],
) -> None:
    """
    Verify that real hidden terminal password.
    """
    engine, module, pg = bootstrap
    password = uuid4().hex
    master, slave = pty.openpty()
    # getpass falls back to this terminal stdin without echo; never send secrets
    # until its prompt has appeared and the ECHO flag is confirmed disabled.
    process = subprocess.Popen(
        [
            sys.executable,
            module.__file__,
            "--database-url-env",
            "BOOTSTRAP_TEST_URL",
            "--username",
            "terminal",
            "--display-name",
            "Terminal",
        ],
        env=os.environ
        | {"BOOTSTRAP_TEST_URL": engine.url.render_as_string(hide_password=False)},
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    output = b""
    sent = 0
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            if io_select.select([master], [], [], 0.1)[0]:
                output += os.read(master, 4096)
            prompt = b"Coordinator password: " if sent == 0 else b"Confirm password: "
            if sent < 2 and prompt in output:
                assert not termios.tcgetattr(slave)[3] & termios.ECHO
                os.write(master, (password + "\n").encode())
                sent += 1
            if process.poll() is not None:
                break
        assert process.wait(timeout=2) == 0 and sent == 2
        assert password.encode() not in output
        assert pg.a.verify_password(password, rows(engine, pg)[0]["password_hash"])
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        os.close(slave)
