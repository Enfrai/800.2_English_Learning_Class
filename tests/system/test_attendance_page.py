"""System tests for the attendance (sign-in) page (US-004).

Test Plan section 5: ST-01 and the attendance-page parts of NT-01, NT-06,
NT-07 and NT-10. Each test uses its own class session and made-up learners,
so tests run in any order and do not need an empty database.

ST-01 is done as in the Test Plan: a teacher account (US-002) logs in,
chooses "Start today's class" (US-014) and opens the class's attendance
list. The other tests get their class from the ``class_session`` fixture,
which uses the same US-014 endpoints, and the demo coordinator takes
attendance; both roles may.

Past classes (US-015) are tested in test_corrections_page.py.

The manual version is docs/system_test/attendance_system_tests.md.

Author: Pei Wu
Date: 23 Oct 2026
Updated: Pei Wu, 25 Oct 2026 (past-class test moved to test_corrections_page.py)
Updated: Pei Wu, 26 Oct 2026 (ST-01 as a teacher with "Start today's class")
"""

import os
import re
import time
from collections.abc import Callable
from typing import Any

from api import BASE_URL, api_headers
from attendance_page import AttendancePage
from learners_page import LearnersPage, unique
from playwright.sync_api import Browser, Page, expect

AddLearner = Callable[..., dict[str, Any]]
ClassSession = Callable[..., str]

LIST_LOAD_SECONDS = 3  # US-004 AC5, NT-07
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"


def full_name(learner: dict[str, Any]) -> str:
    return f"{learner['first_name']} {learner['family_name']}"


# ST-01 Teacher runs a class


def test_st01_teacher_runs_a_class(teacher_page: Page, add_learner: AddLearner) -> None:
    family = unique("Class")
    learners = [add_learner(name, family) for name in ["Ana", "Ben", "Cy", "Di", "Ed"]]
    teacher = teacher_page

    # US-014: the teacher starts today's class and opens its attendance list.
    teacher.goto("/sessions")
    teacher.get_by_role("button", name="Start today's class", exact=True).click()
    teacher.wait_for_url(re.compile(r"/sessions/[0-9a-f-]{36}$"))
    session_id = teacher.url.rsplit("/", 1)[1]
    teacher.get_by_role("link", name="Attendance", exact=True).click()
    teacher.wait_for_url(f"**/sessions/{session_id}/attendance")
    attendance = AttendancePage(teacher)
    attendance.arrive(session_id)
    # Earlier tests may have used today's class (one per date).
    attendance.count_from_now()
    attendance.expect_present_count(0)

    for learner in learners:
        attendance.checkbox(full_name(learner)).check()
    attendance.expect_present_count(5)

    newcomer = unique("Newcomer")
    attendance.add_and_mark("Hana", newcomer)
    expect(attendance.checkbox(f"Hana {newcomer}")).to_be_checked()
    attendance.expect_present_count(6)

    mistake = full_name(learners[0])
    attendance.checkbox(mistake).uncheck()
    attendance.expect_present_count(5)
    expect(attendance.row(mistake).locator(".badge-present")).to_have_count(0)

    attendance.open(session_id)
    attendance.expect_present_count(5)
    expect(attendance.checkbox(mistake)).not_to_be_checked()
    learners_page = LearnersPage(teacher)
    learners_page.open()
    expect(learners_page.row(f"Hana {newcomer}")).to_have_count(1)
    # The session for today exists in the class list.
    teacher.goto("/sessions")
    expect(teacher.locator(f'a[href="/sessions/{session_id}"]').first).to_be_visible()

    teacher.get_by_role("button", name="Log out", exact=True).click()
    teacher.wait_for_url(re.compile(r"/$"))


# US-004 acceptance criteria on screen


def test_ac1_ticked_learner_shows_present_with_the_time(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    learner = full_name(add_learner("Aroha", unique("Ngata")))
    attendance = AttendancePage(logged_in_page)
    attendance.open(class_session())

    attendance.checkbox(learner).check()

    attendance.expect_present_count(1)
    row = attendance.row(learner)
    expect(row.locator(".badge-present")).to_have_text("Present")
    expect(row.locator("td").nth(3)).to_contain_text(":")


def test_ac2_add_and_mark_present_adds_the_learner_in_one_step(
    logged_in_page: Page, class_session: ClassSession
) -> None:
    attendance = AttendancePage(logged_in_page)
    attendance.open(class_session())
    family = unique("Walker")

    attendance.add_and_mark("Mere", family)

    expect(attendance.add_message).to_have_text(
        f"Mere {family} is added to the class list and marked present"
    )
    expect(attendance.checkbox(f"Mere {family}")).to_be_checked()
    attendance.expect_present_count(1)
    expect(attendance.first_name).to_be_focused()


def test_add_and_mark_present_uses_a_learner_already_on_the_list(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    family = unique("Silva")
    add_learner("Ana", family)
    attendance = AttendancePage(logged_in_page)
    attendance.open(class_session())
    rows_before = attendance.rows.count()

    attendance.add_and_mark("ana", family.upper())

    expect(attendance.add_message).to_have_text(
        f"Ana {family} is already on the class list and is now marked present"
    )
    expect(attendance.checkbox(f"Ana {family}")).to_be_checked()
    expect(attendance.rows).to_have_count(rows_before)


def test_add_and_mark_present_needs_both_names(
    logged_in_page: Page, class_session: ClassSession
) -> None:
    attendance = AttendancePage(logged_in_page)
    attendance.open(class_session())

    attendance.add_and_mark("", "")

    page = logged_in_page
    expect(page.locator("#learner-first-name-error")).to_have_text(
        "First name is required"
    )
    expect(page.locator("#learner-family-name-error")).to_have_text(
        "Family name is required"
    )
    expect(attendance.first_name).to_be_focused()
    attendance.expect_present_count(0)


def test_ac3_learner_ticked_on_another_laptop_says_already_signed_in(
    logged_in_page: Page,
    add_learner: AddLearner,
    class_session: ClassSession,
    session_id: str,
) -> None:
    learner = add_learner("Sione", unique("Taufa"))
    lesson_session = class_session()
    attendance = AttendancePage(logged_in_page)
    attendance.open(lesson_session)
    # Another teacher ticks the learner; this page has not reloaded.
    response = logged_in_page.request.post(
        f"/api/access/sessions/{lesson_session}/attendance",
        headers=api_headers(session_id),
        data={"learner_id": learner["id"]},
    )
    assert response.status == 201

    attendance.checkbox(full_name(learner)).check()

    message = attendance.row(full_name(learner)).locator(".msg-info")
    expect(message).to_have_text("Already signed in")
    expect(message).to_be_in_viewport()
    expect(attendance.checkbox(full_name(learner))).to_be_checked()
    attendance.expect_present_count(1)


def test_ac4_unticking_removes_the_present_record(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    learner = full_name(add_learner("Ben", unique("Mistake")))
    session_id = class_session()
    attendance = AttendancePage(logged_in_page)
    attendance.open(session_id)
    attendance.checkbox(learner).check()
    attendance.expect_present_count(1)

    attendance.checkbox(learner).uncheck()

    attendance.expect_present_count(0)
    attendance.open(session_id)
    expect(attendance.checkbox(learner)).not_to_be_checked()


def test_ac5_nt07_list_of_50_learners_shows_within_3_seconds(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    family = unique("Bulk")
    for number in range(50):
        add_learner(f"Learner{number:02d}", family)
    attendance = AttendancePage(logged_in_page)
    session_id = class_session()

    start = time.perf_counter()
    attendance.open(session_id)
    expect(attendance.rows.filter(has_text=family)).to_have_count(50)
    seconds = time.perf_counter() - start

    assert seconds <= LIST_LOAD_SECONDS, f"List took {seconds:.2f}s"


# Access


def test_unknown_session_says_not_found(logged_in_page: Page) -> None:
    attendance = AttendancePage(logged_in_page)

    attendance.open("00000000-0000-0000-0000-000000000000")

    expect(logged_in_page.locator(".msg-error")).to_have_text("Class session not found")


def test_logged_out_person_is_sent_to_the_login_page(
    browser: Browser, class_session: ClassSession
) -> None:
    session_id = class_session()
    # class_session logs the demo coordinator in on the test's own page, so
    # the visitor gets a separate window with no login.
    context = browser.new_context(base_url=BASE_URL)
    try:
        visitor = context.new_page()
        visitor.goto(f"/sessions/{session_id}/attendance")

        # US-001: the server redirects before any attendance data is sent.
        visitor.wait_for_url(re.compile(r"/$"))
        expect(
            visitor.get_by_role("button", name="Sign in", exact=True)
        ).to_be_visible()
        expect(visitor.locator("table.data")).to_have_count(0)
    finally:
        context.close()


# NT-06 Plain and accessible


def test_nt06_learner_can_be_ticked_and_unticked_with_the_keyboard(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    learner = full_name(add_learner("Keyboard", unique("Only")))
    attendance = AttendancePage(logged_in_page)
    attendance.open(class_session())
    box = attendance.checkbox(learner)
    box.focus()

    logged_in_page.keyboard.press("Space")
    attendance.expect_present_count(1)
    expect(box).to_be_focused()
    logged_in_page.keyboard.press("Space")

    attendance.expect_present_count(0)
    expect(box).not_to_be_checked()


def test_nt06_attendance_page_has_no_accessibility_violations(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    learner = full_name(add_learner("Aroha", unique("Audit")))
    attendance = AttendancePage(logged_in_page)
    attendance.open(class_session())
    attendance.checkbox(learner).check()
    attendance.expect_present_count(1)

    logged_in_page.add_script_tag(
        **(
            {"path": os.environ["AXE_SCRIPT_PATH"]}
            if os.getenv("AXE_SCRIPT_PATH")
            else {"url": AXE_URL}
        )
    )
    violations = logged_in_page.evaluate(
        "async () => (await axe.run()).violations.map(v => v.id + ': ' + v.help)"
    )

    assert violations == []


# NT-01 Works with paper


def test_nt01_printed_list_has_no_menu_bar_or_form(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    learner = full_name(add_learner("Print", unique("Me")))
    attendance = AttendancePage(logged_in_page)
    attendance.open(class_session())

    logged_in_page.emulate_media(media="print")

    expect(logged_in_page.locator("header.bar")).to_be_hidden()
    expect(attendance.add_and_mark_button).to_be_hidden()
    expect(attendance.row(learner)).to_be_visible()
    expect(attendance.count).to_be_visible()


# NT-10 Correct te reo


def test_nt10_macrons_are_shown_exactly_in_the_attendance_list(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    family = unique("Māhina")
    add_learner("Tāne", family, "Te reo Māori")
    attendance = AttendancePage(logged_in_page)
    attendance.open(class_session())

    row = attendance.row(f"Tāne {family}")

    expect(row).to_have_count(1)
    expect(row.get_by_role("cell", name="Te reo Māori", exact=True)).to_be_visible()
