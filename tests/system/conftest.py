"""Shared fixtures for browser system tests.

The tests drive a real browser against a running Ako system started with
``docker compose`` (see README.md in this folder). Settings:

- ``BASE_URL``: address of Nginx, default ``http://localhost:8080``
- ``DEMO_USERNAME`` / ``DEMO_PASSWORD``: defaults match ``server/compose.yaml``
- ``TEST_TEACHER_PASSWORD``: password of the ``teacher1`` and ``teacher2``
  test accounts (US-006), default matches ``server/compose.yaml``
- ``BROWSER_CHANNEL``: for example ``chrome`` to use the installed Google
  Chrome instead of Playwright's own Chromium
- ``COMPOSE_FILE``: the running system's compose file, default
  ``server/compose.yaml`` (used to create class sessions)

Author: Pei Wu
Date: 23 Oct 2026
"""

import os
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from learners_page import LearnersPage
from lessons_page import LessonsPage

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")
USERNAME = os.environ.get("DEMO_USERNAME", "demo")
PASSWORD = os.environ.get("DEMO_PASSWORD", "DemoPass123!")
TEACHER_PASSWORD = os.environ.get("TEST_TEACHER_PASSWORD", "TeacherPass123!")
SESSION_KEY = "ako.sessionid"
COMPOSE_FILE = os.environ.get(
    "COMPOSE_FILE", str(Path(__file__).resolve().parents[2] / "server/compose.yaml")
)
# Must match CLUB_TIMEZONE of the Accessment Service.
CLUB_TIMEZONE = "Pacific/Auckland"
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
            headers={"Authorization": f"Bearer {session_id}"},
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
        sql = (
            "INSERT INTO class_sessions (id, session_date, created_by) "
            "VALUES (gen_random_uuid(), "
            f"(now() AT TIME ZONE '{CLUB_TIMEZONE}')::date - {int(days_ago)}, "
            "gen_random_uuid()) RETURNING id"
        )
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
        return result.stdout.strip().splitlines()[0]

    return create


@pytest.fixture
def log_in_through_page(page: Page) -> Callable[[], None]:
    """Log in with the real login page, as a person would."""

    def log_in() -> None:
        page.goto("/")
        page.locator("md-outlined-text-field[name=username] input").fill(USERNAME)
        page.locator("md-outlined-text-field[name=password] input").fill(PASSWORD)
        page.locator("md-filled-button").click()
        # After signing in, the Lessons page opens (US-006).
        page.wait_for_url("**/lessons")

    return log_in


def api_login(page: Page, username: str, password: str) -> str:
    response = page.request.post(
        "/api/user/login", data={"username": username, "password": password}
    )
    assert response.ok, f"Login as {username} failed with status {response.status}"
    return response.json()["sessionid"]


@pytest.fixture
def teacher_page(page: Page) -> Page:
    """A browser window where the test teacher ``teacher1`` is logged in."""
    session = api_login(page, "teacher1", TEACHER_PASSWORD)
    page.context.add_init_script(
        f"window.localStorage.setItem({SESSION_KEY!r}, {session!r})"
    )
    return page


@pytest.fixture
def other_teacher_page(browser: Browser) -> Iterator[Page]:
    """A second, separate window where ``teacher2`` is logged in (UT-42)."""
    context = browser.new_context(
        base_url=BASE_URL, viewport={"width": 1280, "height": 900}
    )
    other = context.new_page()
    session = api_login(other, "teacher2", TEACHER_PASSWORD)
    context.add_init_script(
        f"window.localStorage.setItem({SESSION_KEY!r}, {session!r})"
    )
    yield other
    context.close()


@pytest.fixture
def lessons_page(teacher_page: Page) -> LessonsPage:
    """The Lessons pages, used by the logged-in test teacher."""
    return LessonsPage(teacher_page)
