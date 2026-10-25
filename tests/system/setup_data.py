"""Set up data that the pages cannot create yet, in the running system.

Class sessions (US-014) and QR check-in (US-011) are not built yet, so tests
insert them into the Accessment database through ``docker compose``.

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
