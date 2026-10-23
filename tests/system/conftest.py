"""Shared fixtures for browser system tests.

The tests drive a real browser against a running Ako system started with
``docker compose`` (see README.md in this folder). Settings:

- ``BASE_URL``: address of Nginx, default ``http://localhost:8080``
- ``DEMO_USERNAME`` / ``DEMO_PASSWORD``: defaults match ``server/compose.yaml``
- ``BROWSER_CHANNEL``: for example ``chrome`` to use the installed Google
  Chrome instead of Playwright's own Chromium

Author: Pei Wu
Date: 23 Oct 2026
"""

import os
from collections.abc import Callable, Iterator

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from learners_page import LearnersPage

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")
USERNAME = os.environ.get("DEMO_USERNAME", "demo")
PASSWORD = os.environ.get("DEMO_PASSWORD", "DemoPass123!")
SESSION_KEY = "ako.sessionid"

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
def learners_page(page: Page, session_id: str) -> LearnersPage:
    """The Learners page, opened by a logged-in coordinator."""
    page.context.add_init_script(
        f"window.localStorage.setItem({SESSION_KEY!r}, {session_id!r})"
    )
    learners = LearnersPage(page)
    learners.open()
    return learners


@pytest.fixture
def log_in_through_page(page: Page) -> Callable[[], None]:
    """Log in with the real login page, as a person would."""

    def log_in() -> None:
        page.goto("/")
        page.locator("md-outlined-text-field[name=username] input").fill(USERNAME)
        page.locator("md-outlined-text-field[name=password] input").fill(PASSWORD)
        page.locator("md-filled-button").click()
        expect(page.get_by_text("Login successful")).to_be_visible()

    return log_in
