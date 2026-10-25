"""Set up data that the pages cannot create yet, in the running system.

Class sessions (US-014) and QR check-in (US-011) are not built yet, so tests
insert them into the Accessment database through a guarded test connection
(in Compose test mode) or ``docker compose exec`` (manual host mode).

Author: Pei Wu
Date: 25 Oct 2026
"""

import hashlib
import os
import secrets
import subprocess
from pathlib import Path
from uuid import UUID

COMPOSE_FILE = os.environ.get(
    "COMPOSE_FILE", str(Path(__file__).resolve().parents[2] / "server/compose.yaml")
)

# Must match CLUB_TIMEZONE of the Accessment Service.
CLUB_TIMEZONE = "Pacific/Auckland"


def access_sql(sql: str) -> str:
    """Run SQL in the Accessment database of the running docker compose system.

    Only for set-up the pages cannot do yet (US-011, US-014). Callers build
    the SQL from values they generated or checked, never from user input.
    """
    url = os.getenv("TEST_ACCESS_DATABASE_URL")
    if url:
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url

        target = make_url(url)
        if not (
            os.getenv("AKO_TEST_COMPOSE") == "1"
            and target.host == "postgres-access"
            and target.database == "accessdb"
            and target.username == "access_app"
        ):
            raise RuntimeError(
                "Direct setup SQL is restricted to the isolated test stack"
            )
        engine = create_engine(url)
        try:
            with engine.begin() as db:
                result = db.execute(text(sql))
                return (
                    "\n".join(str(row[0]) for row in result)
                    if result.returns_rows
                    else ""
                )
        finally:
            engine.dispose()
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            COMPOSE_FILE,
            "exec",
            "-T",
            "postgres-access",
            "psql",
            "-U",
            "access_app",
            "-d",
            "accessdb",
            "-tAqc",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class CheckIn:
    """Open and close QR check-in, until US-011 adds it to the pages."""

    def open(self, session_id: str) -> str:
        """Open check-in for a class and return the QR code's token."""
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        access_sql(
            "INSERT INTO checkin_windows "
            "(id, session_id, token_hash, opened_by, expires_at) VALUES "
            f"(gen_random_uuid(), '{UUID(session_id)}', '{token_hash}', "
            "gen_random_uuid(), now() + interval '3 hours')"
        )
        return token

    def close(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        access_sql(
            "UPDATE checkin_windows SET closed_at = now() "
            f"WHERE token_hash = '{token_hash}'"
        )
