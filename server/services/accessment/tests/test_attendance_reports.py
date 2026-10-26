"""Verify US-005 permissions, attendance matrices, Unicode exports and A4 layout.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import csv
import importlib
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

import attendance_reports as reports
import pytest
import report_client
import user_client
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from models import attendance_records, class_sessions
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4, landscape
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

START = date(2026, 10, 1)


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'reports.sqlite'}")
    class_sessions.create(engine)
    attendance_records.create(engine)
    factory = sessionmaker(engine)
    names = {uuid4(): "Māia Test", uuid4(): "James Example", uuid4(): "Māia Test"}
    days = (START, START + timedelta(days=2), START + timedelta(days=4))
    sessions = []
    ids = list(names)
    with factory.begin() as db:
        for i, day in enumerate(days):
            sid = uuid4()
            sessions.append(sid)
            db.execute(
                class_sessions.insert().values(
                    id=sid, session_date=day, created_by=uuid4()
                )
            )
            db.execute(
                attendance_records.insert().values(
                    session_id=sid,
                    learner_id=ids[0],
                    status="present" if i != 1 else "absent",
                    recorded_by=uuid4(),
                )
            )
        db.execute(
            attendance_records.insert().values(
                session_id=sessions[1],
                learner_id=ids[1],
                status="present",
                recorded_by=uuid4(),
            )
        )
    calls = []

    def roster(authorization, recorded):
        calls.append((authorization, recorded))
        assert authorization == "Bearer coordinator"
        return names.copy()

    monkeypatch.setattr(report_client, "report_names", roster)

    def staff(authorization: str | None = Header(default=None)):
        if not authorization:
            raise HTTPException(401, "Login required")
        return SimpleNamespace(
            staff=SimpleNamespace(role=authorization.removeprefix("Bearer ")),
            authorization=authorization,
        )

    app = FastAPI()
    app.include_router(reports.create_report_router(factory, staff))
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            factory=factory,
            engine=engine,
            names=names,
            days=days,
            sessions=sessions,
            calls=calls,
        )
    engine.dispose()


def export(api, format="csv", **changes):
    return api.client.post(
        "/reports/attendance",
        headers={"Authorization": "Bearer coordinator"},
        json={
            "start_date": START.isoformat(),
            "end_date": (START + timedelta(days=4)).isoformat(),
            "format": format,
            **changes,
        },
    )


def csv_rows(response):
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def pdf_text(content):
    return "\n".join(
        page.extract_text() for page in PdfReader(io.BytesIO(content)).pages
    )


def test_csv_dates_are_inclusive_sorted_and_skip_nonclass_days(api):
    response = export(api)
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.headers["content-type"].startswith("text/csv")
    assert csv_rows(response)[0] == [
        "Learner name",
        *(day.isoformat() for day in api.days),
    ]
    assert len(csv_rows(response)) == 4
    assert all(len(row) == 4 for row in csv_rows(response))
    assert len(api.calls) == 1


def test_matrix_keeps_same_name_ids_separate_and_distinguishes_absent(api):
    rows = csv_rows(export(api))[1:]
    maia = [row for row in rows if row[0] == "Māia Test"]
    assert sorted(row[1:] for row in maia) == sorted(
        [["Present", "Absent", "Present"], ["Absent"] * 3]
    )
    assert next(row[1:] for row in rows if row[0] == "James Example") == [
        "Absent",
        "Present",
        "Absent",
    ]
    assert len(api.calls[0][1]) == 2  # The inactive/historical lookup is batched.


@pytest.mark.parametrize("format", ["csv", "pdf"])
def test_attachment_headers_no_cache_and_no_contact_data(api, format):
    response = export(api, format)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="ako-attendance-2026-10-01-2026-10-05.{format}"'
    )
    text = pdf_text(response.content) if format == "pdf" else response.text
    assert "Māia Test" in text
    for field in ("contact", "first_language", "recorded_by", "learner_id"):
        assert field not in text


def test_pdf_is_real_a4_with_each_name_status_and_date(api):
    response = export(api, "pdf")
    assert response.content.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(response.content))
    for page in reader.pages:
        assert float(page.mediabox.width) == pytest.approx(landscape(A4)[0], abs=0.01)
        assert float(page.mediabox.height) == pytest.approx(landscape(A4)[1], abs=0.01)
    text = pdf_text(response.content)
    assert text.count("Māia Test") == 2
    assert text.count("James Example") == 1
    assert text.count("Present") == 3
    # One 'Absent' is the explanation in the page header.
    assert text.count("Absent") == 7
    for day in api.days:
        assert day.strftime("%d %b") in text


@pytest.mark.parametrize("format", ["csv", "pdf"])
def test_no_classes_has_exact_message_and_never_calls_roster_or_renderer(
    api, monkeypatch, format
):
    monkeypatch.setattr(
        reports, "render_csv", lambda _: pytest.fail("No export allowed")
    )
    monkeypatch.setattr(
        reports, "render_pdf", lambda _: pytest.fail("No export allowed")
    )
    response = export(api, format, start_date="2026-09-01", end_date="2026-09-30")
    assert response.status_code == 404
    assert response.json()["detail"] == "No classes found for these dates"
    assert "content-disposition" not in response.headers
    assert api.calls == []


def test_reversed_range_has_exact_message_before_data_access(api):
    response = export(api, start_date="2026-10-05", end_date="2026-10-01")
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "field": "end_date",
        "message": "Start date must be before end date",
    }
    assert api.calls == []


def test_equal_start_and_end_exports_one_class(api):
    response = export(api, start_date=START.isoformat(), end_date=START.isoformat())
    assert response.status_code == 200 and len(csv_rows(response)[0]) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"format": "csv"},
        {"start_date": "invalid", "end_date": "2026-10-05", "format": "csv"},
        {"start_date": "2026-02-30", "end_date": "2026-10-05", "format": "pdf"},
        {"start_date": "2026-10-01", "end_date": "2026-10-05", "format": "exe"},
        {
            "start_date": "2026-10-01",
            "end_date": "2026-10-05",
            "format": "csv",
            "role": "coordinator",
        },
    ],
)
def test_bad_or_missing_inputs_export_nothing(api, payload):
    response = api.client.post(
        "/reports/attendance",
        headers={"Authorization": "Bearer coordinator"},
        json=payload,
    )
    assert response.status_code == 422 and "content-disposition" not in response.headers
    assert api.calls == []


@pytest.mark.parametrize(
    "role,status",
    [(None, 401), ("teacher", 403), ("learner", 403), ("visitor", 403), ("admin", 403)],
)
def test_only_coordinator_can_export_before_queries(api, role, status):
    with api.engine.connect() as connection:
        before = connection.execute(select(attendance_records)).all()
    response = api.client.post(
        "/reports/attendance",
        headers={"Authorization": f"Bearer {role}"} if role else {},
        json={"start_date": "2026-10-01", "end_date": "2026-10-05", "format": "pdf"},
    )
    assert response.status_code == status
    assert api.calls == []
    with api.engine.connect() as connection:
        assert connection.execute(select(attendance_records)).all() == before


@pytest.mark.parametrize(
    "failure,status",
    [(user_client.LoginRequiredError(), 401), (user_client.UserServiceError(), 503)],
)
def test_roster_errors_do_not_produce_partial_or_empty_files(
    api, monkeypatch, failure, status
):
    def fail(*args):
        raise failure

    monkeypatch.setattr(report_client, "report_names", fail)
    response = export(api)
    assert (
        response.status_code == status and "content-disposition" not in response.headers
    )


def test_reports_are_readonly_and_reflect_latest_corrections(api):
    first = list(api.names)[0]
    with api.factory.begin() as db:
        db.execute(
            attendance_records.update()
            .where(attendance_records.c.learner_id == first)
            .values(status="absent")
        )
    before = None
    with api.factory() as db:
        before = db.execute(select(attendance_records)).all()
    report = reports.collect_report(
        api.factory, api.days[0], api.days[-1], "Bearer coordinator"
    )
    assert (
        next(row.statuses for row in report.rows if row.learner_id == first)
        == ("Absent",) * 3
    )
    reports.render_csv(report)
    reports.render_pdf(report)
    with api.factory() as db:
        assert db.execute(select(attendance_records)).all() == before


@pytest.mark.parametrize(
    "name",
    [
        "Aroha, Test",
        'Aroha "Test"',
        "Aroha\nTest",
        "=SUM(1,2) Test",
        "+formula Test",
        "-formula Test",
        "@formula Test",
        "\tformula Test",
        "  =formula Test",
        "Māori āēīōū ĀĒĪŌŪ",
    ],
)
def test_csv_escaping_unicode_and_formula_safety(name):
    report = reports.AttendanceReport(
        START, START, (START,), (reports.ReportRow(uuid4(), name, ("Present",)),)
    )
    row = list(csv.reader(io.StringIO(reports.render_csv(report).decode("utf-8-sig"))))[
        1
    ]
    assert row[0] == reports.spreadsheet_text(name)
    if name.lstrip().startswith(("=", "+", "-", "@")) or name.startswith("\t"):
        assert row[0].startswith("'")
    assert row[1] == "Present"


def test_pdf_escapes_markup_preserves_macrons_and_full_long_names():
    name = "A" * 100 + " " + "B" * 100
    report = reports.AttendanceReport(
        START,
        START,
        (START,),
        tuple(
            reports.ReportRow(uuid4(), n, ("Present",))
            for n in (name, "Māori āēīōū ĀĒĪŌŪ", "<b>Aroha & Test</b>")
        ),
    )
    text = pdf_text(reports.render_pdf(report))
    assert "A" * 100 + "B" * 100 in "".join(text.split())
    assert "Māori āēīōū ĀĒĪŌŪ" in text
    assert "<b>Aroha & Test</b>" in text


def test_twelve_classes_fifty_learners_pdf_within_ten_seconds(api):
    api.names.clear()
    api.names.update({uuid4(): f"Learner {i:02d} Māia Test" for i in range(50)})
    with api.factory.begin() as db:
        db.execute(attendance_records.delete())
        for i in range(5, 14):
            db.execute(
                class_sessions.insert().values(
                    session_date=START + timedelta(days=i), created_by=uuid4()
                )
            )
    begin = monotonic()
    response = export(api, "pdf", end_date="2026-10-14")
    assert response.status_code == 200
    assert monotonic() - begin < 10
    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) > 1
    text = pdf_text(response.content)
    for name in api.names.values():
        assert text.count(name) == 2
    assert text.count("Absent") == 50 * 12 + len(reader.pages)
    assert all("Learner name" in page.extract_text() for page in reader.pages)


def test_many_date_bands_and_empty_roster_still_generate_valid_exports():
    days = tuple(START + timedelta(days=i) for i in range(14))
    report = reports.AttendanceReport(days[0], days[-1], days, ())
    reader = PdfReader(io.BytesIO(reports.render_pdf(report)))
    assert len(reader.pages) == 3
    assert "No learners to report." in pdf_text(reports.render_pdf(report))
    assert (
        len(
            list(
                csv.reader(io.StringIO(reports.render_csv(report).decode("utf-8-sig")))
            )[0]
        )
        == 15
    )


def test_concurrent_pdf_requests_keep_correct_names():
    def render(i):
        report = reports.AttendanceReport(
            START,
            START,
            (START,),
            (reports.ReportRow(uuid4(), f"Unique {i} Māia", ("Present",)),),
        )
        return pdf_text(reports.render_pdf(report))

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(render, range(8)))
    for i, text in enumerate(results):
        assert f"Unique {i} Māia" in text


def test_database_snapshot_is_one_select_and_report_does_not_write(api):
    calls = []

    def trace(connection, cursor, statement, parameters, context, many):
        calls.append(statement)

    event.listen(api.engine, "before_cursor_execute", trace)
    try:
        export(api)
    finally:
        event.remove(api.engine, "before_cursor_execute", trace)
    assert len(calls) == 1 and calls[0].lstrip().upper().startswith("SELECT")


def test_actual_application_registers_report_auth_and_private_errors(api, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    module = importlib.import_module("app")
    monkeypatch.setattr(module, "SessionLocal", api.factory)
    monkeypatch.setattr(
        user_client,
        "current_staff",
        lambda _: user_client.Staff(uuid4(), "Coordinator", "coordinator"),
    )
    client = TestClient(module.app)
    response = client.post(
        "/reports/attendance",
        headers={"Authorization": "Bearer coordinator"},
        json={"start_date": "2026-10-01", "end_date": "2026-10-05", "format": "csv"},
    )
    assert response.status_code == 200 and "Māia" in response.text
    denied = client.post("/reports/attendance", json={"format": "csv"})
    assert denied.status_code == 401 and denied.headers["cache-control"] == "no-store"
    client.close()
