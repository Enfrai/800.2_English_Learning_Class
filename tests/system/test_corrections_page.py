"""System tests for correcting past attendance (US-015).

Test Plan section 5: ST-04 (coordinator corrects attendance) and ST-05
(teacher cannot correct), with the correction view's parts of NT-06. Each
test uses its own class from last week and made-up learners, so tests run in
any order and do not need an empty database.

Past classes cannot be ticked through the page, so the learners who were
ticked during the class are inserted by the ``ticked_in_class`` fixture.

The manual version is docs/system_test/corrections_system_tests.md.

Author: Pei Wu
Date: 25 Oct 2026
"""

import re
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page, expect

from api import BASE_URL
from attendance_page import AttendancePage
from learners_page import unique

AddLearner = Callable[..., dict[str, Any]]
ClassSession = Callable[..., str]
TickedInClass = Callable[[str, str], None]

LAST_WEEK = 7  # days ago
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
# Message catalogue, UI design document section 7.
PAST_ATTENDANCE_LOCKED = "Only a coordinator can correct past attendance"
NO_PERMISSION = "You do not have permission"
# For example "25 Oct 2026, 9:08 pm".
CHANGE_TIME = re.compile(r"^\d{1,2} \w{3} \d{4}, \d{1,2}:\d{2}\s?[ap]m$")


def full_name(learner: dict[str, Any]) -> str:
    return f"{learner['first_name']} {learner['family_name']}"


def last_weeks_class(
    add_learner: AddLearner,
    class_session: ClassSession,
    ticked_in_class: TickedInClass,
) -> tuple[str, str, str]:
    """A class from last week where one learner was ticked and one was missed.

    Returns the session id, the ticked learner's name and the missed one's.
    """
    family = unique("Past")
    ticked = add_learner("Mere", family)
    missed = add_learner("Sione", family)
    session_id = class_session(days_ago=LAST_WEEK)
    ticked_in_class(session_id, ticked["id"])
    return session_id, full_name(ticked), full_name(missed)


def run_axe(page: Page) -> list[str]:
    page.add_script_tag(url=AXE_URL)
    return page.evaluate(
        "async () => (await axe.run()).violations.map(v => v.id + ': ' + v.help)"
    )


# ST-04 Coordinator corrects attendance


def test_st04_coordinator_corrects_attendance(
    logged_in_page: Page,
    add_learner: AddLearner,
    class_session: ClassSession,
    ticked_in_class: TickedInClass,
) -> None:
    session_id, ticked, missed = last_weeks_class(
        add_learner, class_session, ticked_in_class
    )
    coordinator = logged_in_page.request.get("/api/user/session").json()
    attendance = AttendancePage(logged_in_page)
    attendance.open(session_id)
    expect(attendance.correction_notice).to_have_text(
        "You are correcting a past class. "
        "Every change is logged with your name and the time"
    )
    expect(attendance.past_warning).to_have_count(0)
    expect(attendance.history_rows).to_have_count(0)
    attendance.expect_present_count(1)

    # AC1: mark a missing learner present
    attendance.checkbox(missed).check()
    attendance.expect_present_count(2)
    expect(attendance.row(missed).locator(".badge-corrected")).to_have_text("Corrected")

    # AC2: untick a learner marked by mistake
    attendance.checkbox(ticked).uncheck()
    attendance.expect_present_count(1)
    expect(attendance.row(ticked).locator(".badge-present")).to_have_count(0)
    expect(attendance.row(ticked).locator(".badge-corrected")).to_have_count(1)

    # AC4: the history lists both changes with who and when
    expect(attendance.history_rows).to_have_count(2)
    for row, change in zip(
        attendance.history_rows.all(),
        [f"{missed}: Absent → Present", f"{ticked}: Present → Absent"],
        strict=True,
    ):
        cells = row.locator("td")
        expect(cells.nth(0)).to_have_text(CHANGE_TIME)
        expect(cells.nth(1)).to_have_text(coordinator["display_name"])
        expect(cells.nth(2)).to_have_text(change)

    # The corrections are saved, not only shown.
    attendance.open(session_id)
    attendance.expect_present_count(1)
    expect(attendance.checkbox(missed)).to_be_checked()
    expect(attendance.checkbox(ticked)).not_to_be_checked()
    expect(attendance.history_rows).to_have_count(2)


def test_correction_view_has_no_add_learner_form(
    logged_in_page: Page, class_session: ClassSession
) -> None:
    attendance = AttendancePage(logged_in_page)

    attendance.open(class_session(days_ago=LAST_WEEK))

    expect(attendance.correction_notice).to_be_visible()
    expect(attendance.add_and_mark_button).to_have_count(0)


def test_ticking_todays_class_is_not_a_correction(
    logged_in_page: Page, add_learner: AddLearner, class_session: ClassSession
) -> None:
    learner = full_name(add_learner("Aroha", unique("Today")))
    attendance = AttendancePage(logged_in_page)
    attendance.open(class_session())

    attendance.checkbox(learner).check()

    attendance.expect_present_count(1)
    expect(attendance.row(learner).locator(".badge-corrected")).to_have_count(0)
    expect(attendance.correction_notice).to_have_count(0)
    expect(attendance.history_title).to_have_count(0)


# ST-05 Teacher cannot correct


def test_st05_teacher_cannot_correct(
    logged_in_page: Page,
    teacher_page: Page,
    add_learner: AddLearner,
    class_session: ClassSession,
    ticked_in_class: TickedInClass,
) -> None:
    session_id, ticked, missed = last_weeks_class(
        add_learner, class_session, ticked_in_class
    )
    attendance = AttendancePage(teacher_page)

    attendance.open(session_id)

    expect(attendance.past_warning).to_have_text(PAST_ATTENDANCE_LOCKED)
    expect(attendance.row_named(ticked).locator(".badge-present")).to_have_count(1)
    expect(attendance.row_named(missed)).to_have_count(1)
    expect(teacher_page.get_by_role("checkbox")).to_have_count(0)
    expect(attendance.add_and_mark_button).to_have_count(0)
    expect(attendance.correction_notice).to_have_count(0)
    expect(attendance.history_title).to_have_count(0)

    # Typing the correction address: the same request the page would send,
    # with the Origin a browser adds, so only the role can refuse it.
    address = f"/api/staff/access/sessions/{session_id}/corrections"
    origin = {"Origin": BASE_URL}
    learner_id = add_learner("Ana", unique("Silva"))["id"]
    correction = teacher_page.request.post(
        address, headers=origin, data={"learner_id": learner_id, "present": True}
    )
    history = teacher_page.request.get(address, headers=origin)
    assert (correction.status, correction.json()) == (403, {"detail": NO_PERMISSION})
    assert (history.status, history.json()) == (403, {"detail": NO_PERMISSION})
    attendance.open(session_id)
    attendance.expect_present_count(1)


def test_teacher_sees_which_learners_were_corrected(
    logged_in_page: Page,
    teacher_page: Page,
    add_learner: AddLearner,
    class_session: ClassSession,
    ticked_in_class: TickedInClass,
) -> None:
    session_id, ticked, missed = last_weeks_class(
        add_learner, class_session, ticked_in_class
    )
    coordinator_view = AttendancePage(logged_in_page)
    coordinator_view.open(session_id)
    coordinator_view.checkbox(missed).check()
    coordinator_view.expect_present_count(2)

    attendance = AttendancePage(teacher_page)
    attendance.open(session_id)

    attendance.expect_present_count(2)
    expect(attendance.row_named(missed).locator(".badge-corrected")).to_have_count(1)
    expect(attendance.row_named(ticked).locator(".badge-corrected")).to_have_count(0)


# NT-06 Plain and accessible


def test_nt06_correction_view_can_be_used_with_the_keyboard(
    logged_in_page: Page,
    add_learner: AddLearner,
    class_session: ClassSession,
    ticked_in_class: TickedInClass,
) -> None:
    session_id, _, missed = last_weeks_class(
        add_learner, class_session, ticked_in_class
    )
    attendance = AttendancePage(logged_in_page)
    attendance.open(session_id)
    box = attendance.checkbox(missed)

    box.focus()
    logged_in_page.keyboard.press("Space")

    attendance.expect_present_count(2)
    expect(box).to_be_focused()
    expect(attendance.history_rows).to_have_count(1)


def test_nt06_correction_and_teacher_views_have_no_accessibility_violations(
    logged_in_page: Page,
    teacher_page: Page,
    add_learner: AddLearner,
    class_session: ClassSession,
    ticked_in_class: TickedInClass,
) -> None:
    session_id, _, missed = last_weeks_class(
        add_learner, class_session, ticked_in_class
    )
    coordinator_view = AttendancePage(logged_in_page)
    coordinator_view.open(session_id)
    coordinator_view.checkbox(missed).check()
    expect(coordinator_view.history_rows).to_have_count(1)
    teacher_view = AttendancePage(teacher_page)
    teacher_view.open(session_id)
    teacher_view.expect_present_count(2)

    assert run_axe(logged_in_page) == []
    assert run_axe(teacher_page) == []
