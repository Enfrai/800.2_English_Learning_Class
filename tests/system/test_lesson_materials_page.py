"""System tests for teacher access to lesson materials (the story after US-006).

AC1: a signed-in teacher sees shared lessons and their files. AC2: they can
open or download the files. AC3: a visitor who is not signed in, or whose
session has ended, sees no lesson titles or file names, even from a direct
link. Each test adds its own made-up lessons. The manual version is
docs/system_test/lesson_materials_system_tests.md.

Author: Sandhya Tiwari
Date: 24 Oct 2026
"""

from playwright.sync_api import Browser, Page, expect

from conftest import BASE_URL, SESSION_KEY, TEACHER_PASSWORD, api_login
from lessons_page import LessonsPage, pdf_file, unique

PNG = {
    "name": "bus stop.png",
    "mimeType": "image/png",
    "buffer": b"\x89PNG\r\n\x1a\n" + b"0" * 2048,
}


def new_visitor(browser: Browser) -> Page:
    """A separate window with no sign-in."""
    context = browser.new_context(base_url=BASE_URL, viewport={"width": 1280, "height": 900})
    return context.new_page()


# AC1


def test_ac1_other_teacher_sees_the_lesson_with_its_file_count(
    lessons_page: LessonsPage, other_teacher_page: Page
) -> None:
    title = unique("Shared materials")
    lessons_page.add(title, files=[pdf_file("a.pdf", 4096), pdf_file("b.pdf", 4096)])

    other = LessonsPage(other_teacher_page)
    other.open_list()

    row = other.row(title)
    expect(row).to_have_count(1)
    expect(row.locator("td").nth(3)).to_have_text("2")


# AC2


def test_ac2_other_teacher_can_open_a_picture_in_a_new_tab(
    lessons_page: LessonsPage, other_teacher_page: Page
) -> None:
    # A picture, because the headless test browser has no PDF viewer; the
    # manual script checks a PDF in a real browser.
    lesson_id = lessons_page.add(unique("Open me"), files=[PNG])

    other_teacher_page.goto(f"/lessons/{lesson_id}")
    with other_teacher_page.expect_popup() as popup_info:
        other_teacher_page.get_by_role("button", name="Open bus stop.png").click()

    tab = popup_info.value
    tab.wait_for_url(lambda url: url.startswith("blob:"), wait_until="commit")
    assert tab.url.startswith("blob:http")


def test_pdf_offers_open_and_download(lessons_page: LessonsPage) -> None:
    lessons_page.add(unique("PDF buttons"), files=[pdf_file("worksheet.pdf", 4096)])
    page = lessons_page.page

    expect(page.get_by_role("button", name="Open worksheet.pdf")).to_be_visible()
    expect(page.get_by_role("button", name="Download worksheet.pdf")).to_be_visible()


def test_ac2_other_teacher_can_download_with_the_same_name(
    lessons_page: LessonsPage, other_teacher_page: Page
) -> None:
    lesson_id = lessons_page.add(unique("Download me"), files=[PNG])

    other_teacher_page.goto(f"/lessons/{lesson_id}")
    with other_teacher_page.expect_download() as download_info:
        other_teacher_page.get_by_role("button", name="Download bus stop.png").click()

    assert download_info.value.suggested_filename == "bus stop.png"


def test_word_files_offer_download_only(lessons_page: LessonsPage) -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<document>" + "x" * 2000 + "</document>")
    docx = {
        "name": "notes.docx",
        "mimeType": "application/octet-stream",
        "buffer": buffer.getvalue(),
    }

    lessons_page.add(unique("Word file"), files=[docx])
    page = lessons_page.page

    expect(page.get_by_role("button", name="Download notes.docx")).to_be_visible()
    expect(page.get_by_role("button", name="Open notes.docx")).to_have_count(0)


# AC3


def test_ac3_direct_link_without_sign_in_shows_no_title_or_file_names(
    lessons_page: LessonsPage, browser: Browser
) -> None:
    title = unique("Private lesson")
    lesson_id = lessons_page.add(title, files=[pdf_file("Private notes.pdf", 4096)])
    visitor = new_visitor(browser)

    for address in (f"/lessons/{lesson_id}", f"/lessons/{lesson_id}/edit", "/lessons"):
        visitor.goto(address)
        expect(visitor.locator(".msg-error")).to_contain_text("Please log in")
        expect(visitor.locator("body")).not_to_contain_text(title)
        expect(visitor.locator("body")).not_to_contain_text("Private notes.pdf")

    visitor.context.close()


def test_ac3_file_address_without_sign_in_is_refused(
    lessons_page: LessonsPage, browser: Browser
) -> None:
    lesson_id = lessons_page.add(unique("No peeking"), files=[pdf_file("Hidden.pdf", 4096)])
    lessons_page.page.reload()
    material_id = lessons_page.page.evaluate(
        "async (id) => (await (await fetch('/api/lesson/lessons/' + id, {headers: "
        "{Authorization: 'Bearer ' + localStorage.getItem('ako.sessionid')}})).json())"
        ".materials[0].id",
        lesson_id,
    )
    visitor = new_visitor(browser)

    response = visitor.request.get(f"/api/lesson/materials/{material_id}/download")

    assert response.status == 401
    assert "Hidden.pdf" not in response.text()
    visitor.context.close()


def test_ac3_after_log_out_the_old_session_no_longer_works(browser: Browser) -> None:
    context = browser.new_context(base_url=BASE_URL, viewport={"width": 1280, "height": 900})
    page = context.new_page()
    session = api_login(page, "teacher2", TEACHER_PASSWORD)
    context.add_init_script(f"window.localStorage.setItem({SESSION_KEY!r}, {session!r})")
    LessonsPage(page).open_list()

    page.get_by_role("link", name="Log out").click()
    page.wait_for_url("/")

    response = page.request.get(
        "/api/lesson/lessons", headers={"Authorization": f"Bearer {session}"}
    )
    assert response.status == 401
    context.close()
