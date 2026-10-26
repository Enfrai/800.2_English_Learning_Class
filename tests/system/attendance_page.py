"""Page object for the attendance (sign-in) page, so tests read like test steps.

Author: Pei Wu
Date: 23 Oct 2026
Updated: Pei Wu, 25 Oct 2026 (correction view and change history, US-015)
Updated: Pei Wu, 26 Oct 2026 (counts relative to a shared session, US-014)
"""

import re

from playwright.sync_api import Locator, Page, expect

# Learners already present when the class_session fixture handed out each
# session. Today's session is shared by tests (one session per date, US-014).
PRESENT_AT_START: dict[str, int] = {}


class AttendancePage:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.session_id = ""
        # The class list is the first table; the change history is the second.
        self.rows = page.locator("table.data").first.locator("tbody tr")
        self.count = page.locator(".stat")
        self.first_name = page.get_by_label("First name")
        self.family_name = page.get_by_label("Family name")
        self.add_and_mark_button = page.get_by_role(
            "button", name="Add and mark present"
        )
        self.add_message = page.locator("form .msg")
        self.past_warning = page.locator(".msg-warning")
        self.correction_notice = page.locator(".msg-info").filter(
            has_text="You are correcting a past class"
        )
        self.history_title = page.get_by_role("heading", name="Change history")
        self.history_rows = page.get_by_role("region", name="Change history").locator(
            "tbody tr"
        )

    def open(self, session_id: str) -> None:
        self.session_id = session_id
        self.page.goto(f"/sessions/{session_id}/attendance")
        # The page has loaded when the count or an error message shows.
        expect(self.page.locator(".stat, .msg-error").first).to_be_visible()

    def checkbox(self, full_name: str) -> Locator:
        return self.page.get_by_role("checkbox", name=full_name, exact=True)

    def row(self, full_name: str) -> Locator:
        return self.rows.filter(has=self.checkbox(full_name))

    def row_named(self, full_name: str) -> Locator:
        """A learner's row, also when the list has no tick boxes."""
        return self.rows.filter(
            has=self.page.get_by_role("cell", name=full_name, exact=True)
        )

    def expect_present_count(self, present: int) -> None:
        """Expect ``present`` more learners present than when the test began."""
        total = PRESENT_AT_START.get(self.session_id, 0) + present
        expect(self.count).to_have_text(re.compile(rf"^Present {total} of \d+$"))

    def add_and_mark(self, first: str, family: str) -> None:
        self.first_name.fill(first)
        self.family_name.fill(family)
        self.add_and_mark_button.click()
