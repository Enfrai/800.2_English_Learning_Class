"""Coordinator CSV import; existing learner rules and schema remain unchanged."""

from collections.abc import Iterator
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auth import (
    AuthenticatedUser,
    authenticate_session,
    get_db,
    get_session_token,
    require_coordinator,
)
from learner_csv import MAX_CSV_BYTES, CsvFileError, parse_learner_csv
from learners import DuplicateLearnerError, add_learner

router = APIRouter(prefix="/learners", tags=["learner-import"])
IMPORT_LOCK = 800017


def import_db(request: Request) -> Iterator[Session]:
    """Keep the write transaction separate from authentication's read session."""
    yield from get_db(request)


@router.post("/import")
def import_learners(
    file: UploadFile,
    actor: Annotated[AuthenticatedUser, Depends(require_coordinator)],
    token: Annotated[str, Depends(get_session_token)],
    db: Annotated[Session, Depends(import_db)],
) -> dict:
    """Validate the whole file before writes; commit valid rows as one batch.

    The upload filename and parsed content determine CSV validity, not the
    browser's unreliable MIME label. No upload or row content is logged.
    """
    content = file.file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(413, "CSV file must be 1,048,576 bytes or fewer")
    try:
        parsed = parse_learner_csv(content, filename=file.filename or "")
    except CsvFileError as exc:
        raise HTTPException(422, str(exc)) from exc
    duplicates = [
        {
            **asdict(item.record),
            "source": "file",
            "first_row_number": item.first_row_number,
        }
        for item in parsed.duplicates
    ]
    imported = 0
    try:
        with db.begin():
            # Serialize imports across replicas without imposing a unique-name
            # constraint on US-003, which deliberately allows confirmed namesakes.
            # Manual learner writes do not take this lock and may still race.
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK})
            current = require_coordinator(authenticate_session(token, db))
            if current.user_id != actor.user_id:
                raise HTTPException(401, "Not authenticated")
            for record in parsed.records:
                try:
                    add_learner(
                        db,
                        first_name=record.first_name,
                        family_name=record.family_name,
                        first_language=record.first_language,
                        contact=record.contact,
                        created_by=current.user_id,
                    )
                except DuplicateLearnerError:
                    duplicates.append(
                        {
                            **asdict(record),
                            "source": "database",
                            "first_row_number": None,
                        }
                    )
                    continue
                imported += 1
    except SQLAlchemyError as exc:
        # Do not expose SQL statements, submitted personal data or partial success.
        raise HTTPException(
            500, "Unable to import learners. No learners were imported."
        ) from exc
    return {
        "imported_count": imported,
        "message": f"{imported} learners imported",
        "duplicates": sorted(duplicates, key=lambda item: item["row_number"]),
        "errors": [asdict(error) for error in parsed.errors],
    }
