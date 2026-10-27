"""Page object for the Learners page, so tests read like the test steps.

Author: Pei Wu
Date: 23 Oct 2026
"""

from uuid import uuid4

from playwright.sync_api import Locator, Page, expect


def unique(name: str) -> str:
    """Add a short random suffix so each test has its own learners."""
    return f"{name}-{uuid4().hex[:6]}"


class LearnersPage:
    def __init__(self, page: Page) -> None:
        """
        Initialize LearnersPage and retain the supplied constructor state.
        """
        self.page = page
        self.rows = page.locator("table.data tbody tr")
        self.add_button = page.get_by_role("button", name="Add learner")
        self.save_button = page.locator("form").get_by_role(
            "button", name="Save", exact=True
        )
        self.form_cancel_button = page.locator("form > .row").get_by_role(
            "button", name="Cancel"
        )
        self.duplicate_warning = page.locator(".msg-warning")
        self.saved_message = page.locator(".msg-success")
        self.first_name = page.get_by_label("First name")
        self.family_name = page.get_by_label("Family name")
        self.first_language = page.get_by_label("First language")
        self.contact = page.get_by_label("Phone or email")

    def open(self) -> None:
        """
        Prepare or exercise open in the learners page test scenario.
        """
        self.page.goto("/learners")
        # The list has loaded when the table or the "no learners" note shows.
        expect(self.page.locator("table.data, .msg-info").first).to_be_visible()

    def row(self, full_name: str) -> Locator:
        """
        Locate the learner or lesson table row used by this page interaction.
        """
        return self.rows.filter(
            has=self.page.get_by_role("cell", name=full_name, exact=True)
        )

    def field_error(self, field: str) -> Locator:
        """
        Locate the validation message associated with the requested learner field.
        """
        return self.page.locator(f"#learner-{field}-error")

    def fill(
        self, first: str, family: str, language: str = "", contact: str = ""
    ) -> None:
        """
        Populate the learner form with the supplied fictional record fields.
        """
        self.first_name.fill(first)
        self.family_name.fill(family)
        self.first_language.fill(language)
        self.contact.fill(contact)

    def add(
        self, first: str, family: str, language: str = "", contact: str = ""
    ) -> None:
        """Add a learner through the form and wait until it is listed."""
        self.add_button.click()
        self.fill(first, family, language, contact)
        self.save_button.click()
        expect(self.row(f"{first} {family}")).to_have_count(1)
