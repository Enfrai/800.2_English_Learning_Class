"""Page object for the learner QR sign-in page on a phone, so tests read like test steps.

Author: Pei Wu
Date: 25 Oct 2026
"""

from playwright.sync_api import Page, expect

PHONE_SIZE = {"width": 360, "height": 740}  # US-012 AC6, NFR-06


class SignInPage:
    def __init__(self, page: Page) -> None:
        """
        Initialize SignInPage and retain the supplied constructor state.
        """
        self.page = page
        self.date = page.locator(".sub")
        self.first_name = page.get_by_label("First name")
        self.family_name = page.get_by_label("Family name")
        self.button = page.get_by_role("button", name="Sign in", exact=True)
        self.success = page.locator(".msg-success")
        self.info = page.locator(".msg-info")
        self.error = page.locator(".msg-error")
        self.closed = page.locator(".msg-warning")

    def open(self, token: str) -> None:
        """
        Prepare or exercise open in the sign in page test scenario.
        """
        self.page.goto(f"/sign-in/{token}")
        # Loaded when the form or the closed message shows.
        expect(
            self.page.locator("form, .msg-warning, .msg-error").first
        ).to_be_visible()

    def sign_in(self, first: str, family: str) -> None:
        """
        Prepare or exercise sign in in the sign in page test scenario.
        """
        self.first_name.fill(first)
        self.family_name.fill(family)
        self.button.click()

    def device_id(self) -> str | None:
        """
        Read the browser device identifier used by classroom sign-in.
        """
        return self.page.evaluate("localStorage.getItem('ako.signin-device')")
