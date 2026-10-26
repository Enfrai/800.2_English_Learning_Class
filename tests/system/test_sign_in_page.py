"""System tests for learner QR sign-in on a phone (US-012).

Test Plan section 5: ST-14 from the teacher opening check-in to closing it
(US-011, US-012, US-013), US-012 AC1 to AC6, and the sign-in parts of NT-06
and NT-11. Phones are 360 px wide with no login. ST-14 opens and closes
check-in on the class page; the other tests use the ``check_in`` fixture,
which calls the same US-011 endpoints.

The manual version is docs/system_test/sign_in_system_tests.md.

Author: Pei Wu
Date: 25 Oct 2026
Updated: Pei Wu, 26 Oct 2026 (materials link from US-013; full ST-14 with
US-011 and US-013)
"""

import os
import re
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from api import BASE_URL
from attendance_page import AttendancePage
from learners_page import unique
from playwright.sync_api import Browser, Page, expect
from setup_data import ORIGIN, CheckIn, access_sql
from sign_in_page import PHONE_SIZE, SignInPage

AddLearner = Callable[..., dict[str, Any]]
ClassSession = Callable[..., str]
Phone = Callable[[], SignInPage]

NOT_FOUND = "We could not find that name. Please ask the teacher"
CLOSED = "Check-in is closed. Please ask the teacher"
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"


@pytest.fixture
def phone(browser: Browser) -> Iterator[Phone]:
    """A new phone each call: its own browser storage and no login."""
    contexts = []

    def create() -> SignInPage:
        context = browser.new_context(base_url=BASE_URL, viewport=PHONE_SIZE)
        contexts.append(context)
        return SignInPage(context.new_page())

    yield create
    for context in contexts:
        context.close()


def present_on_teachers_list(teacher: Page, session_id: str, learner: str) -> None:
    attendance = AttendancePage(teacher)
    attendance.open(session_id)
    expect(attendance.checkbox(learner)).to_be_checked()


# ST-14 QR check-in, from the teacher opening it to closing it


def share_a_lesson_with_the_class(staff: Page, session_id: str) -> str:
    """Link a lesson with one file shared with learners; return the file name."""
    handout = f"{unique('Bus timetable')}.pdf"
    lesson = staff.request.post(
        "/api/staff/lesson/lessons",
        headers=ORIGIN,
        data={
            "title": unique("Using the bus"),
            "lesson_date": "2026-10-20",
            "tags": ["transport"],
        },
    )
    assert lesson.status == 201, lesson.text()
    lesson_id = lesson.json()["id"]
    upload = staff.request.post(
        f"/api/staff/lesson/lessons/{lesson_id}/materials",
        headers=ORIGIN,
        multipart={
            "file": {
                "name": handout,
                "mimeType": "application/pdf",
                "buffer": b"%PDF-1.7 test",
            },
            "share_with_learners": "true",
        },
    )
    assert upload.status == 201, upload.text()
    link = staff.request.put(
        f"/api/staff/access/sessions/{session_id}/lesson",
        headers=ORIGIN,
        data={"lesson_id": lesson_id},
    )
    assert link.ok, link.text()
    return handout


def test_st14_qr_check_in_from_opening_to_closing(
    phone: Phone,
    teacher_page: Page,
    logged_in_page: Page,
    add_learner: AddLearner,
    class_session: ClassSession,
    check_in: CheckIn,
) -> None:
    family = unique("Ngata")
    add_learner("Aroha", family)
    session_id = class_session()
    handout = share_a_lesson_with_the_class(logged_in_page, session_id)
    check_in.close(session_id)  # Start with check-in closed.

    # US-011: the teacher opens check-in on the class page.
    teacher_page.goto(f"/sessions/{session_id}")
    teacher_page.get_by_role("button", name="Open check-in", exact=True).click()
    expect(teacher_page.get_by_alt_text("QR code for class sign-in")).to_be_visible()
    code = teacher_page.locator("a[href*='/sign-in/']").get_attribute("href")
    assert code
    token = code.rsplit("/", 1)[1]

    # US-012: a phone scans the code and signs in; the teacher sees Present.
    learner = phone()
    learner.open(token)
    start = time.perf_counter()
    learner.sign_in("Aroha", family)
    expect(learner.success).to_have_text("You are signed in")
    present_on_teachers_list(teacher_page, session_id, f"Aroha {family}")
    seconds = time.perf_counter() - start
    assert seconds <= 10, f"Present after {seconds:.1f}s"

    # US-013: the phone opens the lesson materials and downloads the file.
    learner.page.get_by_role("link", name="Lesson materials", exact=True).click()
    learner.page.wait_for_url("**/materials")
    download_link = learner.page.get_by_role(
        "link", name=re.compile(rf"^Download {re.escape(handout)}")
    )
    with learner.page.expect_download() as download:
        download_link.click()
    assert download.value.suggested_filename == handout

    # US-011: the teacher closes check-in; scanning again shows the closed message.
    teacher_page.goto(f"/sessions/{session_id}")
    teacher_page.get_by_role("button", name="Close check-in", exact=True).click()
    expect(
        teacher_page.get_by_role("status").filter(has_text="Check-in is closed")
    ).to_be_visible()
    learner.open(token)
    expect(learner.closed).to_have_text(CLOSED)
    expect(learner.first_name).to_have_count(0)
    # Closing check-in does not take away materials already opened (US-013).
    learner.page.goto("/materials")
    expect(download_link).to_be_visible()


# US-012 acceptance criteria on the phone


def test_ac1_page_shows_the_class_date_with_no_login_or_staff_menu(
    phone: Phone, class_session: ClassSession, check_in: CheckIn
) -> None:
    learner = phone()

    learner.open(check_in.open(class_session()))

    expect(learner.page.get_by_role("heading", name="Sign in to class")).to_be_visible()
    expect(learner.date).to_contain_text(" 20")
    expect(learner.page.locator("header.bar")).to_have_count(0)
    assert learner.page.context.cookies() == []


def test_ac2_name_typed_without_macrons_signs_in(
    phone: Phone,
    add_learner: AddLearner,
    class_session: ClassSession,
    check_in: CheckIn,
) -> None:
    family = unique("Māhina")
    add_learner("Tāne", family)
    learner = phone()
    learner.open(check_in.open(class_session()))

    learner.sign_in("tane", family.replace("ā", "a").upper())

    expect(learner.success).to_have_text("You are signed in")
    # US-013 replaced the greyed "Lesson materials (later)" button with a link.
    expect(
        learner.page.get_by_role("link", name="Lesson materials", exact=True)
    ).to_have_attribute("href", "/materials")


def test_ac3_unknown_name_asks_for_the_teacher(
    phone: Phone, class_session: ClassSession, check_in: CheckIn
) -> None:
    learner = phone()
    learner.open(check_in.open(class_session()))

    learner.sign_in("Nobody", unique("Here"))

    expect(learner.error).to_have_text(NOT_FOUND)
    expect(learner.first_name).to_be_focused()


def test_name_shared_by_two_learners_asks_for_the_teacher(
    phone: Phone,
    add_learner: AddLearner,
    class_session: ClassSession,
    check_in: CheckIn,
) -> None:
    family = unique("Walker")
    add_learner("Mere", family)
    add_learner("Mere", family)
    learner = phone()
    learner.open(check_in.open(class_session()))

    learner.sign_in("Mere", family)

    expect(learner.error).to_have_text(NOT_FOUND)


def test_ac4_second_sign_in_says_already_signed_in(
    phone: Phone,
    add_learner: AddLearner,
    class_session: ClassSession,
    check_in: CheckIn,
) -> None:
    family = unique("Silva")
    add_learner("Ana", family)
    token = check_in.open(class_session())
    learner = phone()
    learner.open(token)
    learner.sign_in("Ana", family)
    expect(learner.success).to_be_visible()

    learner.open(token)
    learner.sign_in("Ana", family)

    expect(learner.info).to_have_text("Already signed in")


@pytest.mark.parametrize("closed", [True, False], ids=["closed", "unknown code"])
def test_ac5_closed_or_unknown_code_shows_the_closed_message(
    phone: Phone, class_session: ClassSession, check_in: CheckIn, closed: bool
) -> None:
    session_id = class_session()
    token = check_in.open(session_id)
    if closed:
        check_in.close(session_id)
    learner = phone()

    learner.open(token if closed else "made-up-token")

    expect(learner.closed).to_have_text(CLOSED)
    expect(learner.first_name).to_have_count(0)


def test_empty_names_are_refused_on_the_phone_and_not_counted(
    phone: Phone, class_session: ClassSession, check_in: CheckIn
) -> None:
    learner = phone()
    learner.open(check_in.open(class_session()))

    learner.button.click()

    expect(learner.page.locator("#learner-first-name-error")).to_have_text(
        "First name is required"
    )
    expect(learner.page.locator("#learner-family-name-error")).to_have_text(
        "Family name is required"
    )
    assert access_sql("SELECT count(*) FROM signin_failures") == "0"


# AC6 and NT-06 on a 360 px phone


def test_ac6_nt06_page_fits_a_360px_phone_with_large_text_and_buttons(
    phone: Phone, class_session: ClassSession, check_in: CheckIn
) -> None:
    learner = phone()
    learner.open(check_in.open(class_session()))

    sizes = learner.page.evaluate(
        """() => ({
            scroll: document.documentElement.scrollWidth,
            width: innerWidth,
            body: getComputedStyle(document.body).fontSize,
            small: [...document.querySelectorAll('button, input')]
                .filter(e => e.getBoundingClientRect().height < 44)
                .map(e => e.id || e.textContent),
        })"""
    )

    assert sizes["scroll"] <= sizes["width"] == 360
    assert sizes["body"] == "18px"
    assert sizes["small"] == []


def test_nt06_sign_in_page_has_no_accessibility_violations(
    phone: Phone, class_session: ClassSession, check_in: CheckIn
) -> None:
    learner = phone()
    learner.open(check_in.open(class_session()))

    learner.page.add_script_tag(
        **(
            {"path": os.environ["AXE_SCRIPT_PATH"]}
            if os.getenv("AXE_SCRIPT_PATH")
            else {"url": AXE_URL}
        )
    )
    violations = learner.page.evaluate(
        "async () => (await axe.run()).violations.map(v => v.id + ': ' + v.help)"
    )

    assert violations == []


def test_sign_in_address_is_not_indexed_or_sent_to_other_sites(
    phone: Phone, class_session: ClassSession, check_in: CheckIn
) -> None:
    learner = phone()
    learner.open(check_in.open(class_session()))

    meta = learner.page.evaluate(
        """() => ({
            robots: document.querySelector('meta[name=robots]')?.content,
            referrer: document.querySelector('meta[name=referrer]')?.content,
        })"""
    )

    assert meta == {"robots": "noindex, nofollow", "referrer": "no-referrer"}


# NT-11 wrong-name limit, per phone


def test_nt11_one_phone_is_blocked_but_a_classmate_on_the_same_wifi_is_not(
    phone: Phone,
    add_learner: AddLearner,
    class_session: ClassSession,
    check_in: CheckIn,
) -> None:
    family = unique("Silva")
    add_learner("Ana", family)
    token = check_in.open(class_session())
    guesser, classmate = phone(), phone()
    guesser.open(token)
    classmate.open(token)
    for n in range(10):
        guesser.sign_in(f"Guess{n}", "X")
        expect(guesser.error).to_have_text(NOT_FOUND)
        # Each answer replaces the last one; wait so the next check sees a new one.
        guesser.page.wait_for_timeout(100)

    guesser.sign_in("Ana", family)
    expect(guesser.error).to_have_text("Too many tries. Please ask the teacher")

    classmate.sign_in("Ana", family)
    expect(classmate.success).to_have_text("You are signed in")
    assert guesser.device_id() and guesser.device_id() != classmate.device_id()
