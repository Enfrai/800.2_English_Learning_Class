"""Call the Ako API from tests the same way the browser does.

Author: Pei Wu
Date: 25 Oct 2026
"""

import os

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")


def api_headers(session_id: str) -> dict[str, str]:
    """Headers for a test's direct API call.

    A browser adds ``Origin`` to every POST, and the User Service refuses
    cookie-authenticated changes without it (CSRF protection, US-001).
    """
    return {"Authorization": f"Bearer {session_id}", "Origin": BASE_URL}
