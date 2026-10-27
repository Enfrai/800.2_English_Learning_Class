"""System tests for the Māori content review on the lesson pages (US-008).

Test Plan ST-09 done on the pages, as a teacher and a coordinator would, and
the page parts of US-008 AC1 to AC5, NT-06 and NT-10. The API-level checks
that a page cannot reach (missing Origin, logged out, a teacher flagging
another teacher's lesson) stay in test_review_flow.py.

The manual version is docs/system_test/review_system_tests.md.

Author: Pei Wu
Date: 26 Oct 2026
"""

import os

from learners_page import unique
from lessons_page import LessonPages
from playwright.sync_api import Page, expect

AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"


def run_axe(page: Page) -> list[str]:
    """
    Run the accessibility audit against the rendered page and inspect its violations.
    """
    page.add_script_tag(
        **(
            {"path": os.environ["AXE_SCRIPT_PATH"]}
            if os.getenv("AXE_SCRIPT_PATH")
            else {"url": AXE_URL}
        )
    )
    return page.evaluate(
        "async () => (await axe.run()).violations.map(v => v.id + ': ' + v.help)"
    )


# ST-09 Lesson with Māori content


def test_st09_lesson_with_maori_content_on_the_pages(
    teacher_page: Page, logged_in_page: Page
) -> None:
    """
    Verify that st09 lesson with maori content on the pages.
    """
    title = unique("Matariki")
    teacher = LessonPages(teacher_page)
    coordinator = LessonPages(logged_in_page)

    # AC1: the teacher ticks the box; the list and the page show the label.
    lesson_id = teacher.create(title, maori_content=True)
    teacher.expect_not_yet_reviewed()
    teacher.open_list()
    teacher.expect_not_yet_reviewed(teacher.list_row(title))

    # AC2: the coordinator records the review.
    coordinator.open(lesson_id)
    coordinator.record_review("Te Aroha", "2026-10-14")
    expect(logged_in_page.get_by_text("Review saved", exact=True)).to_be_visible()
    coordinator.expect_reviewed("Te Aroha", "14 Oct 2026")
    teacher.open(lesson_id)
    teacher.expect_reviewed("Te Aroha", "14 Oct 2026")

    # AC4: the teacher adds a file; the label goes back to not yet reviewed.
    teacher.add_file(lesson_id)
    teacher.expect_not_yet_reviewed()
    coordinator.open_list()
    coordinator.expect_not_yet_reviewed(coordinator.list_row(title))


def test_lesson_without_the_tick_has_no_label_or_review_form(
    teacher_page: Page, logged_in_page: Page
) -> None:
    """
    Verify that lesson without the tick has no label or review form.
    """
    lesson_id = LessonPages(teacher_page).create(unique("Bus"), maori_content=False)
    coordinator = LessonPages(logged_in_page)

    coordinator.open(lesson_id)

    expect(coordinator.pill).to_have_count(0)
    expect(coordinator.review_form).to_have_count(0)


def test_only_coordinators_see_the_review_form(
    teacher_page: Page, logged_in_page: Page
) -> None:
    """
    Verify that only coordinators see the review form.
    """
    teacher = LessonPages(teacher_page)
    lesson_id = teacher.create(unique("Waiata"), maori_content=True)
    coordinator = LessonPages(logged_in_page)

    teacher.open(lesson_id)
    coordinator.open(lesson_id)

    expect(teacher.review_form).to_have_count(0)
    expect(coordinator.review_form).to_be_visible()


# AC3: a bad review is refused and the label does not change


def test_ac3_empty_name_and_future_date_are_refused_on_the_page(
    teacher_page: Page, logged_in_page: Page
) -> None:
    """
    Verify that ac3 empty name and future date are refused on the page.
    """
    lesson_id = LessonPages(teacher_page).create(unique("Haka"), maori_content=True)
    coordinator = LessonPages(logged_in_page)
    coordinator.open(lesson_id)

    coordinator.record_review("", "2099-01-01")

    expect(logged_in_page.locator("#reviewer_name-error")).to_have_text(
        "Reviewer name is required"
    )
    expect(logged_in_page.locator("#review_date-error")).to_have_text(
        "Review date cannot be in the future"
    )
    expect(coordinator.reviewer_name).to_be_focused()
    coordinator.open(lesson_id)
    coordinator.expect_not_yet_reviewed()


def test_unticking_removes_the_label_and_the_review(
    teacher_page: Page, logged_in_page: Page
) -> None:
    """
    Verify that unticking removes the label and the review.
    """
    teacher = LessonPages(teacher_page)
    lesson_id = teacher.create(unique("Karakia"), maori_content=True)
    coordinator = LessonPages(logged_in_page)
    coordinator.open(lesson_id)
    coordinator.record_review("Aroha", "2026-10-14")
    coordinator.expect_reviewed("Aroha", "14 Oct 2026")

    teacher_page.goto(f"/lessons/{lesson_id}/edit")
    expect(
        teacher_page.get_by_text("Unticking removes the recorded review.", exact=False)
    ).to_be_visible()
    teacher.maori_content.uncheck()
    teacher.save_lesson.click()

    teacher.wait_for_lesson_page(lesson_id)
    expect(teacher.pill).to_have_count(0)
    teacher_page.goto(f"/lessons/{lesson_id}/edit")
    expect(teacher.maori_content).not_to_be_checked()


# AC5 / NT-10: macrons exactly as typed


def test_nt10_macrons_are_kept_in_the_list_and_on_the_page(
    teacher_page: Page, logged_in_page: Page
) -> None:
    """
    Verify that nt10 macrons are kept in the list and on the page.
    """
    title = unique("Te reo Māori: ā ē ī ō ū")
    teacher = LessonPages(teacher_page)
    lesson_id = teacher.create(title, maori_content=True)
    coordinator = LessonPages(logged_in_page)
    coordinator.open(lesson_id)

    coordinator.record_review("Kiri Tāmaki-Ōtene", "2026-10-08")

    coordinator.expect_reviewed("Kiri Tāmaki-Ōtene", "8 Oct 2026")
    expect(coordinator.heading(title)).to_be_visible()
    coordinator.open_list()
    row = coordinator.list_row(title)
    expect(row).to_have_count(1)
    coordinator.expect_reviewed("Kiri Tāmaki-Ōtene", "8 Oct 2026", row)


# NT-06 Plain and accessible


def test_nt06_lesson_form_and_review_form_have_no_accessibility_violations(
    teacher_page: Page, logged_in_page: Page
) -> None:
    """
    Verify that nt06 lesson form and review form have no accessibility violations.
    """
    teacher = LessonPages(teacher_page)
    lesson_id = teacher.create(unique("Matariki"), maori_content=True)
    teacher_page.goto(f"/lessons/{lesson_id}/edit")
    expect(teacher.maori_content).to_be_checked()
    coordinator = LessonPages(logged_in_page)
    coordinator.open(lesson_id)
    coordinator.record_review("", "")
    expect(logged_in_page.locator("#review_date-error")).to_be_visible()

    assert run_axe(teacher_page) == []
    assert run_axe(logged_in_page) == []


def test_nt06_review_can_be_recorded_with_the_keyboard(
    teacher_page: Page, logged_in_page: Page
) -> None:
    """
    Verify that nt06 review can be recorded with the keyboard.
    """
    lesson_id = LessonPages(teacher_page).create(unique("Pepeha"), maori_content=True)
    coordinator = LessonPages(logged_in_page)
    coordinator.open(lesson_id)

    coordinator.reviewer_name.focus()
    logged_in_page.keyboard.type("Aroha")
    logged_in_page.keyboard.press("Tab")
    coordinator.review_date.fill("2026-10-14")
    coordinator.review_date.press("Enter")

    coordinator.expect_reviewed("Aroha", "14 Oct 2026")
