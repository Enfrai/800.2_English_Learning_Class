"""System tests for the Lessons pages (US-006).

Test Plan section 5: ST-10 (lesson file rules), US-006 AC1 to AC6, UT-42 as
seen in the browser, and NFR-10 (macrons). Each test adds its own made-up
lessons, so tests run in any order and do not need an empty database. The
manual version is docs/system_test/lessons_system_tests.md.

Author: Sandhya Tiwari
Date: 23 Oct 2026
"""

from collections.abc import Callable

from playwright.sync_api import Page, expect

from lessons_page import MB, LessonsPage, exe_file, pdf_file, unique

FILE_RULE = "Files must be PDF, DOCX, JPG or PNG, from 1 KB to 10 MB"
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"


# Access


def test_logged_out_person_is_asked_to_log_in_and_sees_no_lessons(page: Page) -> None:
    page.goto("/lessons")

    expect(page.locator(".msg-error")).to_contain_text("Please log in to see the lessons")
    expect(page.locator("table.data")).to_have_count(0)


def test_signing_in_opens_the_lessons_page(
    page: Page, log_in_through_page: Callable[[], None]
) -> None:
    log_in_through_page()

    expect(page.get_by_role("heading", level=1)).to_have_text("Lessons")
    expect(page.locator('nav a[aria-current="page"]')).to_have_text("Lessons")
    expect(page.get_by_role("link", name="Add lesson")).to_be_visible()


# AC1 and NFR-10


def test_ac1_saved_lesson_appears_in_the_list_with_date_and_tags(
    lessons_page: LessonsPage,
) -> None:
    title = unique("Catching the bus")

    lessons_page.add(title, "2026-10-21", ("Transport", "Health"))
    lessons_page.open_list()

    row = lessons_page.row(title)
    expect(row).to_have_count(1)
    expect(row).to_contain_text("21 Oct 2026")
    expect(row.locator(".chip")).to_have_text(["Transport", "Health"])


def test_title_with_a_macron_shows_exactly_as_typed(lessons_page: LessonsPage) -> None:
    title = unique("Te reo Māori")

    lessons_page.add(title)
    lessons_page.open_list()

    expect(lessons_page.row(title)).to_have_count(1)


def test_lessons_are_shared_with_other_teachers_without_edit(
    lessons_page: LessonsPage, other_teacher_page: Page
) -> None:
    title = unique("Shared lesson")
    lessons_page.add(title)

    other = LessonsPage(other_teacher_page)
    other.open_list()

    row = other.row(title)
    expect(row).to_have_count(1)
    expect(row.get_by_role("link", name=f"Edit {title}")).to_have_count(0)


# AC2


def test_ac2_empty_title_shows_title_is_required_and_saves_nothing(
    lessons_page: LessonsPage,
) -> None:
    lessons_page.open_new()
    lessons_page.fill("", "2026-10-21", ("Transport",))

    lessons_page.save_button.click()

    expect(lessons_page.field_error("title")).to_have_text("Title is required")
    expect(lessons_page.page).to_have_url("/lessons/new")


def test_missing_date_and_tag_show_their_messages(lessons_page: LessonsPage) -> None:
    lessons_page.open_new()
    lessons_page.title.fill(unique("No date"))

    lessons_page.save_button.click()

    expect(lessons_page.field_error("date")).to_have_text("Lesson date is required")
    expect(lessons_page.field_error("tags")).to_have_text("Choose at least one topic tag")


# AC3


def test_ac3_pdf_of_10_mb_downloads_with_the_same_name(lessons_page: LessonsPage) -> None:
    lessons_page.add(unique("With a PDF"), files=[pdf_file("Bus timetable.pdf", 10 * MB)])
    row = lessons_page.file_row("Bus timetable.pdf")
    expect(row).to_have_count(1)

    with lessons_page.page.expect_download() as download_info:
        row.get_by_role("button", name="Download Bus timetable.pdf").click()

    assert download_info.value.suggested_filename == "Bus timetable.pdf"


def test_share_with_learners_is_off_by_default(lessons_page: LessonsPage) -> None:
    lessons_page.add(unique("Sharing"), files=[pdf_file("worksheet.pdf", 4096)])

    expect(lessons_page.page.get_by_label("Share worksheet.pdf with learners")).not_to_be_checked()


# AC4 and ST-10


def test_st10_large_file_and_exe_are_refused_and_details_are_kept(
    lessons_page: LessonsPage,
) -> None:
    title = unique("File rules")
    lessons_page.open_new()
    lessons_page.fill(title, "2026-10-21", ("Shopping",))

    lessons_page.files.set_input_files([pdf_file("big.pdf", int(10.1 * MB)), exe_file()])

    expect(lessons_page.field_error("files")).to_contain_text(FILE_RULE)
    expect(lessons_page.field_error("files")).to_contain_text("big.pdf")
    expect(lessons_page.field_error("files")).to_contain_text("setup.exe")
    expect(lessons_page.title).to_have_value(title)
    expect(lessons_page.lesson_date).to_have_value("2026-10-21")
    expect(lessons_page.tag("Shopping")).to_be_checked()
    expect(lessons_page.page.get_by_role("table", name="Files to upload")).to_have_count(0)


# AC5


def test_ac5_edited_title_is_listed_and_date_and_files_are_unchanged(
    lessons_page: LessonsPage,
) -> None:
    title = unique("Old title")
    new_title = unique("New title")
    lesson_id = lessons_page.add(title, "2026-09-30", files=[pdf_file("notes.pdf", 4096)])

    lessons_page.page.goto(f"/lessons/{lesson_id}/edit")
    expect(lessons_page.title).to_have_value(title)
    lessons_page.title.fill(new_title)
    lessons_page.save_button.click()

    expect(lessons_page.success).to_have_text("Lesson saved")
    expect(lessons_page.page.locator(".sub")).to_have_text("30 Sept 2026")
    expect(lessons_page.file_row("notes.pdf")).to_have_count(1)
    lessons_page.open_list()
    expect(lessons_page.row(new_title)).to_contain_text("30 Sept 2026")
    expect(lessons_page.row(title)).to_have_count(0)


# AC6


def test_ac6_deleted_lesson_leaves_the_list(lessons_page: LessonsPage) -> None:
    title = unique("To delete")
    lessons_page.add(title, files=[pdf_file("old.pdf", 4096)])
    page = lessons_page.page

    page.get_by_role("button", name="Delete lesson").click()
    expect(page.get_by_role("alertdialog")).to_contain_text("its files can no longer be downloaded")
    page.get_by_role("button", name="Yes, delete").click()

    expect(page).to_have_url("/lessons?notice=deleted")
    expect(lessons_page.success).to_have_text("Lesson deleted")
    expect(lessons_page.row(title)).to_have_count(0)


def test_cancel_on_the_delete_warning_changes_nothing(lessons_page: LessonsPage) -> None:
    title = unique("Keep me")
    lessons_page.add(title)
    page = lessons_page.page

    page.get_by_role("button", name="Delete lesson").click()
    page.get_by_role("button", name="Cancel").click()

    expect(page.get_by_role("alertdialog")).to_have_count(0)
    lessons_page.open_list()
    expect(lessons_page.row(title)).to_have_count(1)


# UT-42 in the browser


def test_other_teacher_typing_the_edit_address_sees_no_permission(
    lessons_page: LessonsPage, other_teacher_page: Page
) -> None:
    lesson_id = lessons_page.add(unique("Not yours"))

    other_teacher_page.goto(f"/lessons/{lesson_id}/edit")

    expect(other_teacher_page.locator(".msg-error")).to_have_text("You do not have permission")
    expect(other_teacher_page.locator("form")).to_have_count(0)
    other_teacher_page.goto(f"/lessons/{lesson_id}")
    expect(other_teacher_page.get_by_role("button", name="Delete lesson")).to_have_count(0)


# NT-06 Accessibility


def test_nt06_lesson_form_with_errors_has_no_accessibility_violations(
    lessons_page: LessonsPage,
) -> None:
    lessons_page.open_new()
    lessons_page.files.set_input_files([exe_file()])
    lessons_page.save_button.click()
    page = lessons_page.page
    expect(lessons_page.field_error("title")).to_be_visible()

    page.add_script_tag(url=AXE_URL)
    violations = page.evaluate(
        "async () => (await axe.run()).violations.map(v => v.id + ': ' + v.help)"
    )

    assert violations == []


def test_nt06_lesson_page_has_no_accessibility_violations(
    lessons_page: LessonsPage,
) -> None:
    lessons_page.add(unique("Accessible"), files=[pdf_file("notes.pdf", 4096)])
    page = lessons_page.page

    page.add_script_tag(url=AXE_URL)
    violations = page.evaluate(
        "async () => (await axe.run()).violations.map(v => v.id + ': ' + v.help)"
    )

    assert violations == []
