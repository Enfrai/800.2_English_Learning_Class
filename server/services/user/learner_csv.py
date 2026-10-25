"""Parse US-017 uploads without database access or partial streaming results."""

import csv
from dataclasses import dataclass, field
from io import StringIO
from pathlib import PurePath

from learners import LearnerValidationError, clean_learner_fields

MAX_CSV_BYTES = 1_048_576
CSV_HEADER = ("first_name", "family_name", "first_language", "contact")


class CsvFileError(ValueError):
    """Reject the entire upload; callers must not persist any of its records."""


@dataclass(frozen=True)
class CsvLearner:
    """Cleaned fields with the starting physical file line (header is line 1)."""

    row_number: int
    first_name: str
    family_name: str
    first_language: str | None
    contact: str | None


@dataclass(frozen=True)
class CsvDuplicate:
    record: CsvLearner
    first_row_number: int


@dataclass(frozen=True)
class CsvRowError:
    row_number: int
    field: str
    message: str


@dataclass
class CsvParseResult:
    records: list[CsvLearner] = field(default_factory=list)
    duplicates: list[CsvDuplicate] = field(default_factory=list)
    errors: list[CsvRowError] = field(default_factory=list)


def parse_learner_csv(content: bytes, *, filename: str) -> CsvParseResult:
    """Validate a complete UTF-8 CSV and classify its rows without saving anything.

    Accept a UTF-8 BOM and standard quoted/multiline CSV fields. Headers must
    match the template exactly, including order. Wrong column counts and broken
    CSV syntax reject the whole file, even after otherwise valid rows.
    Field validation reports the first error per row, following US-003 rules.
    Only valid rows participate in duplicate detection; database duplicates are
    deliberately left to the future import service. No files are opened here.
    """
    if len(content) > MAX_CSV_BYTES:
        raise CsvFileError("CSV file must be 1,048,576 bytes or fewer")
    if PurePath(filename).suffix.lower() != ".csv":
        raise CsvFileError("File must be a CSV file (.csv)")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvFileError("CSV file must use UTF-8 encoding") from exc
    if "\x00" in decoded:
        raise CsvFileError("CSV file must not contain NUL characters")

    # Python's default field ceiling is smaller than the permitted upload.
    # Only raise this process-wide parser limit; the byte cap above still bounds
    # every upload, and we never lower a limit another CSV consumer relies on.
    csv.field_size_limit(max(csv.field_size_limit(), MAX_CSV_BYTES))
    reader = csv.reader(StringIO(decoded, newline=""), strict=True)
    result = CsvParseResult()
    seen: dict[tuple[str, str], int] = {}
    try:
        if next(reader, None) != list(CSV_HEADER):
            raise CsvFileError("CSV header must be: " + ",".join(CSV_HEADER))
        while True:
            # csv.reader.line_num counts physical lines, including quoted newlines.
            row_number = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                break
            if len(row) != len(CSV_HEADER):
                raise CsvFileError(
                    f"CSV row {row_number} must contain exactly 4 columns"
                )
            try:
                fields = clean_learner_fields(
                    first_name=row[0],
                    family_name=row[1],
                    first_language=row[2],
                    contact=row[3],
                )
            except LearnerValidationError as exc:
                result.errors.append(CsvRowError(row_number, exc.field, exc.message))
                continue
            record = CsvLearner(
                row_number,
                str(fields["first_name"]),
                str(fields["family_name"]),
                fields["first_language"],
                fields["contact"],
            )
            # Match US-003's lower() comparison; do not introduce different Unicode
            # casefold/normalization rules for imported and manually entered names.
            key = (record.first_name.lower(), record.family_name.lower())
            if key in seen:
                result.duplicates.append(CsvDuplicate(record, seen[key]))
            else:
                seen[key] = row_number
                result.records.append(record)
    except csv.Error as exc:
        raise CsvFileError(f"Invalid CSV format near row {reader.line_num}") from exc
    return result
