"""Verify real staff QR opening, learner sign-in, live attendance and closure.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from uuid import uuid4

from api import BASE_URL
from playwright.sync_api import expect


def test_qr_open_public_signin_live_attendance_and_close(
    logged_in_page, add_learner, browser
):
    staff = logged_in_page
    learner = add_learner("Māia", f"QR{uuid4().hex[:10]}")
    headers = {"Origin": BASE_URL}
    created = staff.request.post("/api/staff/access/sessions/today", headers=headers)
    assert created.status == 200
    sid = created.json()["id"]
    assert (
        staff.request.delete(
            f"/api/staff/access/sessions/{sid}/check-in", headers=headers
        ).status
        == 200
    )
    staff.goto(f"/sessions/{sid}")
    staff.get_by_role("button", name="Open check-in", exact=True).click()
    expect(staff.get_by_alt_text("QR code for class sign-in")).to_be_visible()
    window = staff.request.get(f"/api/staff/access/sessions/{sid}/check-in").json()
    assert (
        window["state"] == "open" and len(window["sign_in_url"].rsplit("/", 1)[1]) == 43
    )
    staff.goto(f"/sessions/{sid}/attendance")
    checkbox = staff.locator(f"#present-{learner['id']}")
    expect(checkbox).not_to_be_checked()
    context = browser.new_context(
        base_url=BASE_URL, viewport={"width": 360, "height": 800}
    )
    try:
        phone = context.new_page()
        phone.goto(window["sign_in_url"])
        phone.get_by_label("First name", exact=True).fill(learner["first_name"])
        phone.get_by_label("Family name", exact=True).fill(learner["family_name"])
        phone.get_by_role("button", name="Sign in", exact=True).click()
        expect(phone.get_by_text("You are signed in", exact=True)).to_be_visible()
        expect(checkbox).to_be_checked(timeout=10000)
        assert (
            staff.request.delete(
                f"/api/staff/access/sessions/{sid}/check-in", headers=headers
            ).status
            == 200
        )
        phone.reload()
        expect(
            phone.get_by_text("Check-in is closed. Please ask the teacher", exact=True)
        ).to_be_visible()
    finally:
        context.close()


def test_anonymous_cannot_open_close_or_read_qr_windows(page):
    sid = uuid4()
    for method in ("GET", "POST", "DELETE"):
        response = page.request.fetch(
            f"/api/staff/access/sessions/{sid}/check-in",
            method=method,
            headers={"Origin": BASE_URL},
        )
        assert response.status == 401
