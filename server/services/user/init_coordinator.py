"""Explicit, non-destructive Coordinator bootstrap for an already initialized DB."""

import argparse
import getpass
import os
import secrets
import sys
from collections.abc import Callable, Sequence
from enum import Enum

from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from models import users

# Serializes this script's callers only; automatic application seeding is unchanged.
BOOTSTRAP_LOCK = 800002


class BootstrapResult(Enum):
    CREATED = "Coordinator created."
    EXISTS = "An active Coordinator already exists; no changes made."
    USERNAME_TAKEN = "Username already taken; no changes made."


def initialize_coordinator(
    engine: Engine,
    username: str,
    display_name: str,
    password: str,
    hash_password: Callable[[str, bytes], str],
) -> BootstrapResult:
    """Create only when no active Coordinator exists; never update existing rows.

    The caller supplies both the engine and the established application hasher.
    This function does not initialize tables, import the app or read DATABASE_URL.
    """
    if engine.dialect.name != "postgresql":
        raise ValueError("PostgreSQL is required")
    if not username.strip() or len(username) > 100:
        raise ValueError("Username must contain 1 to 100 characters")
    if not display_name.strip() or len(display_name) > 150:
        raise ValueError("Name must contain 1 to 150 characters")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    encoded = hash_password(password, secrets.token_bytes(16))
    try:
        with engine.begin() as db:
            db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": BOOTSTRAP_LOCK}
            )
            existing = db.execute(
                select(users.c.id).where(
                    users.c.role == "coordinator", users.c.is_active.is_(True)
                )
            ).first()
            if existing:
                return BootstrapResult.EXISTS
            if db.execute(
                select(users.c.id).where(users.c.username == username)
            ).first():
                return BootstrapResult.USERNAME_TAKEN
            db.execute(
                users.insert().values(
                    username=username,
                    display_name=display_name,
                    password_hash=encoded,
                    role="coordinator",
                    is_active=True,
                )
            )
    except IntegrityError as exc:
        # A competing account creation outside this script may win the username.
        if (
            getattr(exc.orig, "sqlstate", None) == "23505"
            and getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            == "users_username_key"
        ):
            return BootstrapResult.USERNAME_TAKEN
        raise
    return BootstrapResult.CREATED


def main(argv: Sequence[str] | None = None) -> int:
    """Require a named URL source and a real terminal; never echo connection secrets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-env", required=True, metavar="ENV_NAME")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    args = parser.parse_args(argv)
    value = os.environ.get(args.database_url_env)
    if not value:
        print(
            "The explicitly selected database environment variable is empty.",
            file=sys.stderr,
        )
        return 2
    try:
        url = make_url(value)
        if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
            raise ValueError
    except (ValueError, SQLAlchemyError):
        print("Provide a complete postgresql+psycopg connection URL.", file=sys.stderr)
        return 2
    if not sys.stdin.isatty():
        # getpass can otherwise fall back to echoing piped input with a warning.
        print(
            "An interactive terminal is required for hidden password input.",
            file=sys.stderr,
        )
        return 2
    password = getpass.getpass("Coordinator password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        print("Passwords do not match; no changes made.", file=sys.stderr)
        return 2

    engine = None
    application = None
    previous_url = os.environ.get("DATABASE_URL")
    try:
        # app.py owns the existing hasher. Import only after pinning its lazy engine
        # to the explicit URL; importing does not run FastAPI lifespan/demo seeding.
        os.environ["DATABASE_URL"] = value
        import app as application

        engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
        result = initialize_coordinator(
            engine,
            args.username,
            args.display_name,
            password,
            application.password_hash,
        )
        print(result.value)
        return 2 if result is BootstrapResult.USERNAME_TAKEN else 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except SQLAlchemyError:
        # SQLAlchemy exceptions can contain the DSN or bound password hash.
        print(
            "Database operation failed; no bootstrap changes committed. Verify the target and existing schema.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
        if application is not None:
            application.engine.dispose()
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url


if __name__ == "__main__":
    raise SystemExit(main())
