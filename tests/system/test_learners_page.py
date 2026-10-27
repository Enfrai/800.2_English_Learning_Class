"""System tests for the Learners page (US-003).

Test Plan section 5: ST-11 and the parts of NT-05, NT-06, NT-07, NT-08 and
NT-10 that concern the Learners page. Each test creates its own made-up
learners, so tests run in any order and do not need an empty database.
The manual version is docs/system_test/learners_system_tests.md.

Author: Pei Wu
Date: 23 Oct 2026
"""

import os
import time
from collections.abc import Callable

from api import api_headers
from learners_page import LearnersPage, unique
from playwright.sync_api import Page, expect

LIST_UPDATE_SECONDS = 2  # ST-11
LIST_LOAD_SECONDS = 3  # NT-07
MIN_CONTROL_HEIGHT = 44  # UI design document section 5
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"


# Access to the page


def test_logged_out_person_is_sent_to_the_login_page(page: Page) -> None:
    """
    Verify that logged out person is sent to the login page.
    """
    page.goto("/learners")

    # US-001: the server redirects before any learner data is sent.
    page.wait_for_url("/")
    expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
    expect(page.locator("table.data")).to_have_count(0)


def test_learners_page_works_in_a_new_tab_after_logging_in(
    page: Page, log_in_through_page: Callable[[], None]
) -> None:
    """
    Verify that learners page works in a new tab after logging in.
    """
    log_in_through_page()
    new_tab = page.context.new_page()

    learners = LearnersPage(new_tab)
    learners.open()

    expect(learners.add_button).to_be_visible()
    expect(new_tab.locator('nav a[aria-current="page"]')).to_have_text("Learners")


def test_log_out_ends_access_to_the_learners(
    page: Page, log_in_through_page: Callable[[], None]
) -> None:
    """
    Verify that log out ends access to the learners.
    """
    log_in_through_page()
    LearnersPage(page).open()

    page.get_by_role("button", name="Log out", exact=True).click()
    page.wait_for_url("/")
    page.goto("/learners")

    page.wait_for_url("/")
    expect(page.locator("table.data")).to_have_count(0)


# ST-11 Learner records


def test_st11_added_learner_is_listed_within_2_seconds(
    learners_page: LearnersPage,
) -> None:
    """
    Verify that st11 added learner is listed within 2 seconds.
    """
    family = unique("Ngata")
    learners_page.add_button.click()
    expect(learners_page.first_name).to_be_focused()
    learners_page.fill("Aroha", family, "Te reo Māori", "021 555 0101")

    start = time.perf_counter()
    learners_page.save_button.click()
    expect(learners_page.row(f"Aroha {family}")).to_have_count(1)
    seconds = time.perf_counter() - start

    assert seconds <= LIST_UPDATE_SECONDS, f"List took {seconds:.2f}s"
    expect(learners_page.saved_message).to_have_text("Learner saved")
    expect(learners_page.row(f"Aroha {family}")).to_contain_text("Te reo Māori")


def test_st11_editing_first_language_keeps_the_other_fields(
    learners_page: LearnersPage,
) -> None:
    """
    Verify that st11 editing first language keeps the other fields.
    """
    family = unique("Ngata")
    learners_page.add("Aroha", family, "Te reo Māori", "021 555 0101")
    row = learners_page.row(f"Aroha {family}")

    row.get_by_role("button", name="Edit").click()
    expect(learners_page.first_name).to_have_value("Aroha")
    learners_page.first_language.fill("English")
    start = time.perf_counter()
    learners_page.save_button.click()
    expect(row.get_by_role("cell", name="English", exact=True)).to_be_visible()
    seconds = time.perf_counter() - start

    assert seconds <= LIST_UPDATE_SECONDS, f"List took {seconds:.2f}s"
    expect(row).to_have_count(1)
    expect(row.get_by_role("cell", name="021 555 0101", exact=True)).to_be_visible()


def test_st11_same_name_shows_warning_and_cancel_adds_nothing(
    learners_page: LearnersPage,
) -> None:
    """
    Verify that st11 same name shows warning and cancel adds nothing.
    """
    family = unique("Ngata")
    learners_page.add("Aroha", family)

    learners_page.add_button.click()
    learners_page.fill("aroha", family.upper())
    learners_page.save_button.click()

    warning = learners_page.duplicate_warning
    expect(warning).to_contain_text("A learner with this name already exists.")
    expect(warning.get_by_role("button", name="Cancel")).to_be_visible()
    expect(warning.get_by_role("button", name="Add anyway")).to_be_visible()

    warning.get_by_role("button", name="Cancel").click()

    expect(warning).to_have_count(0)
    learners_page.open()
    expect(learners_page.rows.filter(has_text=family)).to_have_count(1)


def test_st11_add_anyway_gives_two_records(learners_page: LearnersPage) -> None:
    """
    Verify that st11 add anyway gives two records.
    """
    family = unique("Ngata")
    learners_page.add("Aroha", family)

    learners_page.add_button.click()
    learners_page.fill("Aroha", family)
    learners_page.save_button.click()
    start = time.perf_counter()
    learners_page.duplicate_warning.get_by_role("button", name="Add anyway").click()
    expect(learners_page.row(f"Aroha {family}")).to_have_count(2)
    seconds = time.perf_counter() - start

    assert seconds <= LIST_UPDATE_SECONDS, f"List took {seconds:.2f}s"


# US-003 AC2 and AC5 on screen


def test_empty_names_show_messages_under_the_fields_and_save_nothing(
    learners_page: LearnersPage,
) -> None:
    """
    Verify that empty names show messages under the fields and save nothing.
    """
    rows_before = learners_page.rows.count()
    learners_page.add_button.click()
    learners_page.fill("", "", "English")

    learners_page.save_button.click()

    first_error = learners_page.field_error("first-name")
    expect(first_error).to_have_text("First name is required")
    expect(first_error).to_have_attribute("role", "alert")
    expect(learners_page.field_error("family-name")).to_have_text(
        "Family name is required"
    )
    expect(learners_page.first_name).to_be_focused()
    learners_page.open()
    expect(learners_page.rows).to_have_count(rows_before)


def test_name_of_101_characters_is_refused_and_100_is_accepted(
    learners_page: LearnersPage,
) -> None:
    """
    Verify that name of 101 characters is refused and 100 is accepted.
    """
    family = unique("Walker")
    learners_page.add_button.click()
    learners_page.fill("a" * 101, family)

    learners_page.save_button.click()

    expect(learners_page.field_error("first-name")).to_have_text(
        "Name must be 100 characters or fewer"
    )
    expect(learners_page.rows.filter(has_text=family)).to_have_count(0)

    learners_page.fill("a" * 100, family)
    learners_page.save_button.click()

    expect(learners_page.row(f"{'a' * 100} {family}")).to_have_count(1)


# NT-05 Privacy


def test_nt05_form_asks_only_for_what_the_club_needs(
    learners_page: LearnersPage,
) -> None:
    """
    Verify that nt05 form asks only for what the club needs.
    """
    learners_page.add_button.click()

    labels = learners_page.page.locator("form label").all_inner_texts()

    assert [label.strip() for label in labels] == [
        "First name",
        "Family name",
        "First language",
        "Phone or email",
    ]


# NT-06 Plain and accessible


def test_nt06_text_is_18px_and_controls_are_at_least_44px(
    learners_page: LearnersPage,
) -> None:
    """
    Verify that nt06 text is 18px and controls are at least 44px.
    """
    learners_page.add("Aroha", unique("Ngata"))
    learners_page.add_button.click()
    page = learners_page.page

    body_size = page.evaluate("getComputedStyle(document.body).fontSize")
    too_small = page.evaluate(
        """min => [...document.querySelectorAll('main button, main input')]
            .filter(e => e.offsetParent && e.getBoundingClientRect().height < min)
            .map(e => e.id || e.textContent)""",
        MIN_CONTROL_HEIGHT,
    )

    assert body_size == "18px"
    assert too_small == []


def test_nt06_learner_can_be_added_with_the_keyboard_only(
    learners_page: LearnersPage,
) -> None:
    """
    Verify that nt06 learner can be added with the keyboard only.
    """
    page = learners_page.page
    family = unique("Keyboard")
    for _ in range(20):
        page.keyboard.press("Tab")
        if learners_page.add_button.evaluate("e => e === document.activeElement"):
            break
    expect(learners_page.add_button).to_be_focused()

    page.keyboard.press("Enter")
    expect(learners_page.first_name).to_be_focused()
    page.keyboard.type("Ana")
    page.keyboard.press("Tab")
    expect(learners_page.family_name).to_be_focused()
    page.keyboard.type(family)
    page.keyboard.press("Enter")

    expect(learners_page.row(f"Ana {family}")).to_have_count(1)


def test_nt06_page_with_open_form_has_no_accessibility_violations(
    learners_page: LearnersPage,
) -> None:
    """
    Verify that nt06 page with open form has no accessibility violations.
    """
    learners_page.add("Aroha", unique("Ngata"))
    learners_page.add_button.click()
    page = learners_page.page

    page.add_script_tag(
        **(
            {"path": os.environ["AXE_SCRIPT_PATH"]}
            if os.getenv("AXE_SCRIPT_PATH")
            else {"url": AXE_URL}
        )
    )
    violations = page.evaluate(
        "async () => (await axe.run()).violations.map(v => v.id + ': ' + v.help)"
    )

    assert violations == []


# NT-07 Fast enough


def test_nt07_list_of_50_learners_shows_within_3_seconds(
    learners_page: LearnersPage, session_id: str
) -> None:
    """
    Verify that nt07 list of 50 learners shows within 3 seconds.
    """
    page = learners_page.page
    family = unique("Bulk")
    for number in range(50):
        response = page.request.post(
            "/api/user/learners",
            headers=api_headers(session_id),
            data={
                "first_name": f"Learner{number:02d}",
                "family_name": family,
                "first_language": "",
                "contact": "",
            },
        )
        assert response.status == 201, response.status
        time.sleep(0.1)  # Nginx allows 20 requests a second.

    start = time.perf_counter()
    page.goto("/learners")
    expect(learners_page.rows.filter(has_text=family)).to_have_count(50)
    seconds = time.perf_counter() - start

    assert seconds <= LIST_LOAD_SECONDS, f"List took {seconds:.2f}s"


# NT-08 Basic security


def test_nt08_sql_like_text_is_saved_as_plain_text(
    learners_page: LearnersPage,
) -> None:
    """
    Verify that nt08 sql like text is saved as plain text.
    """
    family = unique("x'); DROP TABLE learners;--")

    learners_page.add("Robert", family)
    learners_page.open()

    expect(learners_page.row(f"Robert {family}")).to_have_count(1)


# NT-10 Correct te reo


def test_nt10_macrons_are_shown_exactly_as_typed(learners_page: LearnersPage) -> None:
    """
    Verify that nt10 macrons are shown exactly as typed.
    """
    family = unique("Māhina")

    learners_page.add("Tāne", family, "Te reo Māori")
    learners_page.open()

    row = learners_page.row(f"Tāne {family}")
    expect(row).to_have_count(1)
    expect(row.get_by_role("cell", name="Te reo Māori", exact=True)).to_be_visible()
