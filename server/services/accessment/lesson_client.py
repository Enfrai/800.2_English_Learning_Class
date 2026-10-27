"""Read lesson titles through the authenticated Lesson API for class sessions.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID


class LessonUnavailableError(Exception):
    """The linked lesson no longer exists."""


class LessonServiceError(Exception):
    """The service could not provide a trustworthy lesson response."""


def request_lessons(path: str, authorization: str) -> Any:
    """
    Call the Lesson Service and decode a successful JSON response.
    """
    base = os.getenv("LESSON_API_URL", "http://nginx/api/lesson").rstrip("/")
    request = Request(base + path, headers={"Authorization": authorization})
    try:
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            raise LessonUnavailableError("Lesson is no longer available") from exc
        raise LessonServiceError("Lesson service unavailable") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise LessonServiceError("Lesson service unavailable") from exc


def lesson_title(lesson_id: UUID, authorization: str) -> str:
    """
    Look up the title of a live lesson through the authenticated Lesson API.
    """
    body = request_lessons(f"/lessons/{lesson_id}", authorization)
    try:
        if UUID(body["id"]) != lesson_id or not isinstance(body["title"], str):
            raise ValueError("Invalid lesson")
        return body["title"]
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise LessonServiceError("Invalid lesson response") from exc


def lesson_titles(authorization: str) -> dict[UUID, str]:
    """
    Return an identifier-to-title map for the available lessons.
    """
    try:
        rows = request_lessons("/lessons", authorization)
    except LessonUnavailableError as exc:
        raise LessonServiceError("Lesson service unavailable") from exc
    try:
        if not isinstance(rows, list):
            raise ValueError("Invalid lesson list")
        result = {}
        for row in rows:
            if not isinstance(row["title"], str):
                raise ValueError("Invalid lesson title")
            result[UUID(row["id"])] = row["title"]
        return result
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise LessonServiceError("Invalid lesson response") from exc
