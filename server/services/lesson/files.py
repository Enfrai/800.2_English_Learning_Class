"""Check and store lesson files (US-006).

All file rules live in ``FileValidator`` so the upload endpoint, the tests and
any later import use the same checks and the same message. Files are kept
under ``LESSON_FILES_DIR`` (a Docker volume, outside the code) with a random
name; the original name is kept in the database and used for downloads.

Author: Sandhya Tiwari
Date: 23 Oct 2026
"""

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

KB = 1024
MB = 1024 * KB
MIN_FILE_BYTES = 1 * KB
MAX_FILE_BYTES = 10 * MB
CHUNK_BYTES = 64 * KB

# One message that states the whole rule (US-006 AC4, UI design document 6.8).
FILE_RULE = "Files must be PDF, DOCX, JPG or PNG, from 1 KB to 10 MB"
FILE_NAME_TOO_LONG = "File name must be 255 characters or fewer"
MAX_FILE_NAME_LENGTH = 255

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class FileType:
    extension: str
    mime_type: str
    # The first bytes every file of this type starts with.
    signature: bytes


FILE_TYPES = {
    ".pdf": FileType(".pdf", "application/pdf", b"%PDF-"),
    ".docx": FileType(".docx", DOCX_MIME, b"PK\x03\x04"),
    ".jpg": FileType(".jpg", "image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": FileType(".jpg", "image/jpeg", b"\xff\xd8\xff"),
    ".png": FileType(".png", "image/png", b"\x89PNG\r\n\x1a\n"),
}


class FileRuleError(Exception):
    """A file breaks the type or size rule. Nothing is stored."""

    def __init__(self, message: str = FILE_RULE) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class StoredFile:
    file_name: str
    storage_key: str
    mime_type: str
    file_size: int


class FileValidator:
    """The lesson file rules: four types, 1 KB to 10 MB each."""

    def __init__(
        self,
        min_bytes: int = MIN_FILE_BYTES,
        max_bytes: int = MAX_FILE_BYTES,
        file_types: dict[str, FileType] | None = None,
    ) -> None:
        self.min_bytes = min_bytes
        self.max_bytes = max_bytes
        self.file_types = file_types or FILE_TYPES

    def clean_name(self, file_name: str | None) -> str:
        """Return the name to keep, without any folder part a browser sent."""
        # Some browsers send "C:\\folder\\name.pdf"; keep only the last part.
        name = (file_name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not name:
            raise FileRuleError()
        if len(name) > MAX_FILE_NAME_LENGTH:
            raise FileRuleError(FILE_NAME_TOO_LONG)
        return name

    def type_for(self, file_name: str) -> FileType:
        """Return the file type from the name's extension, in any letter case."""
        file_type = self.file_types.get(Path(file_name).suffix.lower())
        if file_type is None:
            raise FileRuleError()
        return file_type

    def check_size(self, size: int) -> None:
        if size < self.min_bytes or size > self.max_bytes:
            raise FileRuleError()

    def check_content(self, path: Path, file_type: FileType) -> None:
        """Refuse a file whose content does not match its extension.

        This stops, for example, a program renamed to ``.pdf``.
        """
        with path.open("rb") as stored:
            if stored.read(len(file_type.signature)) != file_type.signature:
                raise FileRuleError()
        if file_type.extension == ".docx":
            try:
                with zipfile.ZipFile(path) as archive:
                    if "word/document.xml" not in archive.namelist():
                        raise FileRuleError()
            except zipfile.BadZipFile as error:
                raise FileRuleError() from error


class FileStore:
    """Lesson files on disk, named by a random storage key."""

    def __init__(self, root: Path, validator: FileValidator | None = None) -> None:
        self.root = root
        self.validator = validator or FileValidator()

    @classmethod
    def from_environment(cls) -> "FileStore":
        return cls(Path(os.getenv("LESSON_FILES_DIR", "/data/lesson-files")))

    def path_for(self, storage_key: str) -> Path:
        # Keys are made by save() as uuid4 hex, so they never contain "/" or "..".
        if not (len(storage_key) == 32 and storage_key.isalnum()):
            raise ValueError("Unexpected storage key")
        return self.root / storage_key[:2] / storage_key

    def save(self, file_name: str | None, content: BinaryIO) -> StoredFile:
        """Check the file and store it. Returns what to record in the database.

        The size is counted while reading, so a file over the limit is
        stopped at the limit and never fully written.

        Raises:
            FileRuleError: wrong type, too small, too big, or content that
                does not match the extension. Nothing is kept on disk.
        """
        name = self.validator.clean_name(file_name)
        file_type = self.validator.type_for(name)
        storage_key = uuid4().hex
        path = self.path_for(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        size = 0
        try:
            with partial.open("wb") as out:
                while chunk := content.read(CHUNK_BYTES):
                    size += len(chunk)
                    if size > self.validator.max_bytes:
                        raise FileRuleError()
                    out.write(chunk)
            self.validator.check_size(size)
            self.validator.check_content(partial, file_type)
            partial.replace(path)
        finally:
            partial.unlink(missing_ok=True)
        return StoredFile(name, storage_key, file_type.mime_type, size)

    def remove(self, storage_key: str) -> None:
        """Remove a stored file. Used only to undo a save that was not recorded."""
        self.path_for(storage_key).unlink(missing_ok=True)
