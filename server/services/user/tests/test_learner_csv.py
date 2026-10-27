"""Pure parsing tests with fictional learners; no DB fixtures or application startup."""

import csv
from io import StringIO

import pytest

from learner_csv import CSV_HEADER, MAX_CSV_BYTES, CsvFileError, parse_learner_csv


def document(rows: list[list[str]], newline: str = "\n") -> bytes:
    """
    Prepare or exercise document in the test learner csv test scenario.
    """
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator=newline)
    writer.writerow(CSV_HEADER)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def test_ac1_ten_valid_records() -> None:
    """
    Verify that ac1 ten valid records.
    """
    result = parse_learner_csv(
        document([[f"Fiction{i}", "Example", "", ""] for i in range(10)]),
        filename="learners.csv",
    )
    assert len(result.records) == 10
    assert [r.row_number for r in result.records] == list(range(2, 12))
    assert result.records[0].first_language is None
    assert result.records[0].contact is None
    assert not result.errors and not result.duplicates


def test_ac2_file_duplicates_trimmed_case_insensitive() -> None:
    """
    Verify that ac2 file duplicates trimmed case insensitive.
    """
    result = parse_learner_csv(
        document(
            [
                ["  Āria ", " Example ", " Māori ", " test@example.invalid "],
                ["āRIA", "EXAMPLE", "", ""],
                ["Āria", "Other", "", ""],
                ["Āria", "Example", "English", ""],
            ]
        ),
        filename="learners.csv",
    )
    assert len(result.records) == 2
    assert result.records[0].first_name == "Āria"
    assert result.records[0].first_language == "Māori"
    assert result.records[0].contact == "test@example.invalid"
    assert [d.record.row_number for d in result.duplicates] == [3, 5]
    assert [d.first_row_number for d in result.duplicates] == [2, 2]


@pytest.mark.parametrize("index,field", [(0, "first_name"), (1, "family_name")])
@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_ac3_missing_name_skips_only_bad_row(
    index: int, field: str, value: str
) -> None:
    """
    Verify that ac3 missing name skips only bad row.
    """
    row = ["Fiction", "Example", "", ""]
    row[index] = value
    result = parse_learner_csv(
        document([row, ["Valid", "Example", "", ""]]), filename="a.csv"
    )
    assert [r.row_number for r in result.records] == [3]
    assert result.errors[0].row_number == 2
    assert result.errors[0].field == field
    assert "is required" in result.errors[0].message


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("character", ["a", "界", "😀"])
def test_ac4_unicode_name_boundary(index: int, character: str) -> None:
    """
    Verify that ac4 unicode name boundary.
    """
    good = ["Fiction", "Example", "", ""]
    good[index] = " " + character * 100 + " "
    bad = good.copy()
    bad[index] = character * 101
    result = parse_learner_csv(document([good, bad]), filename="a.csv")
    assert len(result.records) == 1
    assert result.errors[0].row_number == 3
    assert result.errors[0].message == "Name must be 100 characters or fewer"


@pytest.mark.parametrize("filename", ["learners.txt", "learners.xlsx", "learners"])
def test_ac5_non_csv_extension(filename: str) -> None:
    """
    Verify that ac5 non csv extension.
    """
    with pytest.raises(CsvFileError, match="must be a CSV"):
        parse_learner_csv(document([]), filename=filename)


def test_ac5_byte_limit_inclusive() -> None:
    # CSV spaces are trimmed by the existing name validator; this is one valid row.
    """
    Verify that ac5 byte limit inclusive.
    """
    start = (",".join(CSV_HEADER) + "\nFiction,Example,,").encode()
    content = start + b" " * (MAX_CSV_BYTES - len(start))
    assert len(parse_learner_csv(content, filename="a.csv").records) == 1
    with pytest.raises(CsvFileError, match="1,048,576 bytes"):
        parse_learner_csv(content + b" ", filename="a.csv")


@pytest.mark.parametrize("content", [b"\xff", b"\xff\xfea\x00", b"a\x00b"])
def test_encoding_or_binary_rejects_file(content: bytes) -> None:
    """
    Verify that encoding or binary rejects file.
    """
    with pytest.raises(CsvFileError):
        parse_learner_csv(content, filename="a.csv")


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_bom_quotes_multiline_and_physical_row_numbers(ending: str) -> None:
    """
    Verify that bom quotes multiline and physical row numbers.
    """
    content = document(
        [
            ["Fiction", 'Example, "quoted"', "", "line1\nline2"],
            ["", "Example", "", ""],
            ["Valid", "Example", "", ""],
        ],
        ending,
    )
    result = parse_learner_csv(b"\xef\xbb\xbf" + content, filename="A.CSV")
    assert [r.row_number for r in result.records] == [2, 5]
    assert result.errors[0].row_number == 4
    assert result.records[0].family_name == 'Example, "quoted"'


@pytest.mark.parametrize(
    "content", [b"", b"first_name,family_name\n", b"wrong,header,here,now\n"]
)
def test_invalid_header(content: bytes) -> None:
    """
    Verify that invalid header.
    """
    with pytest.raises(CsvFileError, match="CSV header"):
        parse_learner_csv(content, filename="a.csv")


@pytest.mark.parametrize(
    "tail", [b'"unfinished', b"too,few\n", b"too,many,fields,here,extra\n"]
)
def test_late_format_error_returns_no_partial_result(tail: bytes) -> None:
    """
    Verify that late format error returns no partial result.
    """
    with pytest.raises(CsvFileError):
        parse_learner_csv(
            document([["Valid", "Example", "", ""]]) + tail, filename="a.csv"
        )


def test_invalid_row_does_not_reserve_duplicate_name() -> None:
    """
    Verify that invalid row does not reserve duplicate name.
    """
    result = parse_learner_csv(
        document(
            [["Fiction", "Example", "x" * 101, ""], ["Fiction", "Example", "", ""]]
        ),
        filename="a.csv",
    )
    assert len(result.errors) == 1 and len(result.records) == 1
    assert not result.duplicates


def test_header_only_is_empty_result() -> None:
    """
    Verify that header only is empty result.
    """
    result = parse_learner_csv(document([]), filename="a.csv")
    assert not result.records and not result.duplicates and not result.errors
