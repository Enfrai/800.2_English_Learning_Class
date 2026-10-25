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
"""

import os
import time
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from api import BASE_URL, api_headers
from learners_page import LearnersPage
from setup_data import CLUB_TIMEZONE, CheckIn, access_sql

USERNAME = os.environ.get("DEMO_USERNAME", "demo")
PASSWORD = os.environ.get("DEMO_PASSWORD", "DemoPass123!")
SESSION_KEY = "ako.sessionid"
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
def page(browser: Browser) -> Iterator[Page]:
    """A fresh browser window with no login, closed after the test."""
    context = browser.new_context(
        base_url=BASE_URL, viewport={"width": 1280, "height": 900}
    )
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def session_id(page: Page) -> str:
    """Log in through the API. A new login ends any earlier demo session."""
    response = page.request.post(
        "/api/user/login", data={"username": USERNAME, "password": PASSWORD}
    )
    assert response.ok, f"Login failed with status {response.status}"
    return response.json()["sessionid"]


@pytest.fixture
def logged_in_page(page: Page, session_id: str) -> Page:
    """A browser window where the demo coordinator is logged in."""
    page.context.add_init_script(
        f"window.localStorage.setItem({SESSION_KEY!r}, {session_id!r})"
    )
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
    """Create a class session and return its id.

    Until US-014 adds "Start today's class", sessions are inserted straight
    into the Accessment database of the running ``docker compose`` system.
    """

    def create(days_ago: int = 0) -> str:
        # days_ago is an int, so formatting it into the SQL text is safe.
        return access_sql(
            "INSERT INTO class_sessions (id, session_date, created_by) "
            "VALUES (gen_random_uuid(), "
            f"(now() AT TIME ZONE '{CLUB_TIMEZONE}')::date - {int(days_ago)}, "
            "gen_random_uuid()) RETURNING id"
        ).splitlines()[0]

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
        page.locator("md-outlined-text-field[name=username] input").fill(USERNAME)
        page.locator("md-outlined-text-field[name=password] input").fill(PASSWORD)
        page.locator("md-filled-button").click()
        # US-001: a successful login opens the home page for the person's role.
        page.wait_for_url("**/coordinator")

    return log_in
