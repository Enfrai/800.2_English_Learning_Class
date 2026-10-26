"""Shared fixtures for browser system tests.

The tests drive a real browser against a running Ako system started with
``docker compose`` (see README.md in this folder). Settings:

- ``BASE_URL``: address of Nginx, default ``http://localhost:8080``
- ``DEMO_USERNAME`` / ``DEMO_PASSWORD``: defaults match ``server/compose.yaml``
- ``BROWSER_CHANNEL``: for example ``chrome`` to use the installed Google
  Chrome instead of Playwright's own Chromium
- ``COMPOSE_FILE``: the running system's compose file, default
  ``server/compose.yaml`` (used to create class sessions)

Author: Pei Wu
Date: 23 Oct 2026
Updated: Pei Wu, 25 Oct 2026 (teacher login and in-class ticks for US-015)
Updated: Pei Wu, 26 Oct 2026 (one class session per date, US-014)
"""

import os
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from api import BASE_URL, api_headers
from attendance_page import PRESENT_AT_START
from learners_page import LearnersPage
from playwright.sync_api import Browser, Page, expect, sync_playwright
from setup_data import CLUB_TIMEZONE, CheckIn, access_sql

USERNAME = os.environ.get("DEMO_USERNAME", "demo")
PASSWORD = os.environ.get("DEMO_PASSWORD", "DemoPass123!")
API_PAUSE_SECONDS = 0.06  # Nginx allows 20 API requests a second.

# The first page load after a build can be slow.
expect.set_options(timeout=10_000)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("BROWSER_CHANNEL") or None
        )
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser, request: pytest.FixtureRequest) -> Iterator[Page]:
    """A fresh browser window with no login, closed after the test."""
    context = browser.new_context(
        base_url=BASE_URL, viewport={"width": 1280, "height": 900}
    )
    page = context.new_page()
    report_root = os.getenv("AKO_TEST_REPORTS")
    if report_root:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    yield page
    if report_root:
        report = getattr(request.node, "test_call_report", None)
        if report is not None and report.failed:
            name = re.sub(r"[^A-Za-z0-9_.-]", "_", request.node.nodeid)
            artifacts = Path(report_root) / "system" / "failures"
            artifacts.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(path=str(artifacts / f"{name}.png"), full_page=True)
                context.tracing.stop(path=str(artifacts / f"{name}.zip"))
            except Exception:
                # A browser crash must not hide the original test failure.
                pass
        else:
            context.tracing.stop()
    context.close()


@pytest.fixture
def session_id(page: Page) -> str:
    """Log in through the API. A new login ends any earlier demo session."""
    response = page.request.post(
        "/api/user/login",
        data={"username": USERNAME, "password": PASSWORD},
        headers={"Origin": BASE_URL},
    )
    assert response.ok, f"Login failed with status {response.status}"
    return response.json()["sessionid"]


@pytest.fixture
def logged_in_page(page: Page, session_id: str) -> Page:
    """A browser window where the demo coordinator is logged in."""
    # page.request shares cookies with the browser context. The login fixture
    # already installed the HttpOnly session cookie; no localStorage token.
    assert session_id
    return page


@pytest.fixture
def teacher_page(browser: Browser, page: Page, session_id: str) -> Iterator[Page]:
    """A second browser window where a new teacher account is logged in.

    The demo coordinator creates the account through US-002, so each test
    has its own teacher.
    """
    username = f"teacher_{uuid4().hex[:10]}"
    password = f"Temp-{uuid4().hex[:8]}"
    response = page.request.post(
        "/api/user/staff",
        headers=api_headers(session_id),
        data={
            "display_name": "Test Teacher",
            "username": username,
            "temporary_password": password,
        },
    )
    assert response.status == 201, response.status
    context = browser.new_context(
        base_url=BASE_URL, viewport={"width": 1280, "height": 900}
    )
    login = context.request.post(
        "/api/user/login", data={"username": username, "password": password}
    )
    assert login.ok, f"Teacher login failed with status {login.status}"
    yield context.new_page()
    context.close()


@pytest.fixture
def learners_page(logged_in_page: Page) -> LearnersPage:
    """The Learners page, opened by a logged-in coordinator."""
    learners = LearnersPage(logged_in_page)
    learners.open()
    return learners


@pytest.fixture
def add_learner(page: Page, session_id: str) -> Callable[..., dict[str, Any]]:
    """Add a made-up learner through the User Service API."""

    def add(first: str, family: str, language: str = "") -> dict[str, Any]:
        response = page.request.post(
            "/api/user/learners",
            headers=api_headers(session_id),
            data={
                "first_name": first,
                "family_name": family,
                "first_language": language,
                "contact": "",
                "allow_duplicate": True,
            },
        )
        assert response.status == 201, response.status
        time.sleep(API_PAUSE_SECONDS)
        return response.json()

    return add


@pytest.fixture
def class_session() -> Callable[..., str]:
    """Return a class session for today, or a new one in the past.

    US-014 allows one session per date. Today's session is shared by every
    test that asks for it, so earlier tests may already have learners
    present; the number present now is kept in ``PRESENT_AT_START`` and the
    attendance page object counts from it. Nothing is deleted, so a run
    against real data never removes attendance.

    A past session is always new: it gets the first date on or before
    ``days_ago`` days back that has no session, because corrections leave
    change-log entries that cannot be removed (US-015).

    Sessions are inserted into the Accessment database of the running
    ``docker compose`` system rather than started on the page (US-014).
    """
    club_today = f"(now() AT TIME ZONE '{CLUB_TIMEZONE}')::date"

    def create(days_ago: int = 0) -> str:
        # days_ago is an int, so formatting it into the SQL text is safe.
        days_ago = int(days_ago)
        if days_ago == 0:
            access_sql(
                "INSERT INTO class_sessions (id, session_date, created_by) "
                f"VALUES (gen_random_uuid(), {club_today}, gen_random_uuid()) "
                "ON CONFLICT (session_date) DO NOTHING"
            )
            session_id = access_sql(
                f"SELECT id FROM class_sessions WHERE session_date = {club_today}"
            )
        else:
            session_id = access_sql(
                "INSERT INTO class_sessions (id, session_date, created_by) "
                "SELECT gen_random_uuid(), day, gen_random_uuid() "
                f"FROM generate_series({days_ago}, {days_ago} + 3650) AS back, "
                f"LATERAL (SELECT {club_today} - back AS day) AS d "
                "WHERE NOT EXISTS "
                "(SELECT 1 FROM class_sessions WHERE session_date = day) "
                "ORDER BY back LIMIT 1 RETURNING id"
            )
        session_id = session_id.splitlines()[0]
        PRESENT_AT_START[session_id] = int(
            access_sql(
                "SELECT count(*) FROM attendance_records "
                f"WHERE session_id = '{UUID(session_id)}' AND status = 'present'"
            )
        )
        return session_id

    return create


@pytest.fixture
def ticked_in_class() -> Callable[[str, str], None]:
    """Record a learner as present at a class, as a teacher's tick would.

    Past classes cannot be ticked through the page, so the record is
    inserted into the Accessment database.
    """

    def tick(session_id: str, learner_id: str) -> None:
        # UUID() checks both ids before they go into the SQL text.
        access_sql(
            "INSERT INTO attendance_records "
            "(id, session_id, learner_id, status, recorded_by) VALUES "
            f"(gen_random_uuid(), '{UUID(session_id)}', '{UUID(learner_id)}', "
            "'present', gen_random_uuid())"
        )

    return tick


@pytest.fixture
def check_in() -> CheckIn:
    # Every test request comes from this computer's address, so wrong names
    # from earlier tests would count towards its limit of 50. Start each test
    # with no wrong names on the throwaway database.
    access_sql("DELETE FROM signin_failures")
    return CheckIn()


@pytest.fixture
def log_in_through_page(page: Page) -> Callable[[], None]:
    """Log in with the real login page, as a person would."""

    def log_in() -> None:
        page.goto("/")
        page.get_by_label("Username", exact=True).fill(USERNAME)
        page.get_by_label("Password", exact=True).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        # US-001: a successful login opens the home page for the person's role.
        page.wait_for_url("**/coordinator")

    return log_in


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Make the call outcome available to the page fixture before it closes."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item.test_call_report = report
