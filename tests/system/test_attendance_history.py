"""Exercise real learner history, corrections, date filters and access boundaries.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

from datetime import date, timedelta
from uuid import uuid4

from api import BASE_URL
from playwright.sync_api import expect


def test_real_history_tracks_corrections_and_inclusive_range(
    logged_in_page, add_learner
):
    page = logged_in_page
    suffix = uuid4().hex[:10]
    learner = add_learner("Māia", f"History{suffix}")
    start = date(1900, 1, 1) + timedelta(days=int(suffix[:4], 16) % 30000)
    days = [start + timedelta(days=i) for i in range(5)]
    sessions = []
    headers = {"Origin": BASE_URL}
    for i, day in enumerate(days):
        response = page.request.post(
            "/api/staff/access/sessions",
            headers=headers,
            data={"session_date": day.isoformat()},
        )
        assert response.status == 200, response.text()
        sid = response.json()["id"]
        sessions.append(sid)
        # Preserve explicit history from before the learner was imported.
        for present in [True] if i % 2 == 0 else [True, False]:
            response = page.request.post(
                f"/api/staff/access/sessions/{sid}/corrections",
                headers=headers,
                data={
                    "learner_id": learner["id"],
                    "present": present,
                    "reason": "US-016 generated test data",
                },
            )
            assert response.status == 200, response.text()
    page.goto(f"/learners/{learner['id']}/history")
    expect(page.get_by_text("Present 3 of 5", exact=True)).to_be_visible()
    assert page.locator("tbody th").all_text_contents() == [
        d.isoformat() for d in reversed(days)
    ]
    page.get_by_label("Start date", exact=True).fill(days[1].isoformat())
    page.get_by_label("End date", exact=True).fill(days[3].isoformat())
    page.get_by_role("button", name="Apply dates", exact=True).click()
    expect(page.get_by_text("Present 1 of 3", exact=True)).to_be_visible()
    response = page.request.post(
        f"/api/staff/access/sessions/{sessions[2]}/corrections",
        headers=headers,
        data={"learner_id": learner["id"], "present": False},
    )
    assert response.status == 200
    page.get_by_role("button", name="Apply dates", exact=True).click()
    expect(page.get_by_text("Present 0 of 3", exact=True)).to_be_visible()
    response = page.request.get(
        f"/api/staff/access/learners/{learner['id']}/attendance-history?start_date=2026-10-26&end_date=2026-10-01"
    )
    assert response.status == 422


def test_teacher_history_is_readonly_and_unrecorded_is_empty(teacher_page, add_learner):
    learner = add_learner("History", f"Empty{uuid4().hex[:8]}")
    teacher_page.goto(f"/learners/{learner['id']}/history")
    expect(
        teacher_page.get_by_text("No attendance recorded yet", exact=True)
    ).to_be_visible()
    expect(teacher_page.get_by_role("checkbox")).to_have_count(0)
    response = teacher_page.request.post(
        f"/api/staff/access/learners/{learner['id']}/attendance-history",
        headers={"Origin": BASE_URL},
        data={"present": True},
    )
    assert response.status == 405


def test_anonymous_cannot_read_history(page):
    learner_id = uuid4()
    response = page.request.get(
        f"/api/staff/access/learners/{learner_id}/attendance-history"
    )
    assert response.status == 401
    page.goto(f"/learners/{learner_id}/history")
    expect(page).to_have_url(f"{BASE_URL}/")
