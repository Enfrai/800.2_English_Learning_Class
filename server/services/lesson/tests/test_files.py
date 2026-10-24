"""Unit tests for the lesson file rule and file storage (US-006).

Case UT-40 from the Test Plan, section 4.6: four types, 1 KB to 10 MB
(minimum confirmed by the Story Owner on 23 Oct 2026). A refused file is
never left on disk.

Author: Sandhya Tiwari
Date: 23 Oct 2026
"""

import io
from pathlib import Path

import pytest
from sample_files import docx_bytes, exe_bytes, jpg_bytes, pdf_bytes, png_bytes

from files import DOCX_MIME, FILE_RULE, KB, MB, FileRuleError, FileStore


def stored_files(store: FileStore) -> list[Path]:
    return [path for path in store.root.rglob("*") if path.is_file()]


def save(store: FileStore, name: str, content: bytes):
    return store.save(name, io.BytesIO(content))


# Accepted


@pytest.mark.parametrize(
    ("name", "content", "mime_type"),
    [
        ("worksheet.pdf", pdf_bytes(2 * KB), "application/pdf"),
        ("worksheet.docx", docx_bytes(), DOCX_MIME),
        ("bus stop.jpg", jpg_bytes(), "image/jpeg"),
        ("bus stop.JPEG", jpg_bytes(), "image/jpeg"),
        ("map.png", png_bytes(), "image/png"),
    ],
)
def test_the_four_allowed_types_are_stored(
    store: FileStore, name: str, content: bytes, mime_type: str
) -> None:
    stored = save(store, name, content)

    assert stored.file_name == name
    assert stored.mime_type == mime_type
    assert stored.file_size == len(content)
    assert store.path_for(stored.storage_key).read_bytes() == content


def test_file_of_exactly_10_mb_is_accepted(store: FileStore) -> None:
    assert save(store, "big.pdf", pdf_bytes(10 * MB)).file_size == 10 * MB


def test_file_of_exactly_1_kb_is_accepted(store: FileStore) -> None:
    assert save(store, "small.pdf", pdf_bytes(1 * KB)).file_size == 1 * KB


def test_stored_name_is_random_so_two_files_with_one_name_both_stay(
    store: FileStore,
) -> None:
    first = save(store, "notes.pdf", pdf_bytes(2 * KB))
    second = save(store, "notes.pdf", pdf_bytes(3 * KB))

    assert first.storage_key != second.storage_key
    assert len(stored_files(store)) == 2


def test_folder_part_of_a_browser_file_name_is_dropped(store: FileStore) -> None:
    stored = save(store, "C:\\Users\\me\\Desktop\\kai.pdf", pdf_bytes(2 * KB))

    assert stored.file_name == "kai.pdf"


# Refused, with the rule in the message and nothing kept


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("big.pdf", pdf_bytes(10 * MB + 1)),
        ("big.pdf", pdf_bytes(int(10.1 * MB))),
        ("tiny.pdf", pdf_bytes(1 * KB - 1)),
        ("tiny.pdf", pdf_bytes(int(0.9 * KB))),
        ("empty.pdf", b""),
        ("setup.exe", exe_bytes()),
        ("notes.txt", b"plain text " * 200),
        ("no extension", pdf_bytes(2 * KB)),
        # A program renamed to look like an allowed type.
        ("setup.pdf", exe_bytes()),
        ("photo.png", jpg_bytes()),
        # A zip file that is not a Word document.
        ("archive.docx", b"PK\x03\x04" + b"0" * 2000),
    ],
)
def test_file_breaking_the_rule_is_refused_with_the_rule(
    store: FileStore, name: str, content: bytes
) -> None:
    with pytest.raises(FileRuleError) as error:
        save(store, name, content)

    assert error.value.message == FILE_RULE
    assert (
        error.value.message == "Files must be PDF, DOCX, JPG or PNG, from 1 KB to 10 MB"
    )
    assert stored_files(store) == []


def test_missing_file_name_is_refused(store: FileStore) -> None:
    with pytest.raises(FileRuleError):
        save(store, "", pdf_bytes(2 * KB))


def test_storage_key_from_outside_cannot_reach_other_folders(store: FileStore) -> None:
    with pytest.raises(ValueError):
        store.path_for("../../etc/passwd")
