"""Page object for the Lessons pages, so tests read like the test steps.

Author: Sandhya Tiwari
Date: 23 Oct 2026
"""

from uuid import uuid4

from playwright.sync_api import Locator, Page, expect

KB = 1024
MB = 1024 * KB


def unique(title: str) -> str:
    """Add a short random suffix so each test has its own lessons."""
    return f"{title} {uuid4().hex[:6]}"


def pdf_file(name: str, size: int) -> dict:
    """A made-up PDF of the given size, for set_input_files."""
    head = b"%PDF-1.7\n"
    return {"name": name, "mimeType": "application/pdf", "buffer": head + b"0" * (size - len(head))}


def exe_file(name: str = "setup.exe") -> dict:
    return {
        "name": name,
        "mimeType": "application/octet-stream",
        "buffer": b"MZ" + b"0" * (4 * KB),
    }


class LessonsPage:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.rows = page.locator("table.data tbody tr")
        self.title = page.get_by_label("Title")
        self.lesson_date = page.get_by_label("Lesson date")
        self.files = page.locator("#lesson-files")
        self.save_button = page.locator("form").get_by_role("button", name="Save", exact=True)
        self.success = page.locator(".msg-success")

    def open_list(self) -> None:
        self.page.goto("/lessons")
        # The list has loaded when the table or the "no lessons" note shows.
        expect(self.page.locator("table.data, .msg-info").first).to_be_visible()

    def open_new(self) -> None:
        self.page.goto("/lessons/new")
        # The tag list comes from the server; wait for it.
        expect(self.tag("Transport")).to_be_visible()

    def tag(self, name: str) -> Locator:
        return self.page.get_by_role("checkbox", name=name, exact=True)

    def field_error(self, field: str) -> Locator:
        return self.page.locator(f"#lesson-{field}-error")

    def row(self, title: str) -> Locator:
        return self.rows.filter(has=self.page.get_by_role("link", name=title, exact=True))

    def fill(self, title: str, lesson_date: str = "2026-10-21", tags: tuple[str, ...] = ("Transport",)) -> None:
        self.title.fill(title)
        self.lesson_date.fill(lesson_date)
        for name in tags:
            self.tag(name).check()

    def add(
        self,
        title: str,
        lesson_date: str = "2026-10-21",
        tags: tuple[str, ...] = ("Transport",),
        files: list[dict] | None = None,
    ) -> str:
        """Add a lesson through the form; return its id once its page shows."""
        self.open_new()
        self.fill(title, lesson_date, tags)
        if files:
            self.files.set_input_files(files)
        self.save_button.click()
        expect(self.success).to_have_text("Lesson saved")
        expect(self.page.get_by_role("heading", level=1)).to_have_text(title)
        return self.page.url.split("/lessons/")[1].split("?")[0]

    def file_row(self, file_name: str) -> Locator:
        return self.rows.filter(has=self.page.get_by_role("cell", name=file_name, exact=True))
