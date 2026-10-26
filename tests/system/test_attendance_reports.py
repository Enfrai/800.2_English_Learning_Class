"""Exercise real coordinator report downloads through Nginx and both services.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import csv
import io
from datetime import date, timedelta
from uuid import uuid4

from api import BASE_URL
from playwright.sync_api import expect
from pypdf import PdfReader


def test_coordinator_exports_three_classes_and_latest_correction(
    logged_in_page, add_learner
):
    page = logged_in_page
    suffix = uuid4().hex[:10]
    learner = add_learner("Māia", f"Report{suffix}")
    start = date(1900, 1, 1) + timedelta(days=int(suffix[:4], 16) % 30000)
    days = [start + timedelta(days=i) for i in (0, 2, 4)]
    headers = {"Origin": BASE_URL}
    sessions = []
    for day in days:
        response = page.request.post(
            "/api/staff/access/sessions",
            headers=headers,
            data={"session_date": day.isoformat()},
        )
        assert response.status == 200, response.text()
        sessions.append(response.json()["id"])
    for sid in (sessions[0], sessions[2]):
        response = page.request.post(
            f"/api/staff/access/sessions/{sid}/corrections",
            headers=headers,
            data={
                "learner_id": learner["id"],
                "present": True,
                "reason": "US-005 test fixture",
            },
        )
        assert response.status == 200, response.text()
    page.goto("/reports/attendance")
    page.get_by_label("Start date", exact=True).fill(days[0].isoformat())
    page.get_by_label("End date", exact=True).fill(days[-1].isoformat())
    with page.expect_download() as waiting:
        page.get_by_role("button", name="Download PDF", exact=True).click()
    pdf = waiting.value
    assert pdf.suggested_filename.endswith(".pdf")
    reader = PdfReader(pdf.path())
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert f"Māia Report{suffix}" in text
    assert "Present" in text and "Absent" in text
    for day in days:
        assert day.strftime("%d %b") in text
    with page.expect_download() as waiting:
        page.get_by_role("button", name="Download CSV", exact=True).click()
    rows = list(
        csv.reader(io.StringIO(waiting.value.path().read_text(encoding="utf-8-sig")))
    )
    row = next(row for row in rows[1:] if row[0] == f"Māia Report{suffix}")
    assert [row[rows[0].index(day.isoformat())] for day in days] == [
        "Present",
        "Absent",
        "Present",
    ]
    response = page.request.post(
        f"/api/staff/access/sessions/{sessions[0]}/corrections",
        headers=headers,
        data={
            "learner_id": learner["id"],
            "present": False,
            "reason": "US-005 corrected fixture",
        },
    )
    assert response.status == 200
    response = page.request.post(
        "/api/staff/access/reports/attendance",
        headers=headers,
        data={
            "start_date": days[0].isoformat(),
            "end_date": days[-1].isoformat(),
            "format": "csv",
        },
    )
    assert response.status == 200
    rows = list(csv.reader(io.StringIO(response.body().decode("utf-8-sig"))))
    row = next(row for row in rows[1:] if row[0] == f"Māia Report{suffix}")
    assert row[rows[0].index(days[0].isoformat())] == "Absent"


def test_real_report_empty_range_and_reversed_dates(logged_in_page):
    page = logged_in_page
    headers = {"Origin": BASE_URL}
    # US-014 rejects future classes, making this range predictably empty.
    response = page.request.post(
        "/api/staff/access/reports/attendance",
        headers=headers,
        data={"start_date": "9998-01-01", "end_date": "9998-01-02", "format": "pdf"},
    )
    assert response.status == 404
    assert response.json()["detail"] == "No classes found for these dates"
    assert "content-disposition" not in response.headers
    response = page.request.post(
        "/api/staff/access/reports/attendance",
        headers=headers,
        data={"start_date": "2026-10-26", "end_date": "2026-10-24", "format": "csv"},
    )
    assert response.status == 422
    assert response.json()["detail"]["message"] == "Start date must be before end date"


def test_real_teacher_and_anonymous_cannot_download(teacher_page, browser):
    response = teacher_page.request.post(
        "/api/staff/access/reports/attendance",
        headers={"Origin": BASE_URL},
        data={"start_date": "2026-10-24", "end_date": "2026-10-26", "format": "csv"},
    )
    assert response.status == 403
    response = teacher_page.goto("/reports/attendance")
    assert response.status == 403
    expect(
        teacher_page.get_by_text("You do not have permission", exact=True)
    ).to_be_visible()
    context = browser.new_context(base_url=BASE_URL)
    try:
        response = context.request.post(
            "/api/staff/access/reports/attendance",
            headers={"Origin": BASE_URL},
            data={
                "start_date": "2026-10-24",
                "end_date": "2026-10-26",
                "format": "pdf",
            },
        )
        assert response.status == 401
    finally:
        context.close()
