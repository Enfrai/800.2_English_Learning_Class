"""Export coordinator-only attendance matrices as printable A4 PDF and CSV.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from io import BytesIO, StringIO
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from uuid import UUID
from xml.sax.saxutils import escape

import report_client
import user_client
from fastapi import APIRouter, Depends, HTTPException, Response
from models import attendance_records, class_sessions
from pydantic import BaseModel, ConfigDict
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

NO_CLASSES = "No classes found for these dates"
INVALID_RANGE = "Start date must be before end date"
FONT = "AkoReport"
FONT_LOCK = Lock()
DATES_PER_PAGE = 6


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date | None = None
    end_date: date | None = None
    format: Literal["pdf", "csv"]


@dataclass(frozen=True)
class ReportRow:
    learner_id: UUID
    name: str
    statuses: tuple[str, ...]


@dataclass(frozen=True)
class AttendanceReport:
    start: date
    end: date
    dates: tuple[date, ...]
    rows: tuple[ReportRow, ...]


def collect_report(
    factory: Callable[[], Session], start: date, end: date, authorization: str
) -> AttendanceReport:
    # One SELECT takes a consistent snapshot of sessions and current attendance.
    with factory() as db:
        records = (
            db.execute(
                select(
                    class_sessions.c.id,
                    class_sessions.c.session_date,
                    attendance_records.c.learner_id,
                    attendance_records.c.status,
                )
                .select_from(
                    class_sessions.outerjoin(
                        attendance_records,
                        attendance_records.c.session_id == class_sessions.c.id,
                    )
                )
                .where(class_sessions.c.session_date.between(start, end))
                .order_by(class_sessions.c.session_date, class_sessions.c.id)
            )
            .mappings()
            .all()
        )
    if not records:
        raise HTTPException(404, NO_CLASSES)
    dates = tuple(sorted({row["session_date"] for row in records}))
    recorded_ids = {
        row["learner_id"] for row in records if row["learner_id"] is not None
    }
    try:
        names = report_client.report_names(authorization, recorded_ids)
    except user_client.LoginRequiredError as exc:
        raise HTTPException(401, "Login required") from exc
    except user_client.UserServiceError as exc:
        raise HTTPException(
            503, "Learner information is unavailable. Please try again."
        ) from exc
    present = {
        (row["learner_id"], row["session_date"])
        for row in records
        if row["status"] == "present"
    }
    return AttendanceReport(
        start,
        end,
        dates,
        tuple(
            ReportRow(
                identifier,
                name,
                tuple(
                    "Present" if (identifier, day) in present else "Absent"
                    for day in dates
                ),
            )
            for identifier, name in sorted(
                names.items(), key=lambda pair: (pair[1].casefold(), str(pair[0]))
            )
        ),
    )


def spreadsheet_text(value: str) -> str:
    # Quoting CSV alone does not stop spreadsheets evaluating a formula.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + value
    return value


def render_csv(report: AttendanceReport) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Learner name", *(day.isoformat() for day in report.dates)])
    for row in report.rows:
        writer.writerow([spreadsheet_text(row.name), *row.statuses])
    return output.getvalue().encode("utf-8-sig")


def register_font() -> None:
    with FONT_LOCK:
        if FONT not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(
                TTFont(FONT, str(Path(__file__).parent / "fonts/DejaVuSans.ttf"))
            )


def render_pdf(report: AttendanceReport) -> bytes:
    register_font()
    stream = BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=landscape(A4),
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=34 * mm,
        bottomMargin=18 * mm,
        title="Ako attendance record",
        author="Ako",
        pageCompression=1,
    )
    name_style = ParagraphStyle(
        "Name", fontName=FONT, fontSize=11, leading=15, splitLongWords=True
    )
    cell_style = ParagraphStyle("Status", parent=name_style, alignment=TA_CENTER)
    head_style = ParagraphStyle("Header", parent=cell_style, fontSize=10, leading=14)
    label_style = ParagraphStyle("Label", parent=name_style, fontSize=10, leading=14)
    story = []
    for offset in range(0, len(report.dates), DATES_PER_PAGE):
        days = report.dates[offset : offset + DATES_PER_PAGE]
        if offset:
            story.append(PageBreak())
        story.extend(
            [
                Paragraph(
                    f"Class dates {offset + 1}-{offset + len(days)} of {len(report.dates)}",
                    label_style,
                ),
                Spacer(1, 4 * mm),
            ]
        )
        if not report.rows:
            story.extend(
                [Paragraph("No learners to report.", name_style), Spacer(1, 4 * mm)]
            )
        header = [Paragraph("Learner name", name_style)] + [
            Paragraph(day.strftime("%d %b<br/>%Y"), head_style) for day in days
        ]
        data = [header]
        for row in report.rows:
            data.append(
                [Paragraph(escape(row.name).replace("\n", "<br/>"), name_style)]
                + [
                    Paragraph(status, cell_style)
                    for status in row.statuses[offset : offset + len(days)]
                ]
            )
        name_width = 85 * mm
        table = LongTable(
            data,
            colWidths=[name_width]
            + [(document.width - name_width) / len(days)] * len(days),
            repeatRows=1,
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#555555")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(table)

    def page_header(canvas, doc):
        width, height = landscape(A4)
        canvas.saveState()
        canvas.setFillColor(colors.black)
        canvas.setFont(FONT, 17)
        canvas.drawString(18 * mm, height - 15 * mm, "Ako attendance record")
        canvas.setFont(FONT, 10)
        canvas.drawString(
            18 * mm,
            height - 22 * mm,
            f"Date range: {report.start.isoformat()} to {report.end.isoformat()}",
        )
        canvas.setFont(FONT, 8)
        canvas.drawString(
            18 * mm,
            height - 28 * mm,
            "Current learners and recorded historical learners. Missing present records are shown as Absent.",
        )
        canvas.setFont(FONT, 9)
        canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page_header, onLaterPages=page_header)
    return stream.getvalue()


def create_report_router(
    factory: Callable[[], Session], staff_dependency: Callable
) -> APIRouter:
    router = APIRouter(tags=["US-005 attendance reports"])

    @router.post("/reports/attendance")
    def export(payload: ReportIn, request: Any = Depends(staff_dependency)) -> Response:
        if request.staff.role != "coordinator":
            raise HTTPException(403, "You do not have permission")
        for field, label in (("start_date", "Start date"), ("end_date", "End date")):
            if getattr(payload, field) is None:
                raise HTTPException(
                    422, {"field": field, "message": f"{label} is required"}
                )
        if payload.start_date > payload.end_date:
            raise HTTPException(422, {"field": "end_date", "message": INVALID_RANGE})
        report = collect_report(
            factory, payload.start_date, payload.end_date, request.authorization
        )
        body = render_pdf(report) if payload.format == "pdf" else render_csv(report)
        return Response(
            body,
            media_type="application/pdf"
            if payload.format == "pdf"
            else "text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="ako-attendance-{payload.start_date}-{payload.end_date}.{payload.format}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
