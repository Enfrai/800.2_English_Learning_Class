"""System tests for the attendance (sign-in) page (US-004).

Test Plan section 5: ST-01 and the attendance-page parts of NT-01, NT-06,
NT-07 and NT-10. Each test uses its own class session and made-up learners,
so tests run in any order and do not need an empty database.

ST-01 starts with "Start today's class" (US-014, not built yet), so the
session is created by the ``class_session`` fixture instead. Teacher
accounts come with US-002, so the demo coordinator stands in for the
teacher; both roles may take attendance.

The manual version is docs/system_test/attendance_system_tests.md.

Author: Pei Wu
Date: 23 Oct 2026
"""

import os
import time
from collections.abc import Callable
from typing import Any

from api import api_headers
from attendance_page import AttendancePage
from learners_page import LearnersPage, unique
from playwright.sync_api import Page, expect

AddLearner = Callable[..., dict[str, Any]]
ClassSession = Callable[..., str]

LIST_LOAD_SECONDS = 3  # US-004 AC5, NT-07
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
PAST_ATTENDANCE_LOCKED = "Only a coordinator can correct past attendance"


def full_name(learner: dict[str, Any]) -> str:
    return f"{learner['first_name']} {learner['family_name']}"


# ST-01 Teacher runs a class


def test_st01_teacher_runs_a_class(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    family = unique("Class")
    learners = [add_learner(name, family) for name in ["Ana", "Ben", "Cy", "Di", "Ed"]]
    session_id = class_session()
    attendance = AttendancePage(logged_in_page)
    attendance.open(session_id)
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
    learners_page = LearnersPage(logged_in_page)
    learners_page.open()
    expect(learners_page.row(f"Hana {newcomer}")).to_have_count(1)

    logged_in_page.get_by_role("button", name="Log out", exact=True).click()
    logged_in_page.wait_for_url("/")


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


# Sessions that cannot be changed (US-015 AC3) and access


def test_past_session_is_read_only_for_teachers(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    learner = full_name(add_learner("Past", unique("Session")))
    attendance = AttendancePage(logged_in_page)

    attendance.open(class_session(days_ago=1))

    expect(attendance.past_warning).to_have_text(PAST_ATTENDANCE_LOCKED)
    expect(attendance.checkbox(learner)).to_be_disabled()
    expect(attendance.add_and_mark_button).to_have_count(0)


def test_unknown_session_says_not_found(logged_in_page: Page) -> None:
    attendance = AttendancePage(logged_in_page)

    attendance.open("00000000-0000-0000-0000-000000000000")

    expect(logged_in_page.locator(".msg-error")).to_have_text("Class session not found")


def test_logged_out_person_is_sent_to_the_login_page(
    page: Page, class_session: ClassSession
) -> None:
    page.goto(f"/sessions/{class_session()}/attendance")

    # US-001: the server redirects before any attendance data is sent.
    page.wait_for_url("/")
    expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
    expect(page.locator("table.data")).to_have_count(0)


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
