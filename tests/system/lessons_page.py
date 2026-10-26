"""Page object for the lesson pages (US-006) with the Māori content review
(US-008), so tests read like the test steps.

Author: Pei Wu
Date: 26 Oct 2026
"""

import re

from playwright.sync_api import Locator, Page, expect

NOT_YET_REVIEWED = "Māori content – not yet reviewed"
# A tiny file the Lesson service accepts as a PDF.
HANDOUT = {
    "name": "handout.pdf",
    "mimeType": "application/pdf",
    "buffer": b"%PDF-1.7 test",
}


class LessonPages:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.title = page.get_by_label("Title", exact=True)
        self.lesson_date = page.get_by_label("Lesson date", exact=True)
        self.topic_tags = page.get_by_label("Topic tags", exact=True)
        self.maori_content = page.get_by_role(
            "checkbox", name="Contains Māori content", exact=True
        )
        self.materials = page.get_by_label("Add materials (optional)")
        self.save_lesson = page.get_by_role("button", name="Save lesson", exact=True)
        # Amber "not yet reviewed" or green "Reviewed by" (UI design 6.10).
        self.pill = page.locator(".badge-review, .badge-reviewed")
        self.review_form = page.get_by_role("region", name="Record a review")
        self.reviewer_name = page.get_by_label("Reviewer name")
        self.review_date = page.get_by_label("Review date")
        self.save_review = page.get_by_role("button", name="Save review", exact=True)

    def create(self, title: str, *, maori_content: bool) -> str:
        """Add a lesson through the form and return its id."""
        self.page.goto("/lessons/new")
        self.title.fill(title)
        self.lesson_date.fill("2026-10-20")
        self.topic_tags.fill("culture")
        self.maori_content.set_checked(maori_content)
        self.save_lesson.click()
        expect(self.heading(title)).to_be_visible()
        return self.page.url.rstrip("/").split("/")[-1]

    def open(self, lesson_id: str) -> None:
        self.page.goto(f"/lessons/{lesson_id}")
        expect(self.page.get_by_role("heading", name="Materials")).to_be_visible()

    def open_list(self) -> None:
        self.page.goto("/lessons")
        expect(self.page.locator("table.data, .msg-info").first).to_be_visible()

    def add_file(self, lesson_id: str) -> None:
        """Attach a file through the edit form, as a teacher would."""
        self.page.goto(f"/lessons/{lesson_id}/edit")
        self.materials.set_input_files(HANDOUT)
        self.save_lesson.click()
        self.wait_for_lesson_page(lesson_id)
        expect(self.page.get_by_role("link", name=HANDOUT["name"])).to_be_visible()

    def wait_for_lesson_page(self, lesson_id: str) -> None:
        """Saving the form opens the lesson page. The form also has a
        "Materials" heading, so wait for the address instead."""
        self.page.wait_for_url(re.compile(rf"/lessons/{lesson_id}$"))
        expect(self.page.get_by_role("heading", name="Materials")).to_be_visible()

    def record_review(self, name: str, date: str) -> None:
        self.reviewer_name.fill(name)
        self.review_date.fill(date)
        self.save_review.click()

    def heading(self, title: str) -> Locator:
        return self.page.get_by_role("heading", name=title, exact=True)

    def list_row(self, title: str) -> Locator:
        return self.page.locator("table.data tbody tr").filter(
            has=self.page.get_by_role("link", name=title, exact=True)
        )

    def expect_not_yet_reviewed(self, where: Locator | None = None) -> None:
        pill = (where or self.page).locator(".badge-review")
        expect(pill).to_have_text(NOT_YET_REVIEWED)

    def expect_reviewed(
        self, name: str, shown_date: str, where: Locator | None = None
    ) -> None:
        pill = (where or self.page).locator(".badge-reviewed")
        expect(pill).to_have_text(
            re.compile(rf"^Reviewed by {re.escape(name)}, {shown_date}$")
        )
