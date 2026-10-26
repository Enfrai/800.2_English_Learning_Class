"""Set up data for the system tests in the running system.

Class sessions are started through the US-014 endpoints and QR check-in is
opened and closed through the US-011 endpoints, the same ones the pages use.
Only what the pages cannot do is written to the Accessment database, through
a guarded test connection (in Compose test mode) or ``docker compose exec``
(manual host mode): attendance ticked during a past class, and clearing
wrong sign-in names.

Author: Pei Wu
Date: 25 Oct 2026
Updated: Pei Wu, 26 Oct 2026 (check-in through the US-011 endpoints;
  sessions through US-014)
"""

import os
import subprocess
from pathlib import Path
from uuid import UUID

from api import BASE_URL
from playwright.sync_api import APIRequestContext

COMPOSE_FILE = os.environ.get(
    "COMPOSE_FILE", str(Path(__file__).resolve().parents[2] / "server/compose.yaml")
)

# A browser sends Origin with every change; the staff proxy checks it (CSRF).
ORIGIN = {"Origin": BASE_URL}

# Must match CLUB_TIMEZONE of the Accessment Service.
CLUB_TIMEZONE = "Pacific/Auckland"


def access_sql(sql: str) -> str:
    """Run SQL in the Accessment database of the running docker compose system.

    Only for set-up the pages cannot do: attendance ticked during a past
    class (US-015) and clearing wrong sign-in names (US-012). Callers build the SQL from values they generated or checked,
    never from user input.
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
    """Open and close QR check-in as staff, through the US-011 endpoints.

    A class has one open check-in at a time: opening it again returns the
    same code. A code made outside US-011 (by an older version of these
    tests) cannot be shown again, so it is closed and a new one opened.
    """

    def __init__(self, staff: APIRequestContext) -> None:
        self.staff = staff

    def _address(self, session_id: str) -> str:
        return f"/api/staff/access/sessions/{UUID(session_id)}/check-in"

    def open(self, session_id: str) -> str:
        """Open check-in for today's class and return the QR code's token."""
        response = self.staff.post(self._address(session_id), headers=ORIGIN)
        if response.status == 409 and "open it again" in response.text():
            self.close(session_id)
            response = self.staff.post(self._address(session_id), headers=ORIGIN)
        assert response.ok, f"Open check-in: {response.status} {response.text()}"
        return response.json()["sign_in_url"].rsplit("/", 1)[1]

    def close(self, session_id: str) -> None:
        response = self.staff.delete(self._address(session_id), headers=ORIGIN)
        assert response.ok, f"Close check-in: {response.status} {response.text()}"
