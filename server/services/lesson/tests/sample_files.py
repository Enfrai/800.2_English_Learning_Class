"""Made-up lesson files for tests. Each starts with the real signature of its type.

Author: Sandhya Tiwari
Date: 23 Oct 2026
"""

import io
import zipfile

from files import KB


def pdf_bytes(size: int) -> bytes:
    head = b"%PDF-1.7\n"
    return head + b"0" * (size - len(head))


def png_bytes(size: int = 2 * KB) -> bytes:
    head = b"\x89PNG\r\n\x1a\n"
    return head + b"0" * (size - len(head))


def jpg_bytes(size: int = 2 * KB) -> bytes:
    head = b"\xff\xd8\xff\xe0"
    return head + b"0" * (size - len(head))


def docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document>" + "x" * 2000 + "</document>")
    return buffer.getvalue()


def exe_bytes(size: int = 2 * KB) -> bytes:
    head = b"MZ\x90\x00"
    return head + b"0" * (size - len(head))
