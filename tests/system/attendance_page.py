"""Page object for the attendance (sign-in) page, so tests read like test steps.

Author: Pei Wu
Date: 23 Oct 2026
"""

import re

from playwright.sync_api import Locator, Page, expect


class AttendancePage:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.rows = page.locator("table.data tbody tr")
        self.count = page.locator(".stat")
        self.first_name = page.get_by_label("First name")
        self.family_name = page.get_by_label("Family name")
        self.add_and_mark_button = page.get_by_role(
            "button", name="Add and mark present"
        )
        self.add_message = page.locator("form .msg")
        self.past_warning = page.locator(".msg-warning")

    def open(self, session_id: str) -> None:
        self.page.goto(f"/sessions/{session_id}/attendance")
        # The page has loaded when the count or an error message shows.
        expect(self.page.locator(".stat, .msg-error").first).to_be_visible()

    def checkbox(self, full_name: str) -> Locator:
        return self.page.get_by_role("checkbox", name=full_name, exact=True)

    def row(self, full_name: str) -> Locator:
        return self.rows.filter(has=self.checkbox(full_name))

    def expect_present_count(self, present: int) -> None:
        expect(self.count).to_have_text(re.compile(rf"^Present {present} of \d+$"))

    def add_and_mark(self, first: str, family: str) -> None:
        self.first_name.fill(first)
        self.family_name.fill(family)
        self.add_and_mark_button.click()
